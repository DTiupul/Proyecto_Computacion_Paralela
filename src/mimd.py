"""Procesamiento multihilo MIMD por etapas.

El dataset se divide en 3 partes y cada hilo aplica una instruccion
distinta sobre su propio bloque de datos.
"""

import csv
import threading
import time

import mysql.connector

from conexion import conectar_mysql
from rutas import RUTA_DATASET

# ==========================================
# MIMD: Multiple Instruction, Multiple Data
# ==========================================
# El dataset se divide en 3 partes iguales y cada hilo ejecuta una
# instruccion distinta sobre su propio trozo de datos:
#
#   Hilo 1 -> Parte 1 -> IMC = peso / estatura^2
#   Hilo 2 -> Parte 2 -> Relacion S/F = spo2 / fio2
#   Hilo 3 -> Parte 3 -> Ventilacion = volumen corriente * frecuencia respiratoria
#
# Los resultados parciales se guardan en la tabla calculo_mimd_etapas
# (una fila por paciente y etapa) para no mezclarlos con calculo_simd,
# calculo_misd ni con la tabla calculo_mimd existente.

# ==========================================
# 1. CARGA DEL DATASET
# ==========================================

id = []
genero = []
edad = []
practica_ejercicio = []
peso_kg = []
estatura_m = []
spo2_pct = []
fio2 = []
volumen_corriente_ml = []
frecuencia_respiratoria_rpm = []

with open(RUTA_DATASET, "r", encoding="utf-8-sig", newline="") as archivo:
    lector = csv.reader(archivo)
    next(lector)  # Para saltarse los encabezados

    for fila in lector:
        id.append(int(fila[0]))
        genero.append(int(fila[1]))
        edad.append(int(fila[2]))
        practica_ejercicio.append(int(fila[3]))
        peso_kg.append(float(fila[4]))
        estatura_m.append(float(fila[5]))
        spo2_pct.append(float(fila[6]))
        fio2.append(float(fila[7]))
        volumen_corriente_ml.append(int(fila[8]))
        frecuencia_respiratoria_rpm.append(int(fila[9]))

    print("Dataset cargado correctamente")
    print(f"Numero de elementos cargados en el dataset {len(id)}")


# ==========================================
# 2. DISTRIBUCION DEL DATASET EN 3 PARTES IGUALES
# ==========================================

total_registros = len(id)
tamano_parte = total_registros // 3

# Si el total no fuera divisible entre 3, el ultimo trozo absorbe el resto
inicio_parte_1 = 0
fin_parte_1 = tamano_parte
inicio_parte_2 = fin_parte_1
fin_parte_2 = inicio_parte_2 + tamano_parte
inicio_parte_3 = fin_parte_2
fin_parte_3 = total_registros

print("\nDistribucion del dataset en 3 partes:")
print(f"  Parte 1: indices {inicio_parte_1} a {fin_parte_1 - 1} "
      f"({fin_parte_1 - inicio_parte_1} registros) -> IMC")
print(f"  Parte 2: indices {inicio_parte_2} a {fin_parte_2 - 1} "
      f"({fin_parte_2 - inicio_parte_2} registros) -> Relacion S/F")
print(f"  Parte 3: indices {inicio_parte_3} a {fin_parte_3 - 1} "
      f"({fin_parte_3 - inicio_parte_3} registros) -> Ventilacion por minuto")


# ==========================================
# 3. VECTORES DE RESULTADOS
# ==========================================

imc = [0.0] * total_registros
relacion_sf = [0.0] * total_registros
ventilacion_ml_min = [0.0] * total_registros
ventilacion_l_min = [0.0] * total_registros

# Tiempo de cada instruccion, medido dentro de su propio hilo
tiempos = {}


# ==========================================
# 4. INSTRUCCIONES (una distinta por hilo)
# ==========================================

def calcular_imc(inicio, fin):
    """Parte 1: IMC = peso (kg) / estatura (m) ^ 2"""
    inicio_ns = time.perf_counter_ns()

    for i in range(inicio, fin):
        imc[i] = peso_kg[i] / (estatura_m[i] ** 2)

    tiempos["IMC"] = (time.perf_counter_ns() - inicio_ns) / 1000  # microsegundos


def calcular_relacion_sf(inicio, fin):
    """Parte 2: Relacion S/F = spo2 (%) / fio2"""
    inicio_ns = time.perf_counter_ns()

    for i in range(inicio, fin):
        relacion_sf[i] = spo2_pct[i] / fio2[i]

    tiempos["RELACION_SF"] = (time.perf_counter_ns() - inicio_ns) / 1000  # microsegundos


def calcular_ventilacion(inicio, fin):
    """Parte 3: Ventilacion (ml/min) y su conversion a (L/min)"""
    inicio_ns = time.perf_counter_ns()

    for i in range(inicio, fin):
        ventilacion_ml_min[i] = volumen_corriente_ml[i] * frecuencia_respiratoria_rpm[i]

    for i in range(inicio, fin):
        ventilacion_l_min[i] = ventilacion_ml_min[i] / 1000

    tiempos["VENTILACION"] = (time.perf_counter_ns() - inicio_ns) / 1000  # microsegundos


# ==========================================
# 5. EJECUCION MIMD (3 hilos, 3 instrucciones, 3 trozos)
# ==========================================

h1 = threading.Thread(target=calcular_imc, args=(inicio_parte_1, fin_parte_1))
h2 = threading.Thread(target=calcular_relacion_sf, args=(inicio_parte_2, fin_parte_2))
h3 = threading.Thread(target=calcular_ventilacion, args=(inicio_parte_3, fin_parte_3))

