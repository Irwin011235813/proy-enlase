import streamlit as st
import pandas as pd
import time
from pymodbus.client import ModbusTcpClient

# --- CONFIGURACIÓN ---
MODBUS_HOST = "localhost"
MODBUS_PORT = 5020   # debe coincidir con el puerto del bridge
LOG_FILE = "registro_datos.csv"
N_COILS = 8          # número de salidas Q0–Q7

# --- FUNCIONES ---

def leer_estado_actual():
    """Lee el estado de las salidas (coils) desde el servidor Modbus."""
    try:
        client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
        client.connect()

        # En las nuevas versiones de pymodbus no se usa 'slave' ni 'unit'
        result = client.read_coils(0, N_COILS)

        client.close()
        if result.isError():
            st.error(f"Error leyendo coils: {result}")
            return None
        return result.bits[:N_COILS]  # Solo los primeros N_COILS bits
    except Exception as e:
        st.error(f"Error de conexión Modbus: {e}")
        return None



def escribir_salida_manual(coil_address, value):
    """Escribe un valor booleano (True/False) a una Coil específica."""
    try:
        client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
        client.connect()
        result = client.write_coil(address=coil_address, value=value, slave=1)
        client.close()
        if result.isError():
            st.error(f"Error escribiendo Q{coil_address}: {result}")
        else:
            st.success(f"Q{coil_address} → {'ON' if value else 'OFF'}")
    except Exception as e:
        st.error(f"Error de conexión al escribir Modbus: {e}")


def leer_registro():
    """Lee el archivo CSV de registro de datos."""
    try:
        df = pd.read_csv(LOG_FILE)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    except Exception as e:
        st.warning(f"No se pudo leer el registro ({e})")
        return None


# --- INTERFAZ STREAMLIT ---

st.set_page_config(page_title="Panel de Control Modbus", layout="wide")
st.title("🧩 Panel de Control - Modbus Bridge (Lectura / Escritura)")

# Control del refresco
refresh_rate = st.sidebar.slider("⏱ Frecuencia de actualización (seg)", 1, 10, 2)

# --- CONTROL MANUAL ---
st.subheader("Control Manual de Salidas (Escritura)")
cols_ctrl = st.columns(N_COILS)

for i in range(N_COILS):
    with cols_ctrl[i]:
        if st.button(f"ON Q{i}", key=f"on_{i}"):
            escribir_salida_manual(i, True)
        if st.button(f"OFF Q{i}", key=f"off_{i}"):
            escribir_salida_manual(i, False)

# --- ESTADO ACTUAL ---
st.subheader("Estado Actual de Salidas (Lectura)")
estado = leer_estado_actual()

if estado:
    cols = st.columns(len(estado))
    for i, val in enumerate(estado):
        color = "🟢" if val else "🔴"
        cols[i].markdown(f"**Q{i}** {color}")
else:
    st.error("No se pudo leer el estado actual del servidor Modbus.")

# --- HISTÓRICO ---
st.subheader("Gráfico Histórico de las Salidas")
df = leer_registro()
if df is not None:
    st.line_chart(df.drop(columns=["timestamp"], errors="ignore"))
else:
    st.info("Aún no hay registros para mostrar.")

# --- AUTO-REFRESCO ---
st.markdown(f"Actualizando automáticamente cada {refresh_rate} segundos...")
time.sleep(refresh_rate)
st.rerun()

