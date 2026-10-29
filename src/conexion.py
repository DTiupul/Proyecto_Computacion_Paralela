"""Conexion compartida a la base de datos MySQL del proyecto."""

import mysql.connector


def conectar_mysql():
    """Devuelve una conexion abierta a la base de datos proyecto_paralela."""
    conexion = mysql.connector.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        database="proyecto_paralela"
    )
    return conexion


if __name__ == "__main__":
    try:
        conexion = conectar_mysql()
        if conexion.is_connected():
            print("Conexion exitosa a la base de datos MySQL")
            print("Base de datos proyecto_paralela")
            conexion.close()
    except mysql.connector.Error as error:
        print(f"Error al conectar a la base de datos {error}")