inicio = time.perf_counter_ns()

h1.start()
h2.start()
h3.start()

h1.join()
h2.join()
h3.join()

fin = time.perf_counter_ns()
tiempo_total = (fin - inicio) / 1000  # microsegundos


# ==========================================
# 6. RESULTADOS POR PANTALLA
# ==========================================

print("\n================ PARTE 1: IMC ================")
for i in range(inicio_parte_1, min(inicio_parte_1 + 3, fin_parte_1)):
    print("Registro:", id[i])
    print("  Peso (kg):", peso_kg[i])
    print("  Estatura (m):", estatura_m[i])
    print(f"  IMC: {imc[i]:.2f}")

print("\n================ PARTE 2: RELACION S/F ================")
for i in range(inicio_parte_2, min(inicio_parte_2 + 3, fin_parte_2)):
    print("Registro:", id[i])
    print("  SpO2 (%):", spo2_pct[i])
    print("  FiO2:", fio2[i])
    print(f"  Relacion S/F: {relacion_sf[i]:.2f}")

print("\n================ PARTE 3: VENTILACION ================")
for i in range(inicio_parte_3, min(inicio_parte_3 + 3, fin_parte_3)):
    print("Registro:", id[i])
    print("  Volumen corriente (ml):", volumen_corriente_ml[i])
    print("  Frecuencia respiratoria (rpm):", frecuencia_respiratoria_rpm[i])
    print(f"  Ventilacion: {ventilacion_ml_min[i]:.0f} ml/min "
          f"({ventilacion_l_min[i]:.2f} L/min)")

print("\n--------------------------")
print("Primer registro:", id[0])
print("Ultimo registro:", id[-1])
print("Total registros:", total_registros)

print("\n--------------------------")
print("Tiempo por instruccion (medido en cada hilo):")
print(f"  IMC: {tiempos['IMC']:.4f} microsegundos")
print(f"  Relacion S/F: {tiempos['RELACION_SF']:.4f} microsegundos")
print(f"  Ventilacion: {tiempos['VENTILACION']:.4f} microsegundos")
print(f"Tiempo total MIMD (los 3 hilos en paralelo): {tiempo_total:.4f} microsegundos")


# ==========================================
# 7. GUARDAR EN MYSQL
# ==========================================

conexion = None
cursor = None

try:
    conexion = conectar_mysql()
    cursor = conexion.cursor()

    print("Conexion exitosa a la base de datos MySQL")

    # Tabla propia de esta practica: una fila por paciente y etapa,
    # con la FK paciente_id -> datos_fisiologicos.id.
    sql_crear_tabla = """
        CREATE TABLE IF NOT EXISTS calculo_mimd_etapas (
            id INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
            paciente_id INT(10) UNSIGNED NOT NULL,
            etapa VARCHAR(20) NOT NULL,
            imc DECIMAL(5,2) NULL,
            relacion_sf DECIMAL(7,2) NULL,
            ventilacion_ml_min INT(10) UNSIGNED NULL,
            ventilacion_l_min DECIMAL(6,2) NULL,
            tiempo_microsegundos DOUBLE NOT NULL,
            fecha_procesamiento TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_mimd_etapa_paciente (paciente_id, etapa),
            CONSTRAINT fk_mimd_etapa_paciente FOREIGN KEY (paciente_id)
                REFERENCES datos_fisiologicos (id)
        ) ENGINE=InnoDB
    """
    cursor.execute(sql_crear_tabla)

    sql_mimd = '''
        INSERT INTO calculo_mimd_etapas (
            paciente_id,
            etapa,
            imc,
            relacion_sf,
            ventilacion_ml_min,
            ventilacion_l_min,
            tiempo_microsegundos
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            imc = VALUES(imc),
            relacion_sf = VALUES(relacion_sf),
            ventilacion_ml_min = VALUES(ventilacion_ml_min),
            ventilacion_l_min = VALUES(ventilacion_l_min),
            tiempo_microsegundos = VALUES(tiempo_microsegundos),
            fecha_procesamiento = CURRENT_TIMESTAMP

    '''

    # Parte 1: solo IMC
    for i in range(inicio_parte_1, fin_parte_1):
        cursor.execute(
            sql_mimd,
            (id[i], "IMC", imc[i], None, None, None, tiempos["IMC"])
        )

    # Parte 2: solo relacion S/F
    for i in range(inicio_parte_2, fin_parte_2):
        cursor.execute(
            sql_mimd,
            (id[i], "RELACION_SF", None, relacion_sf[i], None, None,
             tiempos["RELACION_SF"])
        )

    # Parte 3: solo ventilacion minuto
    for i in range(inicio_parte_3, fin_parte_3):
        cursor.execute(
            sql_mimd,
            (id[i], "VENTILACION", None, None, ventilacion_ml_min[i],
             ventilacion_l_min[i], tiempos["VENTILACION"])
        )

    conexion.commit()

    print("\nDATOS GUARDADOS CORRECTAMENTE")
    print(f"REGISTROS EN calculo_mimd_etapas: {total_registros}")
    print(f"  Etapa IMC: {fin_parte_1 - inicio_parte_1}")
    print(f"  Etapa RELACION_SF: {fin_parte_2 - inicio_parte_2}")
    print(f"  Etapa VENTILACION: {fin_parte_3 - inicio_parte_3}")

except mysql.connector.Error as error:
    if conexion is not None and conexion.is_connected():
        conexion.rollback()

    print(f"Error al guardar los datos en MySQL: {error}")

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
