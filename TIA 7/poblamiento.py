import time
import sys
import re
import random
import pandas as pd
import psycopg2
from psycopg2 import Error
import csv
from datetime import datetime, timedelta
import numpy as np

# Variables globales
error_con = False
id_pais = 57  # codigo ISO Colombia

# Parámetros de conexión de la Base de datos local
v_host = "localhost"
v_port = "5432"
v_database = "monitoreo_produccion"
v_user = "postgres"
v_password = "jeshua30"

#-----------------------------------------------------------------------------
# Clase para generar datos aleatorios de sensores
#-----------------------------------------------------------------------------
class GeneradorDatosSensores:
    
    def __init__(self):
        self.estados_alarma = ['normal', 'advertencia', 'crítica']
        self.sensores_disponibles = ['S01', 'S02', 'S03', 'S04']
        self.lineas_produccion = [1, 2, 3]
        self.usuarios_turno = ['turno1']  # Basado en el Excel actual
    
    def generar_ppm_benceno(self):
        """Genera valores de PPM de benceno realistas"""
        # Valores típicos de benceno en ambiente industrial (0.1 - 5.0 ppm)
        return round(random.uniform(0.1, 5.0), 2)
    
    def generar_fecha_hora_formato(self, fecha_inicio, fecha_fin):
        """Genera una fecha y hora aleatoria en formato específico"""
        time_between = fecha_fin - fecha_inicio
        days_between = time_between.days
        random_days = random.randrange(days_between)
        random_seconds = random.randrange(24 * 60 * 60)
        
        fecha_aleatoria = fecha_inicio + timedelta(days=random_days, seconds=random_seconds)
        # Formato similar al Excel: fecha/hora
        return fecha_aleatoria.strftime("%d/%m/%Y %H:%M:%S")
    
    def generar_estado_alarma(self):
        """Genera un estado de alarma aleatorio con probabilidades ponderadas"""
        # Más probabilidad de estar 'normal'
        probabilidades = [0.6, 0.3, 0.1]  # normal, advertencia, crítica
        return np.random.choice(self.estados_alarma, p=probabilidades)
    
    def asignar_linea_por_sensor(self, sensor):
        """Asigna línea de producción basada en el sensor"""
        # Mapeo basado en el patrón del Excel
        mapeo_sensor_linea = {
            'S01': 1,
            'S02': 1, 
            'S03': 2,
            'S04': 3
        }
        return mapeo_sensor_linea.get(sensor, 1)

#-----------------------------------------------------------------------------
# Función: Conectar a la base de datos
#-----------------------------------------------------------------------------
def conectar_bd():
    """Establece conexión con la base de datos PostgreSQL"""
    global error_con
    try:
        connection = psycopg2.connect(
            host=v_host,
            port=v_port,
            database=v_database,
            user=v_user,
            password=v_password
        )
        print("Conexión exitosa a la base de datos PostgreSQL")
        error_con = False
        return connection
        
    except Error as e:
        print(f"Error al conectar a PostgreSQL: {e}")
        error_con = True
        return None

