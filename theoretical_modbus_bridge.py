# theoretical_modbus_bridge.py
"""
Bridge Modbus <-> Memoria Compartida (CADe SIMU / PC-SIMU)
- Requisitos: Python 3.8+, pymodbus (3.x)
- Pip: pip install pymodbus
- Guarda como theoretical_modbus_bridge.py
"""

import asyncio
import logging
import threading
import time
import os
import csv
import ctypes
from ctypes import wintypes

from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext

# -------------------------
# CONFIGURACIÓN
# -------------------------
MODBUS_IP = "0.0.0.0"
MODBUS_PORT = 5020                 # puerto del servidor Modbus (502 requiere admin)
SHARED_MEM_NAME = "Global\\CADE_IO_MAP"  # Nombre candidato (ajustá según lo detectes)
SHARED_MEM_SIZE = 256             # bytes (ajustá según estructura real)
SHM_INPUT_OFFSET = 0              # offset bytes para Inputs (I)
SHM_OUTPUT_OFFSET = 2             # offset bytes para Outputs (Q)
SHM_INPUT_BYTES = 2               # nº de bytes para Inputs
SHM_OUTPUT_BYTES = 2              # nº de bytes para Outputs

LOG_CSV = "registro_datos.csv"
POLL_INTERVAL = 0.1               # segundos entre sincronizaciones

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("bridge")

# -------------------------
# UTILIDADES MEMORIA COMPARTIDA (Windows)
# -------------------------
kernel32 = ctypes.windll.kernel32

# Flags
FILE_MAP_READ  = 0x0004
FILE_MAP_WRITE = 0x0002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

OpenFileMapping = kernel32.OpenFileMappingW
OpenFileMapping.restype = wintypes.HANDLE
OpenFileMapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

MapViewOfFile = kernel32.MapViewOfFile
MapViewOfFile.restype = wintypes.LPVOID
MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]

UnmapViewOfFile = kernel32.UnmapViewOfFile
UnmapViewOfFile.restype = wintypes.BOOL
UnmapViewOfFile.argtypes = [wintypes.LPCVOID]

CloseHandle = kernel32.CloseHandle
CloseHandle.restype = wintypes.BOOL
CloseHandle.argtypes = [wintypes.HANDLE]

def try_open_shared_mem(name, size, write=False):
    """Intenta mapear el objeto de memoria compartida indicado por name.
    Devuelve (ptr, handle) o (None, None) si no existe / falla.
    """
    access = FILE_MAP_READ | FILE_MAP_WRITE if write else FILE_MAP_READ
    h = OpenFileMapping(access, False, name)
    if not h:
        return None, None
    p = MapViewOfFile(h, access, 0, 0, size)
    if not p:
        CloseHandle(h)
        return None, None
    return p, h

def close_shared_mem(ptr, handle):
    if ptr:
        UnmapViewOfFile(ptr)
    if handle:
        CloseHandle(handle)

def read_shared_memory_bytes(name, size):
    """Lectura segura: devuelve bytes o None"""
    try:
        p, h = try_open_shared_mem(name, size, write=False)
        if not p:
            return None
        buf = (ctypes.c_ubyte * size).from_address(ctypes.addressof(ctypes.c_ubyte.from_address(p)))
        data = bytes(buf)
        close_shared_mem(p, h)
        return data
    except Exception as e:
        log.debug(f"read_shared_memory_bytes exception: {e}")
        return None

def write_shared_memory_bytes(name, offset, bts):
    """Escribe bytes en la memoria compartida si es posible. Retorna True/False"""
    try:
        p, h = try_open_shared_mem(name, max(offset + len(bts), SHARED_MEM_SIZE), write=True)
        if not p:
            return False
        base = ctypes.addressof(ctypes.c_ubyte.from_address(p))
        dest = (ctypes.c_ubyte * len(bts)).from_address(base + offset)
        for i, val in enumerate(bts):
            dest[i] = val
        close_shared_mem(p, h)
        return True
    except Exception as e:
        log.debug(f"write_shared_memory_bytes exception: {e}")
        return False

# -------------------------
# UTIL: conversión bytes <-> lista de bool (LSB = bit0)
# -------------------------
def bytes_to_bool_list(bts):
    """Convierte bytes en lista de booleanos (bitwise, LSB first)."""
    res = []
    for byte in bts:
        for i in range(8):
            res.append(bool((byte >> i) & 1))
    return res

def bool_list_to_bytes(bools, nbytes):
    """Convierte lista de booleanos a bytes (LSB first) y devuelve nbytes length."""
    bts = bytearray(nbytes)
    for i, val in enumerate(bools):
        byte_index = i // 8
        bit_index = i % 8
        if byte_index >= nbytes:
            break
        if val:
            bts[byte_index] |= (1 << bit_index)
    return bytes(bts)

# -------------------------
# DATASOURCE MODBUS
# -------------------------
# Creamos datastore Modbus con 200 bits (suficiente)
store = ModbusSequentialDataBlock(0, [0] * 200)
context = ModbusServerContext(store, single=True)

# Helpers para acceder a coils en el contexto
def modbus_read_coils(start, count):
    """Lee coils desde el datastore (start, count). Devuelve lista de bools."""
    try:
        res = context[0].getValues(start, count)  # según pymodbus 3.x
        # getValues devuelve lista de ints/booleans
        return [bool(x) for x in res]
    except Exception as e:
        log.debug(f"modbus_read_coils error: {e}")
        return [False] * count

