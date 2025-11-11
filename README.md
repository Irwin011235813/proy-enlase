# Proyecto Puente Modbus SCADA
Añadir README
Este repositorio contiene el código fuente y los scripts para un sistema de adquisición y control de datos (SCADA) básico, utilizando el protocolo Modbus para la comunicación. El proyecto simula un puente Modbus y visualiza datos en un dashboard local.

## Archivos Principales

*   `cliente_modbus.py`: Script que actúa como cliente Modbus, solicitando datos al servidor.
*   `dashboard_modbus.py`: Script para la visualización de datos en un panel de control (dashboard).
*   `theoretical_modbus_bridge.py`: Implementación teórica o de simulación del puente Modbus.
*   `registro_datos.csv`: Archivo CSV utilizado para almacenar los datos adquiridos.

## Requisitos

Para ejecutar este proyecto, necesitarás Python 3.x y las siguientes librerías:

*   `pymodbus`
*   `pandas` (para el manejo del CSV)
*   `matplotlib` o similar (si el dashboard usa visualización gráfica)

Puedes instalar los requisitos usando `pip install <nombre_de_la_libreria>`.

## Uso

1. Iniciar el servidor/puente teórico (`theoretical_modbus_bridge.py`).
2. Iniciar el cliente (`cliente_modbus.py`) para interactuar y registrar datos.
3. Ejecutar el dashboard (`dashboard_modbus.py`) para visualizar los resultados.

