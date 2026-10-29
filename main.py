import csv
import time

from conexion import conectar_mysql
import mysql.connector

id = []
peso_kg = []
estatura_m = []

with open('dataset_5001.csv', 'r', encoding="utf-8-sig", newline="") as archivo:
    lector = csv.reader(archivo)
    next(lector)  # Saltar los encabezados

    for fila in lector:
        id.append(int(fila[0]))
        peso_kg.append(float(fila[4]))
        estatura_m.append(float(fila[5]))

    print("Dataset cargado correctamente")
    print("Numero de elementos cargados en el dataset:", len(id))

imc = [0.0] * len(id)


def calcular_imc():
    for i in range(len(id)):
        imc[i] = round(peso_kg[i] / (estatura_m[i] * estatura_m[i]), 2)


inicio = time.perf_counter_ns()

# Unico flujo de procesamiento SIMD
calcular_imc()

fin = time.perf_counter_ns()
tiempo = (fin - inicio) / 1000  # Convertir a microsegundos

for i in range(len(id)):
    print("\n--------------------------------")
    print("REGISTRO:", id[i])
    print("PESO (KG):", peso_kg[i])
    print("ESTATURA (M):", estatura_m[i])
    print("IMC:", imc[i])

print("PRIMER REGISTRO:", id[0])
print("ULTIMO REGISTRO:", id[-1])
print("TOTAL REGISTROS:", len(id))

print("\n--------------------")
print(f"TIEMPO: {tiempo:.4f} us")

# "conectar a mysql y guardar en la base de datos"

conexion = None
cursor = None

try:
    conexion = conectar_mysql()
    cursor = conexion.cursor()

    print("Conexion exitosa a la base de datos MySQL")

    sql_resultado = """
        INSERT INTO calculo_simd
        (paciente_id, imc, tiempo_microsegundos)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            imc = VALUES(imc),
            tiempo_microsegundos = VALUES(tiempo_microsegundos),
            fecha_procesamiento = CURRENT_TIMESTAMP
    """

    for i in range(len(id)):
        cursor.execute(
            sql_resultado,
            (id[i], imc[i], tiempo)
        )

    conexion.commit()

    print("DATOS GUARDADOS CORRECTAMENTE")
    print("\nREGISTROS GUARDADOS:", len(id))

except mysql.connector.Error as error:
    if conexion is not None and conexion.is_connected():
        conexion.rollback()

    print(f"Error al guardar los datos en la base de datos: {error}")

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