def modbus_write_coils(start, values):
    """Escribe valores (lista de 0/1 o bool) en coils a partir de start."""
    try:
        # setValues(address, list)
        context[0].setValues(start, [int(bool(x)) for x in values])
        return True
    except Exception as e:
        log.debug(f"modbus_write_coils error: {e}")
        return False

# -------------------------
# CSV Logger (salidas)
# -------------------------
def escribir_registro(salidas):
    """Escribe timestamp + salidas (lista de 0/1) en CSV con encabezado si no existe."""
    file_exists = os.path.exists(LOG_CSV)
    try:
        with open(LOG_CSV, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                header = ["timestamp"] + [f"Q{i}" for i in range(len(salidas))]
                writer.writerow(header)
            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S")] + [int(bool(x)) for x in salidas])
    except Exception as e:
        log.warning(f"No se pudo escribir en CSV: {e}")

# -------------------------
# Tareas asíncronas / hilos
# -------------------------
class SharedMemorySync:
    """Clase auxiliar que mantiene el estado anterior y gestiona sync y logging."""
    def __init__(self, shm_name, shm_size, in_off, in_len, out_off, out_len):
        self.shm_name = shm_name
        self.shm_size = shm_size
        self.in_off = in_off
        self.in_len = in_len
        self.out_off = out_off
        self.out_len = out_len
        self.prev_outputs = None
        self.fallback = False
        # fallback buffer local si no hay memoria compartida
        self.local_buf = bytearray(shm_size)

    def read_shm(self):
        data = read_shared_memory_bytes(self.shm_name, self.shm_size)
        if data is None:
            # fallback: usar buffer local y marcarlo
            self.fallback = True
            return bytes(self.local_buf)
        else:
            self.fallback = False
            return data

    def write_shm(self, offset, bts):
        ok = write_shared_memory_bytes(self.shm_name, offset, bts)
        if not ok:
            # intentar fallback write en buffer local
            self.fallback = True
            for i, val in enumerate(bts):
                self.local_buf[offset + i] = val
        return ok

    def parse_io_from_shm(self, data):
        # Inputs
        input_bytes = data[self.in_off:self.in_off + self.in_len]
        output_bytes = data[self.out_off:self.out_off + self.out_len]
        inputs = bytes_to_bool_list(input_bytes)
        outputs = bytes_to_bool_list(output_bytes)
        return inputs, outputs

# Instancia global de sync
shm_sync = SharedMemorySync(SHARED_MEM_NAME, SHARED_MEM_SIZE, SHM_INPUT_OFFSET, SHM_INPUT_BYTES, SHM_OUTPUT_OFFSET, SHM_OUTPUT_BYTES)

# Tarea 1: leer SHM -> actualizar datastore Modbus y loguear cambios en outputs
async def task_shm_to_modbus():
    log.info("Arrancando tarea SHM->Modbus")
    while True:
        data = shm_sync.read_shm()
        if data:
            inputs, outputs = shm_sync.parse_io_from_shm(data)
            # Actualizar discrete inputs en Modbus (si quieres distinguir types, aquí simplificamos usando coils area for demo)
            modbus_write_coils(0, inputs)      # mapeo simple: coils 0.. = inputs
            modbus_write_coils(16, outputs)    # mapeo outputs en coils 16.. (evita solapamientos)
            # Loguear cambios de salidas (outputs)
            if shm_sync.prev_outputs != outputs:
                escribir_registro(outputs)
                shm_sync.prev_outputs = outputs.copy()
        await asyncio.sleep(POLL_INTERVAL)

# Tarea 2: leer datastore Modbus (coils que puedan haber sido escritos por clientes) -> escribir SHM outputs
async def task_modbus_to_shm():
    log.info("Arrancando tarea Modbus->SHM")
    while True:
        # Leemos del datastore las coils "manuales" que representan outputs escritos por HMI
        # Asumimos que el dashboard escribe en coils 32.. (salidas de control manual). Ajustá según tu mapping.
        manual_coils = modbus_read_coils(32, SHM_OUTPUT_BYTES * 8)
        # Convertir a bytes y escribir en SHM offset de outputs
        bts = bool_list_to_bytes(manual_coils, SHM_OUTPUT_BYTES)
        shm_sync.write_shm(SHM_OUTPUT_OFFSET, bts)
        await asyncio.sleep(POLL_INTERVAL)

# -------------------------
# Server runner
# -------------------------
async def run_server():
    # Lanzar tareas de sync
    t1 = asyncio.create_task(task_shm_to_modbus())
    t2 = asyncio.create_task(task_modbus_to_shm())

    log.info(f"🚀 Iniciando servidor Modbus TCP en {MODBUS_IP}:{MODBUS_PORT}")
    await StartAsyncTcpServer(context=context, address=(MODBUS_IP, MODBUS_PORT))

# -------------------------
# ENTRYPOINT
# -------------------------
if __name__ == "__main__":
    try:
        log.info("Bridge inicializando...")
        # Información de arranque
        log.info(f"SHM name: {SHARED_MEM_NAME} (size={SHARED_MEM_SIZE})")
        log.info("Mapa: Inputs bytes @%d len=%d, Outputs bytes @%d len=%d",
                 SHM_INPUT_OFFSET, SHM_INPUT_BYTES, SHM_OUTPUT_OFFSET, SHM_OUTPUT_BYTES)
        asyncio.run(run_server())
    except KeyboardInterrupt:
        log.info("Bridge detenido por usuario.")
    except Exception as e:
        log.exception(f"Error en bridge principal: {e}")