#-----------------------------------------------------------------------------
# Función: Insertar datos en la tabla lecturas (CORREGIDA)
#-----------------------------------------------------------------------------
def insertar_lecturas(connection, datos_lecturas):
    """Inserta los datos generados en la tabla lecturas"""
    try:
        cursor = connection.cursor()
        
        # Query de inserción actualizada para incluir id_nivel
        insert_query = """
        INSERT INTO lecturas (
            fecha_hora, concentracion_ppm, id_sensor, estado_lectura, 
            id_turno, observaciones, id_nivel
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        # Preparar datos para inserción (mapear estructura Excel a BD)
        datos_para_insercion = []
        for dato in datos_lecturas:
            # Convertir fecha_hora de string a datetime para la BD
            fecha_hora_dt = datetime.strptime(dato[1], "%d/%m/%Y %H:%M:%S")
            
            # Mapear estado_alarma a estado_lectura
            estado_mapping = {
                'normal': 'NORMAL',
                'advertencia': 'ANOMALIA',
                'crítica': 'ANOMALIA'
            }
            estado_bd = estado_mapping.get(dato[4], 'NORMAL')
            
            # Convertir id_sensor de formato S01 a número entero
            sensor_mapping = {
                'S01': 1,
                'S02': 2,
                'S03': 3,
                'S04': 4
            }
            id_sensor_numerico = sensor_mapping.get(dato[3], 1)
            
            # Mapear usuario_turno a id_turno (extraer número)
            turno_numero = 1  # default
            if 'turno' in dato[6].lower():
                try:
                    turno_numero = int(dato[6].lower().replace('turno', ''))
                except:
                    turno_numero = 1
            
            # Determinar id_nivel basado en el estado de alarma
            nivel_mapping = {
                'normal': 1,      # Nivel normal
                'advertencia': 2, # Nivel de advertencia
                'crítica': 3      # Nivel crítico
            }
            id_nivel = nivel_mapping.get(dato[4], 1)
            
            datos_para_insercion.append((
                fecha_hora_dt,                    # fecha_hora
                dato[2],                         # concentracion_ppm (era ppm_benceno)
                id_sensor_numerico,              # id_sensor (convertido a entero)
                estado_bd,                       # estado_lectura (mapeado de estado_alarma)
                turno_numero,                    # id_turno (extraído de usuario_turno)
                f"Línea {dato[5]} - {dato[4]}",  # observaciones (combinando línea y estado)
                id_nivel                         # id_nivel (basado en estado_alarma)
            ))
        
        # Insertar datos en lotes
        cursor.executemany(insert_query, datos_para_insercion)
        connection.commit()
        
        print(f"Se insertaron {len(datos_para_insercion)} registros en la tabla lecturas")
        cursor.close()
        return True
        
    except Error as e:
        print(f"Error al insertar datos: {e}")
        connection.rollback()
        return False

#-----------------------------------------------------------------------------
# Función: Exportar datos a Excel
#-----------------------------------------------------------------------------
def exportar_a_excel(datos, nombre_archivo="lecturas-sensor.xlsx"):
    """Exporta los datos a una hoja de Excel con el formato exacto"""
    try:
        # Crear DataFrame con las columnas exactas del Excel
        columnas = [
            'id_lectura', 'fecha_hora', 'ppm_benceno', 'id_sensor',
            'estado_alarma', 'id_line_produccion', 'usuario_turno'
        ]
        
        df = pd.DataFrame(datos, columns=columnas)
        
        # Exportar a Excel con formato
        with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Lecturas_Sensores', index=False)
            
            # Obtener la hoja para formatear
            worksheet = writer.sheets['Lecturas_Sensores']
            
            # Ajustar ancho de columnas específicamente
            column_widths = {
                'A': 12,  # id_lectura
                'B': 20,  # fecha_hora
                'C': 15,  # ppm_benceno
                'D': 12,  # id_sensor
                'E': 15,  # estado_alarma
                'F': 18,  # id_line_produccion
                'G': 15   # usuario_turno
            }
            
            for col, width in column_widths.items():
                worksheet.column_dimensions[col].width = width
        
        print(f"Datos exportados exitosamente a {nombre_archivo}")
        return True
        
    except Exception as e:
        print(f"Error al exportar a Excel: {e}")
        return False

#-----------------------------------------------------------------------------
# Función principal: Generar y poblar datos
#-----------------------------------------------------------------------------
def generar_datos_sensores(num_registros=20, exportar_excel=True, id_inicial=1):
    """Función principal que genera y guarda los datos de sensores"""
    
    print(f"Iniciando generación de {num_registros} registros de lecturas...")
    
    # Crear instancia del generador
    generador = GeneradorDatosSensores()
    
    # Definir rango de fechas (último mes)
    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=30)
    
    # Generar datos aleatorios
    datos_lecturas = []
    
    for i in range(num_registros):
        # Seleccionar sensor aleatorio
        sensor_seleccionado = random.choice(generador.sensores_disponibles)
        
        # Generar registro con estructura exacta del Excel
        registro = (
            id_inicial + i,                                                    # id_lectura
            generador.generar_fecha_hora_formato(fecha_inicio, fecha_fin),     # fecha_hora
            generador.generar_ppm_benceno(),                                   # ppm_benceno
            sensor_seleccionado,                                               # id_sensor
            generador.generar_estado_alarma(),                                 # estado_alarma
            generador.asignar_linea_por_sensor(sensor_seleccionado),          # id_line_produccion
            random.choice(generador.usuarios_turno)                           # usuario_turno
        )
        datos_lecturas.append(registro)
    
    print(f"Datos generados exitosamente: {len(datos_lecturas)} registros")
    
    # Conectar a la base de datos e insertar datos
    connection = conectar_bd()
    
    if connection and not error_con:
        exito_insercion = insertar_lecturas(connection, datos_lecturas)
        
        if exito_insercion:
            print("✓ Datos insertados correctamente en la base de datos")
        else:
            print("✗ Error al insertar datos en la base de datos")
        
        connection.close()
    else:
        print("✗ No se pudo conectar a la base de datos")
        print("ℹ️  Los datos se exportarán solo a Excel")
    
    # Exportar a Excel si se solicita
    if exportar_excel:
        exito_excel = exportar_a_excel(datos_lecturas)
        if exito_excel:
            print("✓ Datos exportados correctamente a Excel")
        else:
            print("✗ Error al exportar datos a Excel")
    
    return datos_lecturas

#-----------------------------------------------------------------------------
# Función: Mostrar estadísticas de los datos generados
#-----------------------------------------------------------------------------
def mostrar_estadisticas(datos):
    """Muestra estadísticas básicas de los datos generados"""
    if not datos:
        print("No hay datos para mostrar estadísticas")
        return
    
    df = pd.DataFrame(datos, columns=[
        'id_lectura', 'fecha_hora', 'ppm_benceno', 'id_sensor',
        'estado_alarma', 'id_line_produccion', 'usuario_turno'
    ])
    
    print("\n" + "="*60)
    print("ESTADÍSTICAS DE LOS DATOS GENERADOS")
    print("="*60)
    print(f"Total de registros: {len(datos)}")
    print(f"Sensores únicos: {df['id_sensor'].nunique()}")
    print(f"Estados de alarma únicos: {df['estado_alarma'].nunique()}")
    print(f"Líneas de producción únicas: {df['id_line_produccion'].nunique()}")
    
    print("\nEstadísticas de PPM Benceno:")
    print("-" * 40)
    print(f"Mínimo: {df['ppm_benceno'].min():.2f} ppm")
    print(f"Máximo: {df['ppm_benceno'].max():.2f} ppm")
    print(f"Promedio: {df['ppm_benceno'].mean():.2f} ppm")
    print(f"Mediana: {df['ppm_benceno'].median():.2f} ppm")
    
    print("\nDistribución por sensores:")
    print("-" * 40)
    sensores_count = df['id_sensor'].value_counts()
    for sensor, count in sensores_count.items():
        porcentaje = (count / len(datos)) * 100
        print(f"{sensor}: {count} registros ({porcentaje:.1f}%)")
    
    print("\nDistribución de estados de alarma:")
    print("-" * 40)
    estados_count = df['estado_alarma'].value_counts()
    for estado, count in estados_count.items():
        porcentaje = (count / len(datos)) * 100
        print(f"{estado}: {count} registros ({porcentaje:.1f}%)")
    
    print("\nDistribución por líneas de producción:")
    print("-" * 40)
    lineas_count = df['id_line_produccion'].value_counts()
    for linea, count in lineas_count.items():
        porcentaje = (count / len(datos)) * 100
        print(f"Línea {linea}: {count} registros ({porcentaje:.1f}%)")

#-----------------------------------------------------------------------------
# Función para continuar numeración existente
#-----------------------------------------------------------------------------
def obtener_ultimo_id(connection):
    """Obtiene el último ID de lectura para continuar la numeración"""
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT MAX(id_lectura) FROM lecturas")
        resultado = cursor.fetchone()
        cursor.close()
        
        if resultado[0] is not None:
            return resultado[0] + 1
        else:
            return 1
            
    except Error as e:
        print(f"Error al obtener último ID: {e}")
        return 1

#-----------------------------------------------------------------------------
# Función principal de ejecución
#-----------------------------------------------------------------------------
def main():
    """Función principal del programa"""
    print("GENERADOR DE DATOS ALEATORIOS PARA SENSORES DE BENCENO")
    print("=" * 55)
    print("Estructura: id_lectura | fecha_hora | ppm_benceno | id_sensor | estado_alarma | id_line_produccion | usuario_turno")
    print("Sensores disponibles: S01, S02, S03, S04")
    print("Estados: normal, advertencia, crítica")
    print("-" * 55)
    
    try:
        # Solicitar número de registros al usuario
        while True:
            try:
                num_registros = int(input("Ingrese el número de registros a generar (default: 20): ") or "20")
                if num_registros > 0:
                    break
                else:
                    print("Por favor ingrese un número positivo")
            except ValueError:
                print("Por favor ingrese un número válido")
        
        # Preguntar si desea exportar a Excel
        exportar = input("¿Desea exportar los datos a Excel? (s/n, default: s): ").lower().strip() or "s"
        exportar_excel = exportar in ['s', 'si', 'sí', 'y', 'yes']
        
        # Determinar ID inicial
        connection = conectar_bd()
        id_inicial = 1
        if connection and not error_con:
            id_inicial = obtener_ultimo_id(connection)
            connection.close()
            print(f"ℹ️  La numeración continuará desde el ID: {id_inicial}")
        else:
            print("ℹ️  Se iniciará la numeración desde el ID: 1")
        
        # Generar los datos
        datos_generados = generar_datos_sensores(num_registros, exportar_excel, id_inicial)
        
        # Mostrar estadísticas
        mostrar_estadisticas(datos_generados)
        
        print("\n✓ Proceso completado exitosamente")
        print(f"📁 Archivo generado: lecturas-sensor.xlsx")
        
    except KeyboardInterrupt:
        print("\n\nProceso interrumpido por el usuario")
    except Exception as e:
        print(f"\nError inesperado: {e}")

#-----------------------------------------------------------------------------
# Punto de entrada del programa
#-----------------------------------------------------------------------------
if __name__ == "__main__":
    main()