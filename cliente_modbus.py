import streamlit as st
import pandas as pd
import time
from pymodbus.client import ModbusTcpClient

# Configuración del cliente Modbus
MODBUS_HOST = 'localhost'
MODBUS_PORT = 5020

# Función para leer el estado actual
def leer_estado_actual():
    client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
    client.connect()
    result = client.read_coils(address=0, count=16)
    client.close()
    if result.isError():
        return None
    return result.bits

# Función para escribir en una salida
def escribir_salida_manual(coil_address, value):
    client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
    client.connect()
    result = client.write_coil(coil_address, value)
    client.close()
    if result.isError():
        st.error(f"Error escribiendo Q{coil_address}: {result}")
    else:
        st.success(f"Q{coil_address} actualizada a {'ON' if value else 'OFF'}")

# Interfaz de Streamlit
st.title("Panel de Control Modbus")

# Refresco automático
refresh_rate = st.sidebar.slider("Frecuencia de actualización (seg)", 1, 10, 2)

# Control Manual
st.subheader("Control Manual de Salidas (Escritura)")
control_cols = st.columns(16)
for i in range(16):
    with control_cols[i]:
        if st.button(f"Activar Q{i}", key=f"on_{i}"):
            escribir_salida_manual(i, True)
        if st.button(f"Desactivar Q{i}", key=f"off_{i}"):
            escribir_salida_manual(i, False)

# Estado actual
st.subheader("Estado Actual de Salidas (Q)")
estado_actual = leer_estado_actual()
if estado_actual:
    cols = st.columns(len(estado_actual))
    for i, val in enumerate(estado_actual):
        color = "🟢" if val else "🔴"
        cols[i].markdown(f"**Q{i}** {color}")
else:
    st.error("No se pudo leer el estado actual del servidor.")

# Actualización automática
st.markdown("Actualizando automáticamente cada {} segundos...".format(refresh_rate))
time.sleep(refresh_rate)
st.rerun()