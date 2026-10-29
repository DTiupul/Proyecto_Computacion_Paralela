"""Procesamiento multihilo MISD.

Cuatro hilos aplican una instruccion distinta sobre el mismo dataset
completo y guardan los resultados en MySQL.
"""

import csv
import threading
import time

import mysql.connector

from conexion import conectar_mysql
from rutas import RUTA_DATASET

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
    next(lector)  # Saltar los encabezados

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
# 2. VECTORES DE RESULTADOS
# ==========================================

imc = [0.0] * len(id)
relacion_sf = [0.0] * len(id)
ventilacion_ml_min = [0.0] * len(id)
ventilacion_l_min = [0.0] * len(id)


# ==========================================
# 3. INSTRUCCIONES (una distinta por hilo)
# ==========================================

def calcular_imc():
    for i in range(len(id)):
        imc[i] = peso_kg[i] / (estatura_m[i] ** 2)


def calcular_relacion_sf():
    for i in range(len(id)):
        relacion_sf[i] = spo2_pct[i] / fio2[i]


def calcular_ventilacion_ml_min():
    for i in range(len(id)):
        ventilacion_ml_min[i] = volumen_corriente_ml[i] * frecuencia_respiratoria_rpm[i]


def convertir_ventilacion_ml_a_ventilacion_l():
    for i in range(len(ventilacion_ml_min)):
        ventilacion_l_min[i] = ventilacion_ml_min[i] / 1000


# ==========================================
# 4. EJECUCION MISD (4 hilos, mismo dataset)
# ==========================================

h1 = threading.Thread(target=calcular_imc)
h2 = threading.Thread(target=calcular_relacion_sf)
h3 = threading.Thread(target=calcular_ventilacion_ml_min)
h4 = threading.Thread(target=convertir_ventilacion_ml_a_ventilacion_l)

inicio = time.perf_counter_ns()

h1.start()
h2.start()
h3.start()
h4.start()

h1.join()
h2.join()
h3.join()
h4.join()

fin = time.perf_counter_ns()
tiempo = (fin - inicio) / 1000  # Convertir a microsegundos


# ==========================================
# 5. RESULTADOS POR PANTALLA
# ==========================================

for i in range(len(id)):
    print("\n----------------------\n")
    print("Registro: ", id[i])
    print("Peso (kg): ", peso_kg[i])
    print("Estatura (m): ", estatura_m[i])
    print("IMC peso (kg) / (estatura (m) ^ 2): ", imc[i])

print("\n--------------------------")
print("Primer registro: ", id[0])
print("Ultimo registro: ", id[-1])
print("Total registros: ", len(id))

print("\n--------------------------")
print(f"Tiempo: {tiempo:.4f} microsegundos")


# ==========================================
# 6. GUARDAR EN MYSQL
# ==========================================

conexion = None
cursor = None

try:
    conexion = conectar_mysql()
    cursor = conexion.cursor()

    print("Conexion exitosa a la base de datos MySQL")

    datos_fisiologicos = """
        INSERT INTO datos_fisiologicos (
            id,
            genero,
            edad,
            practica_ejercicio,
            peso_kg,
            estatura_m,
            spo2_pct,
            fio2,
            volumen_corriente_ml,
            frecuencia_respiratoria_rpm
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            genero = VALUES(genero),
            edad = VALUES(edad),
            practica_ejercicio = VALUES(practica_ejercicio),
            peso_kg = VALUES(peso_kg),
            estatura_m = VALUES(estatura_m),
            spo2_pct = VALUES(spo2_pct),
            fio2 = VALUES(fio2),
            volumen_corriente_ml = VALUES(volumen_corriente_ml),
            frecuencia_respiratoria_rpm = VALUES(frecuencia_respiratoria_rpm)
    """

    sql_misd = """
        INSERT INTO calculo_misd(
            paciente_id,
            imc,
            relacion_sf,
            ventilacion_ml_min,
            ventilacion_l_min,
            tiempo_microsegundos
        )
        VALUES(%s, %s, %s, %s, %s, %s)
    """

    for i in range(len(id)):
        cursor.execute(
            datos_fisiologicos,
            (
                id[i],
                genero[i],
                edad[i],
                practica_ejercicio[i],
                peso_kg[i],
                estatura_m[i],
                spo2_pct[i],
                fio2[i],
                volumen_corriente_ml[i],
                frecuencia_respiratoria_rpm[i]
            )
        )

        cursor.execute(
            sql_misd,
            (
                id[i],
                imc[i],
                relacion_sf[i],
                ventilacion_ml_min[i],
                ventilacion_l_min[i],
                tiempo
            )
        )

    conexion.commit()

    print("DATOS GUARDADOS CORRECTAMENTE")
    print("REGISTROS PROCESADOS: ", len(id))

except mysql.connector.Error as error:
    if conexion is not None and conexion.is_connected():
        conexion.rollback()

    print(f"Error al guardar los datos en MySQL: {error}")

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
