"""
Dashboard interactivo de análisis fisiológico y comparación de arquitecturas
SIMD, MISD y MIMD.

Archivo independiente: NO modifica dashboard.py, el CSV original ni los datos
de MySQL. Todas las consultas a MySQL son SELECT (no se crean ni alteran tablas).
"""

import math

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from conexion import conectar_mysql

# ==========================================================
# 1. CONFIGURACIÓN Y CONSTANTES
# ==========================================================

st.set_page_config(
    page_title="Dashboard fisiológico SIMD · MISD · MIMD",
    page_icon="🫁",
    layout="wide",
)

ARCHIVO_CSV = "dataset_5001.csv"

# Columnas de entrada realmente presentes en dataset_5001.csv
COLUMNAS_CSV = [
    "id",
    "genero",
    "edad",
    "practica_ejercicio",
    "peso_kg",
    "estatura_m",
    "spo2_pct",
    "fio2",
    "volumen_corriente_ml",
    "frecuencia_respiratoria_rpm",
]

# Nombres esperados por el enunciado. Se resuelven sin distinguir mayúsculas
# contra la base real (en MySQL/Windows aparecen en minúsculas).
TABLAS_ESPERADAS = [
    "datos_fisiologicos",
    "calcular",
    "calculo_simd",
    "calculo_misd",
    "calculo_mimd",
    "calculo_mimd_etapas",
]

GENERO_MAP = {1: "Masculino", 0: "Femenino"}
EJERCICIO_MAP = {1: "Sí", 0: "No"}

COLOR_GENERO = {"Masculino": "#2E86DE", "Femenino": "#E84393", "Sin dato": "#95A5A6"}
COLOR_EJERCICIO = {"Sí": "#27AE60", "No": "#E67E22", "Sin dato": "#95A5A6"}
COLOR_ARQUITECTURA = {"SIMD": "#2E86DE", "MISD": "#27AE60", "MIMD": "#8E44AD"}

VARIABLES = [
    {"clave": "imc_calculado", "etiqueta": "IMC", "unidad": "kg/m²", "dec": 2},
    {
        "clave": "relacion_sf_calculada",
        "etiqueta": "Relación SpO₂/FiO₂",
        "unidad": "adimensional",
        "dec": 2,
    },
    {
        "clave": "ventilacion_ml_min_calculada",
        "etiqueta": "Ventilación por minuto",
        "unidad": "mL/min",
        "dec": 0,
    },
    {
        "clave": "ventilacion_l_min_calculada",
        "etiqueta": "Ventilación por minuto",
        "unidad": "L/min",
        "dec": 2,
    },
]

ETIQUETAS_NUMERICAS = {
    "edad": "Edad (años)",
    "peso_kg": "Peso (kg)",
    "estatura_m": "Estatura (m)",
    "imc_calculado": "IMC (kg/m²)",
    "spo2_pct": "SpO₂ (%)",
    "fio2": "FiO₂",
    "relacion_sf_calculada": "Relación SpO₂/FiO₂",
    "volumen_corriente_ml": "Vol. corriente (mL)",
    "frecuencia_respiratoria_rpm": "Frec. respiratoria (rpm)",
    "ventilacion_ml_min_calculada": "Ventilación (mL/min)",
    "ventilacion_l_min_calculada": "Ventilación (L/min)",
}

# ==========================================================
# 2. UTILIDADES
# ==========================================================


def fmt(valor, dec=2, sufijo=""):
    """Formatea un número mostrando '—' cuando no hay dato válido."""
    if valor is None:
        return "—"
    try:
        if pd.isna(valor):
            return "—"
    except (TypeError, ValueError):
        pass
    return f"{float(valor):,.{dec}f}{sufijo}"


def parse_ids(texto):
    """Extrae IDs enteros de un texto tipo '12, 45 900'. Devuelve (ids, invalidos)."""
    ids, invalidos = [], []
    for token in texto.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            invalidos.append(token)
    return ids, invalidos


def buscar_tabla(esquema, nombre):
    """Devuelve el nombre real de la tabla sin distinguir mayúsculas."""
    for tabla in esquema:
        if tabla.lower() == nombre.lower():
            return tabla
    return None


def consultar_dataframe(consulta):
    """Ejecuta un SELECT y devuelve un DataFrame. Cierra siempre cursor y conexión."""
    conexion = conectar_mysql()
    try:
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute(consulta)
            filas = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        if conexion.is_connected():
            conexion.close()
    return pd.DataFrame(filas)


def normalizar_resultados(df):
    """Convierte DECIMAL/TIMESTAMP de MySQL a tipos numéricos/fecha de pandas."""
    if df.empty:
        return df
    df = df.copy()
    for columna in [
        "id",
        "paciente_id",
        "imc",
        "relacion_sf",
        "ventilacion_ml_min",
        "ventilacion_l_min",
        "tiempo_microsegundos",
    ]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    if "fecha_procesamiento" in df.columns:
        df["fecha_procesamiento"] = pd.to_datetime(
            df["fecha_procesamiento"], errors="coerce"
        )
    return df


@st.cache_data(ttl=120, show_spinner="Leyendo estructura de MySQL...")
def cargar_esquema():
    """Devuelve ({tabla: [columnas]}, error)."""
    try:
        df = consultar_dataframe(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        esquema = {}
        for _, fila in df.iterrows():
            esquema.setdefault(fila["TABLE_NAME"], []).append(fila["COLUMN_NAME"])
        return esquema, None
    except Exception as error:  # conexión caída, permisos, etc.
        return {}, str(error)


@st.cache_data(ttl=120, show_spinner="Consultando MySQL...")
def cargar_tabla(nombre_real):
    """Lee una tabla completa. El nombre proviene de information_schema (whitelist)."""
    return normalizar_resultados(consultar_dataframe(f"SELECT * FROM `{nombre_real}`"))


def cargar_tablas(esquema):
    tablas, errores = {}, []
    for esperada in TABLAS_ESPERADAS:
        real = buscar_tabla(esquema, esperada)
        if not real:
            continue
        try:
            tablas[esperada] = cargar_tabla(real)
        except Exception as error:
            errores.append(f"{real}: {error}")
    return tablas, errores


@st.cache_data(ttl=120, show_spinner="Leyendo dataset_5001.csv...")
def cargar_csv():
    return pd.read_csv(ARCHIVO_CSV)


def preparar_entrada(df, origen):
    """Valida columnas, normaliza tipos y calcula las métricas fisiológicas."""
    faltantes = [c for c in COLUMNAS_CSV if c not in df.columns]
    if faltantes:
        raise ValueError(
            "Faltan columnas de entrada en la fuente de datos: " + ", ".join(faltantes)
        )

    df = df.copy()
    for columna in [
        "id",
        "genero",
        "edad",
        "practica_ejercicio",
        "peso_kg",
        "estatura_m",
        "spo2_pct",
        "fio2",
        "volumen_corriente_ml",
        "frecuencia_respiratoria_rpm",
    ]:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    df = df.dropna(subset=["id"]).copy()
    df["id"] = df["id"].astype("int64")
    df = df.drop_duplicates(subset="id", keep="last")

    # Métricas calculadas en el dashboard (el CSV no las trae).
    estatura = df["estatura_m"].where(df["estatura_m"] > 0)
    fio2 = df["fio2"].where(df["fio2"] > 0)
    df["imc_calculado"] = df["peso_kg"] / estatura.pow(2)
    df["relacion_sf_calculada"] = df["spo2_pct"] / fio2
    df["ventilacion_ml_min_calculada"] = (
        df["volumen_corriente_ml"] * df["frecuencia_respiratoria_rpm"]
    )
    df["ventilacion_l_min_calculada"] = df["ventilacion_ml_min_calculada"] / 1000

    df["genero_desc"] = df["genero"].map(GENERO_MAP).fillna("Sin dato")
    df["ejercicio_desc"] = df["practica_ejercicio"].map(EJERCICIO_MAP).fillna("Sin dato")
    df["fuente"] = origen
    return df


def agregar_resultados(base, tablas, avisos):
    """Une resultados MySQL a la base por la FK paciente_id, sin multiplicar filas."""
    df = base.copy()

    def ultimo_por_paciente(nombre):
        tabla = tablas[nombre].copy()
        duplicados = int(tabla["paciente_id"].duplicated().sum())
        tabla = tabla.sort_values("id").drop_duplicates("paciente_id", keep="last")
        if duplicados:
            avisos.append(
                f"`{nombre}` tenía {duplicados:,} filas repetidas por paciente; "
                "se usó la última (mayor id)."
            )
        return tabla

    if tablas.get("calculo_simd") is not None and not tablas["calculo_simd"].empty:
        simd = ultimo_por_paciente("calculo_simd").rename(
            columns={
                "paciente_id": "_pid",
                "imc": "imc_simd",
                "tiempo_microsegundos": "tiempo_simd_us",
                "fecha_procesamiento": "fecha_simd",
            }
        )
        df = df.merge(
            simd[["_pid", "imc_simd", "tiempo_simd_us", "fecha_simd"]],
            left_on="id",
            right_on="_pid",
            how="left",
        ).drop(columns="_pid")

    if tablas.get("calculo_misd") is not None and not tablas["calculo_misd"].empty:
        misd = ultimo_por_paciente("calculo_misd").rename(
            columns={
                "paciente_id": "_pid",
                "imc": "imc_misd",
                "relacion_sf": "relacion_sf_misd",
                "ventilacion_ml_min": "ventilacion_ml_min_misd",
                "ventilacion_l_min": "ventilacion_l_min_misd",
                "tiempo_microsegundos": "tiempo_misd_us",
                "fecha_procesamiento": "fecha_misd",
            }
        )
        df = df.merge(
            misd[
                [
                    "_pid",
                    "imc_misd",
                    "relacion_sf_misd",
                    "ventilacion_ml_min_misd",
                    "ventilacion_l_min_misd",
                    "tiempo_misd_us",
                    "fecha_misd",
                ]
            ],
            left_on="id",
            right_on="_pid",
            how="left",
        ).drop(columns="_pid")

    mimd = tablas.get("calculo_mimd_etapas")
    if mimd is not None and not mimd.empty:
        mimd = ultimo_por_paciente("calculo_mimd_etapas").rename(
            columns={
                "paciente_id": "_pid",
                "etapa": "mimd_etapa",
                "imc": "mimd_imc",
                "relacion_sf": "mimd_relacion_sf",
                "ventilacion_ml_min": "mimd_ventilacion_ml_min",
                "ventilacion_l_min": "mimd_ventilacion_l_min",
                "tiempo_microsegundos": "mimd_tiempo_us",
                "fecha_procesamiento": "fecha_mimd",
            }
        )
        # Cada paciente solo tiene valor en la columna de su etapa.
        mimd["mimd_resultado"] = (
            mimd[["mimd_imc", "mimd_relacion_sf", "mimd_ventilacion_ml_min"]]
            .bfill(axis=1)
            .iloc[:, 0]
        )
        df = df.merge(
            mimd[
                [
                    "_pid",
                    "mimd_etapa",
                    "mimd_resultado",
                    "mimd_imc",
                    "mimd_relacion_sf",
                    "mimd_ventilacion_ml_min",
                    "mimd_ventilacion_l_min",
                    "mimd_tiempo_us",
                    "fecha_mimd",
                ]
            ],
            left_on="id",
            right_on="_pid",
            how="left",
        ).drop(columns="_pid")
    elif tablas.get("calculo_mimd") is not None and not tablas["calculo_mimd"].empty:
        # Respaldo: tabla MIMD "completa" (una fila por paciente).
        mimd = ultimo_por_paciente("calculo_mimd").rename(
            columns={
                "paciente_id": "_pid",
                "imc": "mimd_imc",
                "relacion_sf": "mimd_relacion_sf",
                "ventilacion_ml_min": "mimd_ventilacion_ml_min",
                "ventilacion_l_min": "mimd_ventilacion_l_min",
                "tiempo_microsegundos": "mimd_tiempo_us",
                "fecha_procesamiento": "fecha_mimd",
            }
        )
        mimd["mimd_etapa"] = "COMPLETO"
        df = df.merge(
            mimd[
                [
                    "_pid",
                    "mimd_etapa",
                    "mimd_imc",
                    "mimd_relacion_sf",
                    "mimd_ventilacion_ml_min",
                    "mimd_ventilacion_l_min",
                    "mimd_tiempo_us",
                    "fecha_mimd",
                ]
            ],
            left_on="id",
            right_on="_pid",
            how="left",
        ).drop(columns="_pid")

    if len(df) != len(base):
        avisos.append(
            "La unión con resultados multiplicó filas; se conservó un registro por ID."
        )
        df = df.drop_duplicates(subset="id", keep="last")

    return df


def estadisticas_serie(serie):
    """Media, mediana, extremos y desviación estándar muestral (ddof=1)."""
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    return {
        "n": int(s.size),
        "media": float(s.mean()),
        "mediana": float(s.median()),
        "min": float(s.min()),
        "max": float(s.max()),
        "desv": float(s.std(ddof=1)) if s.size > 1 else float("nan"),
    }


def tabla_estadisticas(df):
    filas = []
    for variable in VARIABLES:
        estadisticas = estadisticas_serie(df[variable["clave"]])
        filas.append(
            {
                "Variable": variable["etiqueta"],
                "Unidad": variable["unidad"],
                "n válidos": estadisticas["n"],
                "Media": estadisticas.get("media"),
                "Mediana": estadisticas.get("mediana"),
                "Mínimo": estadisticas.get("min"),
                "Máximo": estadisticas.get("max"),
                "Desv. est.": estadisticas.get("desv"),
            }
        )
    return pd.DataFrame(filas)


def resumen_por_grupo(df, variables):
    filas = []
    for variable in variables:
        for codigo, grupo in [(0, "No"), (1, "Sí")]:
            subconjunto = df.loc[
                df["practica_ejercicio"] == codigo, variable["clave"]
            ].dropna()
            if subconjunto.empty:
                continue
            filas.append(
                {
                    "Variable": f"{variable['etiqueta']} ({variable['unidad']})",
                    "Unidad": variable["unidad"],
                    "Grupo": grupo,
                    "n": int(subconjunto.size),
                    "Media": float(subconjunto.mean()),
                    "Mediana": float(subconjunto.median()),
                    "Mínimo": float(subconjunto.min()),
                    "Máximo": float(subconjunto.max()),
                    "Desv. est.": (
                        float(subconjunto.std(ddof=1))
                        if subconjunto.size > 1
                        else float("nan")
                    ),
                }
            )
    return pd.DataFrame(filas)


def diferencias_entre_grupos(df, variables):
    filas = []
    for variable in variables:
        sin = df.loc[df["practica_ejercicio"] == 0, variable["clave"]].dropna()
        con = df.loc[df["practica_ejercicio"] == 1, variable["clave"]].dropna()
        if sin.empty or con.empty:
            continue
        media_sin, media_con = float(sin.mean()), float(con.mean())
        diferencia = media_con - media_sin
        porcentaje = (
            diferencia / abs(media_sin) * 100 if abs(media_sin) > 1e-9 else float("nan")
        )
        filas.append(
            {
                "Variable": variable["etiqueta"],
                "Unidad": variable["unidad"],
                "Media sin ejercicio": media_sin,
                "Media con ejercicio": media_con,
                "Diferencia (Sí − No)": diferencia,
                "Diferencia %": porcentaje,
            }
        )
    return pd.DataFrame(filas)


def valores_ejecucion(serie):
    """Tiempos distintos (redondeados a 4 decimales) = ejecuciones detectadas."""
    s = pd.to_numeric(serie, errors="coerce").dropna().round(4)
    if s.empty:
        return np.array([])
    return np.sort(s.unique())


# ==========================================================
# 3. COMPONENTES DE VISUALIZACIÓN
# ==========================================================


def histograma(serie, titulo, eje_x, color="#2E86DE"):
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        st.info("No hay datos válidos para graficar esta variable.")
        return
    temp = pd.DataFrame({"valor": s})
    fig = px.histogram(
        temp,
        x="valor",
        nbins=40,
        title=titulo,
        labels={"valor": eje_x, "count": "Cantidad de registros"},
        color_discrete_sequence=[color],
    )
    fig.update_layout(
        yaxis_title="Cantidad de registros", xaxis_title=eje_x, bargap=0.02
    )
    st.plotly_chart(fig, width="stretch")


def caja_simple(serie, titulo, eje_y, color="#2E86DE"):
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        st.info("No hay datos válidos para graficar esta variable.")
        return
    temp = pd.DataFrame({"valor": s})
    fig = px.box(
        temp,
        y="valor",
        points="outliers",
        title=titulo,
        labels={"valor": eje_y},
        color_discrete_sequence=[color],
    )
    fig.update_layout(yaxis_title=eje_y, xaxis_title="")
    st.plotly_chart(fig, width="stretch")


def caja_por_grupo(df, columna, grupo, titulo, eje_y, eje_x, color_map):
    datos = df[[columna, grupo]].dropna()
    if datos.empty:
        st.info("No hay datos válidos para comparar los grupos.")
        return
    fig = px.box(
        datos,
        x=grupo,
        y=columna,
        color=grupo,
        points="outliers",
        title=titulo,
        labels={columna: eje_y, grupo: eje_x},
        color_discrete_map=color_map,
    )
    fig.update_layout(showlegend=False, yaxis_title=eje_y, xaxis_title=eje_x)
    st.plotly_chart(fig, width="stretch")


def barras_grupo(resumen_variable, titulo, eje_y, color_map):
    if resumen_variable.empty:
        st.info("No hay datos válidos para comparar los grupos.")
        return
    fig = px.bar(
        resumen_variable,
        x="Grupo",
        y="Media",
        color="Grupo",
        error_y="Desv. est.",
        text_auto=".2f",
        title=titulo,
        labels={
            "Media": eje_y,
            "Grupo": "Practica ejercicio",
            "Desv. est.": "Desviación estándar",
        },
        color_discrete_map=color_map,
    )
    fig.update_layout(showlegend=False, yaxis_title=eje_y, xaxis_title="Practica ejercicio")
    st.plotly_chart(fig, width="stretch")


def configuracion_numerica(mapa):
    """Mapa {columna: format} -> column_config de Streamlit."""
    return {
        columna: st.column_config.NumberColumn(format=formato)
        for columna, formato in mapa.items()
    }


def tabla_estado_tablas(esquema, tablas):
    filas = []
    for esperada in TABLAS_ESPERADAS:
        real = buscar_tabla(esquema, esperada)
        if real:
            df = tablas.get(esperada)
            filas.append(
                {
                    "Tabla esperada": esperada,
                    "Estado": "Disponible",
                    "Nombre real": real,
                    "Filas": 0 if df is None else len(df),
                    "Columnas": ", ".join(esquema.get(real, [])),
                }
            )
        else:
            filas.append(
                {
                    "Tabla esperada": esperada,
                    "Estado": "No existe",
                    "Nombre real": "—",
                    "Filas": 0,
                    "Columnas": "—",
                }
            )
    return pd.DataFrame(filas)


# ==========================================================
# 4. PESTAÑA 1: RESUMEN GENERAL
# ==========================================================


def render_resumen(ctx):
    datos = ctx["filtrado"]
    st.subheader("Indicadores generales")
    st.caption(
        f"Vista de datos: **{ctx['fuente_etiqueta']}** · "
        f"{len(datos):,} de {len(ctx['datos']):,} registros tras los filtros globales."
    )

    if datos.empty:
        st.warning("Los filtros globales no dejan registros. Ajusta los filtros del panel lateral.")
        return

    edad = estadisticas_serie(datos["edad"])
    imc = estadisticas_serie(datos["imc_calculado"])
    relacion = estadisticas_serie(datos["relacion_sf_calculada"])
    vent_ml = estadisticas_serie(datos["ventilacion_ml_min_calculada"])
    vent_l = estadisticas_serie(datos["ventilacion_l_min_calculada"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Registros disponibles",
        f"{len(datos):,}",
        help=f"Total en el dataset: {len(ctx['datos']):,}",
    )
    col2.metric(
        "Pacientes únicos",
        f"{datos['id'].nunique():,}",
        help="Conteo por ID distinto, sin duplicar pacientes entre tablas.",
    )
    col3.metric("Edad promedio", fmt(edad.get("media"), 2, " años"))
    col4.metric("IMC promedio", fmt(imc.get("media"), 2, " kg/m²"))

    col5, col6, col7 = st.columns(3)
    col5.metric("Relación SpO₂/FiO₂ promedio", fmt(relacion.get("media"), 2))
    col6.metric("Ventilación promedio", fmt(vent_ml.get("media"), 0, " mL/min"))
    col7.metric("Ventilación promedio", fmt(vent_l.get("media"), 2, " L/min"))

    st.markdown("#### Valores mínimo y máximo de las variables calculadas")
    filas = []
    for variable in VARIABLES:
        est = estadisticas_serie(datos[variable["clave"]])
        filas.append(
            {
                "Variable": variable["etiqueta"],
                "Unidad": variable["unidad"],
                "n válidos": est["n"],
                "Media": est.get("media"),
                "Mínimo": est.get("min"),
                "Máximo": est.get("max"),
            }
        )
    tabla = pd.DataFrame(filas)
    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config=configuracion_numerica(
            {
                "Media": "%.2f",
                "Mínimo": "%.2f",
                "Máximo": "%.2f",
            }
        ),
    )
    st.caption(
        "Promedios con dos decimales. IMC en kg/m², relación S/F adimensional y "
        "ventilación en mL/min y L/min. Valores calculados en el dashboard a partir "
        "de peso, estatura, SpO₂, FiO₂, volumen corriente y frecuencia respiratoria."
    )

    st.divider()

    columna_izq, columna_der = st.columns(2)

    with columna_izq:
        st.markdown("#### Cobertura de resultados almacenados")
        cobertura = []
        for arquitectura, columna, detalle in [
            ("SIMD", "imc_simd", "IMC"),
            ("MISD", "imc_misd", "IMC, relación S/F y ventilación"),
            ("MIMD", "mimd_resultado", "Una métrica distinta por etapa"),
        ]:
            if columna in datos.columns:
                disponibles = int(datos[columna].notna().sum())
                cobertura.append(
                    {
                        "Arquitectura": arquitectura,
                        "Pacientes con resultado": disponibles,
                        "Cobertura": disponibles / len(datos) * 100,
                        "Métricas": detalle,
                    }
                )
            else:
                cobertura.append(
                    {
                        "Arquitectura": arquitectura,
                        "Pacientes con resultado": 0,
                        "Cobertura": 0.0,
                        "Métricas": "No disponible",
                    }
                )
        st.dataframe(
            pd.DataFrame(cobertura),
            width="stretch",
            hide_index=True,
            column_config={
                "Pacientes con resultado": st.column_config.NumberColumn(format="%d"),
                "Cobertura": st.column_config.NumberColumn(format="%.2f %%"),
            },
        )
        st.caption(
            "MIMD reparte el dataset en tercios: cada paciente tiene resultado de una "
            "sola etapa (IMC, relación S/F o ventilación)."
        )

    with columna_der:
        st.markdown("#### Estado de las tablas en MySQL")
        st.dataframe(
            tabla_estado_tablas(ctx["esquema"], ctx["tablas"]),
            width="stretch",
            hide_index=True,
            column_config={
                "Filas": st.column_config.NumberColumn(format="%d"),
            },
        )
        if ctx["error_bd"]:
            st.error(f"MySQL no disponible: {ctx['error_bd']}")
        else:
            faltantes = [
                t
                for t in TABLAS_ESPERADAS
                if buscar_tabla(ctx["esquema"], t) is None
            ]
            if faltantes:
                st.warning(
                    "Tablas esperadas que no existen en esta base: "
                    + ", ".join(f"`{t}`" for t in faltantes)
                    + ". Las secciones que dependen de ellas se muestran como no disponibles."
                )
            if (
                "calculo_mimd" in faltantes
                and "calculo_mimd_etapas" not in faltantes
            ):
                st.info(
                    "Los resultados MIMD reales están en `calculo_mimd_etapas` "
                    "(una fila por paciente y etapa)."
                )

    st.divider()

    with st.expander("🔎 Control de calidad de los datos", expanded=False):
        filas = []
        if ctx["csv"] is not None:
            csv = ctx["csv"]
            filas.append(
                {
                    "Fuente": "CSV",
                    "Filas": len(csv),
                    "IDs únicos": csv["id"].nunique(),
                    "IDs duplicados": int(csv["id"].duplicated().sum()),
                    "Nulos en columnas de entrada": int(
                        csv[COLUMNAS_CSV].isna().sum().sum()
                    ),
                }
            )
        db = ctx["tablas"].get("datos_fisiologicos")
        if db is not None:
            filas.append(
                {
                    "Fuente": "datos_fisiologicos (MySQL)",
                    "Filas": len(db),
                    "IDs únicos": db["id"].nunique(),
                    "IDs duplicados": int(db["id"].duplicated().sum()),
                    "Nulos en columnas de entrada": int(
                        db[[c for c in COLUMNAS_CSV if c in db.columns]]
                        .isna()
                        .sum()
                        .sum()
                    ),
                }
            )
        if filas:
            st.dataframe(
                pd.DataFrame(filas),
                width="stretch",
                hide_index=True,
                column_config={
                    "Filas": st.column_config.NumberColumn(format="%d"),
                    "IDs únicos": st.column_config.NumberColumn(format="%d"),
                    "IDs duplicados": st.column_config.NumberColumn(format="%d"),
                    "Nulos en columnas de entrada": st.column_config.NumberColumn(
                        format="%d"
                    ),
                },
            )

        csv = ctx["csv"]
        db = ctx["tablas"].get("datos_fisiologicos")
        if csv is not None and db is not None:
            comparacion = csv.merge(db, on="id", how="outer", indicator=True)
            conteo = comparacion["_merge"].value_counts().to_dict()
            st.caption(
                "Cruce CSV ↔ `datos_fisiologicos`: "
                f"{conteo.get('both', 0):,} IDs en ambas fuentes, "
                f"{conteo.get('left_only', 0):,} solo en CSV, "
                f"{conteo.get('right_only', 0):,} solo en MySQL."
            )
            diferencias = []
            for columna in [
                "genero",
                "edad",
                "practica_ejercicio",
                "peso_kg",
                "estatura_m",
                "spo2_pct",
                "fio2",
                "volumen_corriente_ml",
                "frecuencia_respiratoria_rpm",
            ]:
                a = pd.to_numeric(comparacion.get(f"{columna}_x"), errors="coerce")
                b = pd.to_numeric(comparacion.get(f"{columna}_y"), errors="coerce")
                if a is not None and b is not None:
                    diferencias.append(
                        {
                            "Variable": columna,
                            "Diferencia máxima absoluta": float(
                                (a - b).abs().max()
                                if (a - b).abs().notna().any()
                                else 0.0
                            ),
                        }
                    )
            if diferencias:
                st.dataframe(
                    pd.DataFrame(diferencias),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Diferencia máxima absoluta": st.column_config.NumberColumn(
                            format="%.4f"
                        )
                    },
                )

        if ctx["tablas"]:
            ids_validos = set(ctx["datos"]["id"].tolist())
            filas = []
            for nombre, tabla in ctx["tablas"].items():
                if "paciente_id" not in tabla.columns:
                    continue
                filas.append(
                    {
                        "Tabla": nombre,
                        "Filas": len(tabla),
                        "Duplicados por paciente": int(
                            tabla["paciente_id"].duplicated().sum()
                        ),
                        "FK sin paciente": int(
                            (~tabla["paciente_id"].isin(ids_validos)).sum()
                        ),
                    }
                )
            if filas:
                st.dataframe(
                    pd.DataFrame(filas),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Filas": st.column_config.NumberColumn(format="%d"),
                        "Duplicados por paciente": st.column_config.NumberColumn(
                            format="%d"
                        ),
                        "FK sin paciente": st.column_config.NumberColumn(format="%d"),
                    },
                )

    with st.expander("✅ Verificación de fórmulas (dashboard vs MySQL)", expanded=False):
        filas = []

        def comparar(nombre, calculado, almacenado, tolerancia):
            pares = pd.DataFrame({"calculado": calculado, "almacenado": almacenado})
            pares = pares.dropna()
            if pares.empty:
                return
            diferencia = (pares["calculado"] - pares["almacenado"]).abs()
            filas.append(
                {
                    "Comparación": nombre,
                    "Pares comparados": len(pares),
                    "Diferencia máxima": float(diferencia.max()),
                    "Fuera de tolerancia": int((diferencia > tolerancia).sum()),
                }
            )

        if "imc_simd" in ctx["datos"].columns:
            comparar(
                "IMC dashboard vs calculo_simd.imc",
                ctx["datos"]["imc_calculado"],
                ctx["datos"]["imc_simd"],
                0.011,
            )
        for columna, etiqueta in [
            ("imc_misd", "IMC"),
            ("relacion_sf_misd", "Relación S/F"),
            ("ventilacion_ml_min_misd", "Ventilación (mL/min)"),
        ]:
            if columna in ctx["datos"].columns:
                calculada = {
                    "imc_misd": ctx["datos"]["imc_calculado"],
                    "relacion_sf_misd": ctx["datos"]["relacion_sf_calculada"],
                    "ventilacion_ml_min_misd": ctx["datos"][
                        "ventilacion_ml_min_calculada"
                    ],
                }[columna]
                comparar(
                    f"{etiqueta} dashboard vs calculo_misd",
                    calculada,
                    ctx["datos"][columna],
                    0.011 if "ventilacion" not in columna else 0.5,
                )
        if "mimd_resultado" in ctx["datos"].columns:
            sub = ctx["datos"].dropna(subset=["mimd_resultado"])
            if not sub.empty:
                calculada = pd.Series(
                    np.select(
                        [
                            sub["mimd_etapa"] == "IMC",
                            sub["mimd_etapa"] == "RELACION_SF",
                            sub["mimd_etapa"] == "VENTILACION",
                        ],
                        [
                            sub["imc_calculado"],
                            sub["relacion_sf_calculada"],
                            sub["ventilacion_ml_min_calculada"],
                        ],
                        default=np.nan,
                    ),
                    index=sub.index,
                )
                comparar(
                    "Etapa MIMD vs cálculo del dashboard",
                    calculada,
                    sub["mimd_resultado"],
                    0.5,
                )

        if filas:
            st.dataframe(
                pd.DataFrame(filas),
                width="stretch",
                hide_index=True,
                column_config={
                    "Pares comparados": st.column_config.NumberColumn(format="%d"),
                    "Diferencia máxima": st.column_config.NumberColumn(format="%.4f"),
                    "Fuera de tolerancia": st.column_config.NumberColumn(format="%d"),
                },
            )
            st.caption(
                "El IMC y la relación S/F se almacenan con 2 decimales y la ventilación "
                "en mL/min como entero; por eso se aplica una tolerancia de redondeo."
            )
        else:
            st.info("No hay resultados almacenados para comparar las fórmulas.")

    if ctx["avisos"]:
        with st.expander("📝 Notas de integración de datos", expanded=False):
            for aviso in ctx["avisos"]:
                st.markdown(f"- {aviso}")


# ==========================================================
# 5. PESTAÑA 2: REGISTROS Y FILTROS
# ==========================================================

COLUMNAS_REGISTROS = [
    ("id", "ID"),
    ("genero_desc", "Género"),
    ("edad", "Edad (años)"),
    ("ejercicio_desc", "Practica ejercicio"),
    ("peso_kg", "Peso (kg)"),
    ("estatura_m", "Estatura (m)"),
    ("spo2_pct", "SpO₂ (%)"),
    ("fio2", "FiO₂"),
    ("volumen_corriente_ml", "Vol. corriente (mL)"),
    ("frecuencia_respiratoria_rpm", "Frec. respiratoria (rpm)"),
    ("imc_calculado", "IMC calculado (kg/m²)"),
    ("relacion_sf_calculada", "Relación S/F calculada"),
    ("ventilacion_ml_min_calculada", "Ventilación calculada (mL/min)"),
    ("ventilacion_l_min_calculada", "Ventilación calculada (L/min)"),
    ("imc_simd", "IMC SIMD"),
    ("imc_misd", "IMC MISD"),
    ("relacion_sf_misd", "Relación S/F MISD"),
    ("ventilacion_ml_min_misd", "Ventilación MISD (mL/min)"),
    ("ventilacion_l_min_misd", "Ventilación MISD (L/min)"),
    ("mimd_etapa", "Etapa MIMD"),
    ("mimd_resultado", "Resultado MIMD (etapa)"),
    ("fuente", "Fuente"),
]

CONFIG_REGISTROS = {
    "ID": "%d",
    "Edad (años)": "%d",
    "Peso (kg)": "%.1f",
    "Estatura (m)": "%.2f",
    "SpO₂ (%)": "%.1f",
    "FiO₂": "%.2f",
    "Vol. corriente (mL)": "%d",
    "Frec. respiratoria (rpm)": "%d",
    "IMC calculado (kg/m²)": "%.2f",
    "Relación S/F calculada": "%.2f",
    "Ventilación calculada (mL/min)": "%.0f",
    "Ventilación calculada (L/min)": "%.2f",
    "IMC SIMD": "%.2f",
    "IMC MISD": "%.2f",
    "Relación S/F MISD": "%.2f",
    "Ventilación MISD (mL/min)": "%.0f",
    "Ventilación MISD (L/min)": "%.2f",
    "Resultado MIMD (etapa)": "%.2f",
}


def tabla_para_mostrar(df):
    presentes = [(col, nombre) for col, nombre in COLUMNAS_REGISTROS if col in df.columns]
    return df[[col for col, _ in presentes]].rename(
        columns={col: nombre for col, nombre in presentes}
    )


def render_registros(ctx):
    datos = ctx["filtrado"]
    st.subheader("Registros del dataset")
    st.caption(
        f"Vista de datos: **{ctx['fuente_etiqueta']}**. Un registro por paciente "
        "(ID único); las tablas de resultados se unen por la FK `paciente_id` sin "
        "multiplicar filas. Puedes ordenar haciendo clic en los encabezados."
    )

    if datos.empty:
        st.warning("No hay registros con los filtros globales actuales.")
        return

    busqueda = st.text_input(
        "Buscar por ID (varios separados por coma, ej. 12, 45, 900)",
        key="buscar_id",
    )
    ids, invalidos = parse_ids(busqueda)
    if invalidos:
        st.warning("Valores ignorados (no son enteros): " + ", ".join(invalidos))

    tabla = datos.copy()
    if ids:
        tabla = tabla[tabla["id"].isin(ids)].copy()
        if tabla.empty:
            st.warning(f"Ningún registro coincide con los IDs indicados: {ids}.")
            return

    st.caption(
        f"**{len(tabla):,}** registros coinciden con los filtros globales"
        + (" y la búsqueda por ID." if ids else ".")
    )

    columna_tamano, columna_pagina, columna_descarga = st.columns([1, 1, 2])

    with columna_tamano:
        tam_pagina = st.selectbox(
            "Filas por página", [25, 50, 100, 250], index=1, key="tam_pagina"
        )

    with columna_pagina:
        total_paginas = max(1, math.ceil(len(tabla) / tam_pagina))
        firma = (len(datos), len(tabla), tuple(ids), tam_pagina)
        if st.session_state.get("firma_pagina") != firma:
            st.session_state["firma_pagina"] = firma
            st.session_state["pagina_registros"] = 1
        if st.session_state.get("pagina_registros", 1) > total_paginas:
            st.session_state["pagina_registros"] = total_paginas
        pagina = st.number_input(
            f"Página (1 de {total_paginas:,})",
            min_value=1,
            max_value=total_paginas,
            key="pagina_registros",
        )

    tabla_completa = tabla_para_mostrar(tabla)

    with columna_descarga:
        st.download_button(
            "📥 Descargar registros filtrados (CSV)",
            data=tabla_completa.to_csv(index=False).encode("utf-8-sig"),
            file_name="registros_filtrados.csv",
            mime="text/csv",
            key="descarga_registros",
            width="stretch",
        )

    inicio = (int(pagina) - 1) * tam_pagina
    fin = min(inicio + tam_pagina, len(tabla))
    vista = tabla_completa.iloc[inicio:fin]

    st.caption(
        f"Mostrando filas {inicio + 1:,}–{fin:,} de {len(tabla):,}. "
        f"Exportación CSV con todas las filas filtradas ({len(tabla):,})."
    )

    st.dataframe(
        vista,
        width="stretch",
        hide_index=True,
        height=560,
        column_config=configuracion_numerica(
            {c: f for c, f in CONFIG_REGISTROS.items() if c in vista.columns}
        ),
    )

    st.caption(
        "`Resultado MIMD (etapa)` usa la unidad de la etapa indicada: IMC en kg/m², "
        "relación S/F adimensional o ventilación en mL/min. Cada paciente solo fue "
        "procesado por una de las tres etapas MIMD."
    )


# ==========================================================
# 6. PESTAÑA 3: ESTADÍSTICAS FISIOLÓGICAS
# ==========================================================

COLORES_VARIABLES = ["#2E86DE", "#27AE60", "#E67E22", "#8E44AD"]


def render_fisiologicas(ctx):
    datos = ctx["filtrado"]
    st.subheader("Estadísticas de las variables fisiológicas")
    st.caption(
        f"Calculadas en el dashboard sobre **{len(datos):,}** registros "
        f"({ctx['fuente_etiqueta']}). Fórmulas: IMC = peso / estatura², "
        "relación S/F = SpO₂ / FiO₂, ventilación = volumen corriente × frecuencia "
        "respiratoria."
    )

    if datos.empty:
        st.warning("No hay registros para analizar con los filtros actuales.")
        return

    tabla = tabla_estadisticas(datos)
    st.markdown("#### Resumen descriptivo")
    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config=configuracion_numerica(
            {
                "Media": "%.2f",
                "Mediana": "%.2f",
                "Mínimo": "%.2f",
                "Máximo": "%.2f",
                "Desv. est.": "%.2f",
            }
        ),
    )
    st.caption(
        "La desviación estándar es muestral (ddof = 1) y se muestra «—» cuando "
        "solo existe un valor válido. Los valores se presentan con dos decimales."
    )

    st.markdown("#### Distribuciones (histogramas)")
    columnas = st.columns(2)
    for indice, variable in enumerate(VARIABLES):
        with columnas[indice % 2]:
            histograma(
                datos[variable["clave"]],
                f"Distribución de {variable['etiqueta']} ({variable['unidad']})",
                f"{variable['etiqueta']} ({variable['unidad']})",
                color=COLORES_VARIABLES[indice],
            )

    st.markdown("#### Dispersión y valores extremos (diagramas de caja)")
    columnas = st.columns(2)
    for indice, variable in enumerate(VARIABLES):
        with columnas[indice % 2]:
            caja_simple(
                datos[variable["clave"]],
                f"{variable['etiqueta']} ({variable['unidad']})",
                f"{variable['etiqueta']} ({variable['unidad']})",
                color=COLORES_VARIABLES[indice],
            )

    st.info(
        "El dataset es sintético. Aquí solo se describen medias, medianas, extremos y "
        "dispersión: no se clasifican valores como normales o patológicos porque no hay "
        "criterios clínicos validados para estos datos."
    )


# ==========================================================
# 7. PESTAÑA 4: COMPARACIÓN POR PRÁCTICA DE EJERCICIO
# ==========================================================

VARIABLE_EDAD = {"clave": "edad", "etiqueta": "Edad", "unidad": "años", "dec": 0}
VARIABLES_EJERCICIO = VARIABLES + [VARIABLE_EDAD]


def render_ejercicio(ctx):
    datos = ctx["filtrado"]
    st.subheader("Comparación: práctica vs. no práctica de ejercicio")
    st.caption(
        "Codificación verificada en el dataset: `practica_ejercicio` = 0 (no) y "
        "1 (sí). Grupos calculados sobre los registros filtrados."
    )

    if datos.empty:
        st.warning("No hay registros para comparar con los filtros actuales.")
        return

    resumen = resumen_por_grupo(datos, VARIABLES_EJERCICIO)
    if resumen.empty:
        st.warning("No hay datos suficientes en ambos grupos para la comparación.")
        return

    grupos_presentes = set(resumen["Grupo"])
    if grupos_presentes != {"Sí", "No"}:
        st.warning(
            "La comparación requiere registros de ambos grupos. Con los filtros "
            "actuales solo hay: "
            + ", ".join(sorted(grupos_presentes))
            + ". Ajusta el filtro global de práctica de ejercicio."
        )

    st.markdown("#### Estadísticas por grupo")
    st.dataframe(
        resumen,
        width="stretch",
        hide_index=True,
        column_config=configuracion_numerica(
            {
                "Media": "%.2f",
                "Mediana": "%.2f",
                "Mínimo": "%.2f",
                "Máximo": "%.2f",
                "Desv. est.": "%.2f",
            }
        ),
    )

    diferencias = diferencias_entre_grupos(datos, VARIABLES_EJERCICIO)
    st.markdown("#### Diferencias entre grupos")
    if diferencias.empty:
        st.info(
            "No fue posible calcular diferencias: se necesitan registros de ambos "
            "grupos (Sí y No). Ajusta el filtro global de práctica de ejercicio."
        )
    else:
        mostrar = diferencias.copy()
        mostrar["Diferencia %"] = mostrar["Diferencia %"].map(
            lambda valor: fmt(valor, 2, " %")
        )
        st.dataframe(
            mostrar,
            width="stretch",
            hide_index=True,
            column_config=configuracion_numerica(
                {
                    "Media sin ejercicio": "%.2f",
                    "Media con ejercicio": "%.2f",
                    "Diferencia (Sí − No)": "%.2f",
                }
            ),
        )
        st.caption(
            "Diferencia % = (media con ejercicio − media sin ejercicio) / |media sin "
            "ejercicio| × 100. Se muestra «—» cuando el denominador es cero o "
            "prácticamente cero."
        )

    st.markdown("#### Medias por grupo con desviación estándar")
    columnas = st.columns(2)
    for indice, variable in enumerate(VARIABLES):
        with columnas[indice % 2]:
            barras_grupo(
                resumen[
                    resumen["Variable"]
                    == f"{variable['etiqueta']} ({variable['unidad']})"
                ],
                f"{variable['etiqueta']} medio por práctica de ejercicio "
                f"({variable['unidad']})",
                f"{variable['etiqueta']} ({variable['unidad']})",
                COLOR_EJERCICIO,
            )

    st.markdown("#### Distribuciones por grupo")
    columnas = st.columns(2)
    for indice, variable in enumerate(VARIABLES):
        with columnas[indice % 2]:
            caja_por_grupo(
                datos,
                variable["clave"],
                "ejercicio_desc",
                f"{variable['etiqueta']} según práctica de ejercicio "
                f"({variable['unidad']})",
                f"{variable['etiqueta']} ({variable['unidad']})",
                "Practica ejercicio",
                COLOR_EJERCICIO,
            )

    columna_edad_1, columna_edad_2 = st.columns(2)
    with columna_edad_1:
        barras_grupo(
            resumen[resumen["Variable"] == "Edad (años)"],
            "Edad media por práctica de ejercicio (años)",
            "Edad (años)",
            COLOR_EJERCICIO,
        )
    with columna_edad_2:
        caja_por_grupo(
            datos,
            "edad",
            "ejercicio_desc",
            "Edad según práctica de ejercicio (años)",
            "Edad (años)",
            "Practica ejercicio",
            COLOR_EJERCICIO,
        )

    st.warning(
        "Una diferencia visual o numérica entre grupos no demuestra causalidad. "
        "Los datos son sintéticos y este análisis es descriptivo: no permite "
        "conclusiones médicas ni sobre los efectos reales del ejercicio."
    )


# ==========================================================
# 8. PESTAÑA 5: COMPARACIÓN SIMD · MISD · MIMD
# ==========================================================


def construir_arquitecturas(tablas):
    """Resume los tiempos realmente almacenados por cada arquitectura."""
    arqs = {}

    simd = tablas.get("calculo_simd")
    if simd is not None and not simd.empty and "tiempo_microsegundos" in simd.columns:
        valores = valores_ejecucion(simd["tiempo_microsegundos"])
        if valores.size:
            arqs["SIMD"] = {
                "tabla": "calculo_simd",
                "filas": len(simd),
                "pacientes": int(simd["paciente_id"].nunique()),
                "valores": valores,
                "es_etapas": False,
                "etapa_detalle": None,
                "desde": simd["fecha_procesamiento"].min(),
                "hasta": simd["fecha_procesamiento"].max(),
            }

    misd = tablas.get("calculo_misd")
    if misd is not None and not misd.empty and "tiempo_microsegundos" in misd.columns:
        valores = valores_ejecucion(misd["tiempo_microsegundos"])
        if valores.size:
            arqs["MISD"] = {
                "tabla": "calculo_misd",
                "filas": len(misd),
                "pacientes": int(misd["paciente_id"].nunique()),
                "valores": valores,
                "es_etapas": False,
                "etapa_detalle": None,
                "desde": misd["fecha_procesamiento"].min(),
                "hasta": misd["fecha_procesamiento"].max(),
            }

    etapas = tablas.get("calculo_mimd_etapas")
    if (
        etapas is not None
        and not etapas.empty
        and "etapa" in etapas.columns
        and "tiempo_microsegundos" in etapas.columns
    ):
        valores = valores_ejecucion(etapas["tiempo_microsegundos"])
        if valores.size:
            arqs["MIMD"] = {
                "tabla": "calculo_mimd_etapas",
                "filas": len(etapas),
                "pacientes": int(etapas["paciente_id"].nunique()),
                "valores": valores,
                "es_etapas": True,
                "etapa_detalle": etapas,
                "desde": etapas["fecha_procesamiento"].min(),
                "hasta": etapas["fecha_procesamiento"].max(),
            }
    else:
        mimd = tablas.get("calculo_mimd")
        if (
            arqs.get("MIMD") is None
            and mimd is not None
            and not mimd.empty
            and "tiempo_microsegundos" in mimd.columns
        ):
            valores = valores_ejecucion(mimd["tiempo_microsegundos"])
            if valores.size:
                arqs["MIMD"] = {
                    "tabla": "calculo_mimd",
                    "filas": len(mimd),
                    "pacientes": int(mimd["paciente_id"].nunique()),
                    "valores": valores,
                    "es_etapas": False,
                    "etapa_detalle": None,
                    "desde": mimd["fecha_procesamiento"].min(),
                    "hasta": mimd["fecha_procesamiento"].max(),
                }

    return arqs


def resumen_arquitectura(info):
    valores = info["valores"]
    cantidad = len(valores)
    resumen = {
        "Filas": info["filas"],
        "Pacientes": info["pacientes"],
        "Mediciones": cantidad,
        "Media": float(valores.mean()),
        "Mediana": float(np.median(valores)),
        "Mínimo": float(valores.min()),
        "Máximo": float(valores.max()),
        "Desv. est.": float(valores.std(ddof=1)) if cantidad > 1 else float("nan"),
        "P90": float(np.percentile(valores, 90)),
        "P95": float(np.percentile(valores, 95)),
        "Total acumulado": float(valores.sum()),
    }
    return resumen


def render_arquitecturas(ctx):
    st.subheader("Comparación de arquitecturas: SIMD · MISD · MIMD")
    st.caption(
        "Tiempos leídos de las tablas de resultados. Unidad verificada en el código: "
        "`(fin - inicio) / 1000` sobre `perf_counter_ns()` = **microsegundos (µs)**. "
        "El comentario de `misd.py` que dice «milisegundos» es incorrecto."
    )

    if ctx["fuente"] == "Solo CSV":
        st.info(
            "La comparación de arquitecturas requiere los resultados almacenados en "
            "MySQL. Cambia la fuente de datos a **CSV + MySQL** o **Solo MySQL**."
        )
        return

    arqs = construir_arquitecturas(ctx["tablas"])
    if not arqs:
        st.warning(
            "No hay tiempos almacenados en `calculo_simd`, `calculo_misd` ni "
            "`calculo_mimd_etapas`/`calculo_mimd`. No se generan resultados de "
            "rendimiento para no inventar datos."
        )
        st.dataframe(
            tabla_estado_tablas(ctx["esquema"], ctx["tablas"]),
            width="stretch",
            hide_index=True,
        )
        return

    filas = []
    for arquitectura, info in arqs.items():
        resumen = resumen_arquitectura(info)
        filas.append(
            {
                "Arquitectura": arquitectura,
                "Tabla": info["tabla"],
                "Filas": resumen["Filas"],
                "Pacientes": resumen["Pacientes"],
                "Mediciones": resumen["Mediciones"],
                "Media (µs)": resumen["Media"],
                "Mediana (µs)": resumen["Mediana"],
                "Mín (µs)": resumen["Mínimo"],
                "Máx (µs)": resumen["Máximo"],
                "Desv. est. (µs)": resumen["Desv. est."],
                "P90 (µs)": resumen["P90"],
                "P95 (µs)": resumen["P95"],
                "Total acumulado (µs)": resumen["Total acumulado"],
            }
        )
    tabla = pd.DataFrame(filas)

    st.markdown("#### Estadísticas de tiempo por arquitectura")
    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config=configuracion_numerica(
            {
                "Filas": "%d",
                "Pacientes": "%d",
                "Mediciones": "%d",
                "Media (µs)": "%.4f",
                "Mediana (µs)": "%.4f",
                "Mín (µs)": "%.4f",
                "Máx (µs)": "%.4f",
                "Desv. est. (µs)": "%.4f",
                "P90 (µs)": "%.4f",
                "P95 (µs)": "%.4f",
                "Total acumulado (µs)": "%.4f",
            }
        ),
    )
    st.caption(
        "**Mediciones** = cantidad de tiempos distintos detectados en la tabla "
        "(el tiempo se guarda una vez por ejecución y se repite en cada fila). "
        "Con una sola medición, la desviación estándar no existe (se muestra vacía) "
        "y los percentiles coinciden con ese único valor. **Total acumulado** = suma "
        "de los tiempos de las mediciones detectadas; en MIMD es la suma de las tres "
        "etapas, no un tiempo de pared medido. En MIMD, la desviación y los "
        "percentiles describen la dispersión **entre las tres etapas** (cálculos "
        "distintos), no entre repeticiones de una misma ejecución. Las tablas no "
        "tienen columnas de estado o error: todas las filas leídas se consideran "
        "válidas."
    )

    columna_a, columna_b = st.columns(2)

    with columna_a:
        barras = []
        for arquitectura, info in arqs.items():
            resumen_info = resumen_arquitectura(info)
            for estadistico, valor in [
                ("Media", resumen_info["Media"]),
                ("Mediana", resumen_info["Mediana"]),
            ]:
                barras.append(
                    {
                        "Arquitectura": arquitectura,
                        "Estadístico": estadistico,
                        "Tiempo (µs)": valor,
                        "Mediciones": resumen_info["Mediciones"],
                    }
                )
        figura = px.bar(
            pd.DataFrame(barras),
            x="Arquitectura",
            y="Tiempo (µs)",
            color="Estadístico",
            barmode="group",
            text_auto=".4f",
            title="Tiempo medio y mediano por arquitectura (µs)",
            hover_data={"Mediciones": True},
            color_discrete_sequence=["#2E86DE", "#8E44AD"],
        )
        figura.update_layout(
            yaxis_type="log",
            yaxis_title="Tiempo (µs, escala log)",
            xaxis_title="Arquitectura",
            legend_title_text="Estadístico",
        )
        st.plotly_chart(figura, width="stretch")
        st.caption(
            "Media y mediana sobre las mediciones detectadas (una por ejecución; "
            "tres en MIMD, una por etapa). Escala logarítmica por la diferencia de "
            "magnitudes."
        )

    with columna_b:
        puntos = []
        for arquitectura, info in arqs.items():
            if info["es_etapas"] and info["etapa_detalle"] is not None:
                for etapa, subconjunto in info["etapa_detalle"].groupby(
                    "etapa", observed=True
                ):
                    valores = valores_ejecucion(subconjunto["tiempo_microsegundos"])
                    for valor in valores:
                        puntos.append(
                            {
                                "Arquitectura": arquitectura,
                                "Tiempo (µs)": valor,
                                "Detalle": f"Etapa {etapa}",
                            }
                        )
            else:
                for valor in info["valores"]:
                    puntos.append(
                        {
                            "Arquitectura": arquitectura,
                            "Tiempo (µs)": valor,
                            "Detalle": "Ejecución",
                        }
                    )
        figura = px.scatter(
            pd.DataFrame(puntos),
            x="Arquitectura",
            y="Tiempo (µs)",
            color="Detalle",
            symbol="Arquitectura",
            log_y=True,
            title="Tiempos medidos individualmente (µs)",
            labels={"Tiempo (µs)": "Tiempo (µs, escala log)"},
        )
        figura.update_traces(marker={"size": 14})
        figura.update_layout(yaxis_title="Tiempo (µs, escala log)")
        st.plotly_chart(figura, width="stretch")
        st.caption(
            "Cada punto es una medición almacenada. En MIMD se muestran las tres "
            "etapas; no son repeticiones del mismo cálculo."
        )

    st.divider()

    if "MIMD" in arqs and arqs["MIMD"]["es_etapas"]:
        st.markdown("#### Detalle de las etapas MIMD")
        detalle = arqs["MIMD"]["etapa_detalle"]
        filas = []
        for etapa, subconjunto in detalle.groupby("etapa", observed=True):
            valores = valores_ejecucion(subconjunto["tiempo_microsegundos"])
            filas.append(
                {
                    "Etapa": etapa,
                    "Filas": len(subconjunto),
                    "Pacientes": int(subconjunto["paciente_id"].nunique()),
                    "ID mínimo": int(subconjunto["paciente_id"].min()),
                    "ID máximo": int(subconjunto["paciente_id"].max()),
                    "Tiempo (µs)": float(valores[0]) if valores.size else float("nan"),
                    "Mediciones": int(valores.size),
                }
            )
        st.dataframe(
            pd.DataFrame(filas),
            width="stretch",
            hide_index=True,
            column_config=configuracion_numerica(
                {
                    "Filas": "%d",
                    "Pacientes": "%d",
                    "ID mínimo": "%d",
                    "ID máximo": "%d",
                    "Tiempo (µs)": "%.4f",
                    "Mediciones": "%d",
                }
            ),
        )
        st.caption(
            "Cada etapa procesa un tercio del dataset con una instrucción distinta: "
            "IMC (registros 1–1667), relación S/F (1668–3334) y ventilación "
            "(3335–5001)."
        )

    st.markdown("#### Speedup y reducción frente a una referencia")

    columna_modo, columna_ref = st.columns(2)

    with columna_modo:
        modo = st.radio(
            "Métrica de comparación",
            ["Total de la ejecución (µs)", "Media por medición (µs)"],
            horizontal=True,
            key="modo_comparacion",
        )

    with columna_ref:
        opciones = list(arqs.keys())
        representativo_inicial = {
            arquitectura: (
                resumen_arquitectura(info)["Total acumulado"]
                if modo.startswith("Total")
                else resumen_arquitectura(info)["Media"]
            )
            for arquitectura, info in arqs.items()
        }
        indice_referencia = int(
            np.argmax([representativo_inicial[a] for a in opciones])
        )
        referencia = st.selectbox(
            "Arquitectura de referencia",
            opciones,
            index=indice_referencia,
            key="arquitectura_referencia",
        )

    representativos = {
        arquitectura: (
            resumen_arquitectura(info)["Total acumulado"]
            if modo.startswith("Total")
            else resumen_arquitectura(info)["Media"]
        )
        for arquitectura, info in arqs.items()
    }

    tiempo_ref = representativos[referencia]
    filas = []
    for arquitectura in arqs:
        tiempo = representativos[arquitectura]
        filas.append(
            {
                "Arquitectura": arquitectura,
                "Tiempo representativo (µs)": tiempo,
                "Diferencia vs referencia (µs)": tiempo - tiempo_ref,
                "Reducción vs referencia (%)": (
                    (tiempo_ref - tiempo) / tiempo_ref * 100
                    if tiempo_ref
                    else float("nan")
                ),
                "Speedup (referencia / arquitectura)": (
                    tiempo_ref / tiempo if tiempo else float("nan")
                ),
                "Mediciones": int(arqs[arquitectura]["valores"].size),
            }
        )

    st.dataframe(
        pd.DataFrame(filas),
        width="stretch",
        hide_index=True,
        column_config=configuracion_numerica(
            {
                "Tiempo representativo (µs)": "%.4f",
                "Diferencia vs referencia (µs)": "%.4f",
                "Reducción vs referencia (%)": "%.2f",
                "Speedup (referencia / arquitectura)": "%.3f",
                "Mediciones": "%d",
            }
        ),
    )
    st.caption(
        "Por defecto se propone como referencia la arquitectura con mayor tiempo "
        "representativo según la métrica elegida; puedes cambiarla. Reducción % = "
        "(tiempo de referencia − tiempo de la arquitectura) / tiempo de referencia "
        "× 100; un valor negativo indica que es más lenta. Speedup = tiempo de "
        "referencia / tiempo de la arquitectura."
    )

    medias = {
        arquitectura: resumen_arquitectura(info)["Media"]
        for arquitectura, info in arqs.items()
    }
    medianas = {
        arquitectura: resumen_arquitectura(info)["Mediana"]
        for arquitectura, info in arqs.items()
    }
    mejor_media = min(medias, key=medias.get)
    mejor_mediana = min(medianas, key=medianas.get)

    st.caption(
        f"Menor **media por medición**: {mejor_media} "
        f"({fmt(medias[mejor_media], 4)} µs, "
        f"{int(arqs[mejor_media]['valores'].size)} medición(es)). "
        f"Menor **mediana**: {mejor_mediana} "
        f"({fmt(medianas[mejor_mediana], 4)} µs). "
        f"Referencia elegida: {referencia} ({fmt(tiempo_ref, 4)} µs)."
    )

    st.warning(
        "Estas mediciones **no comparan cargas equivalentes**: SIMD calcula solo el IMC "
        "de los 5 001 registros, MISD calcula cuatro métricas de los 5 001 registros y "
        "MIMD calcula una métrica distinta por tercio. Además hay una sola ejecución "
        "registrada por arquitectura, por lo que no existe variabilidad entre "
        "repeticiones independientes y no se puede afirmar significancia estadística."
    )

    with st.expander("Limitaciones de la comparación", expanded=False):
        st.markdown(
            """
- **Unidad de tiempo:** microsegundos, confirmada en `main.py`, `misd.py` y `mimd.py`
  (`perf_counter_ns()` dividido entre 1 000).
- **Una ejecución por arquitectura:** el tiempo se almacena repetido en cada fila;
  por eso «mediciones» cuenta tiempos distintos, no filas.
- **MIMD:** `calculo_mimd_etapas` guarda el tiempo de cada etapa, no el tiempo de pared
  total. El «total acumulado» es la suma de las tres etapas y se etiqueta como tal.
- **Cargas distintas:** SIMD (1 cálculo), MISD (4 cálculos) y MIMD (1 cálculo por
  tercio) no realizan el mismo trabajo; el speedup debe leerse con esa salvedad.
- **Sin repeticiones:** no se presentan intervalos de confianza ni pruebas de
  significancia porque no hay muestras independientes suficientes.
- **Sin mediciones pareadas:** dentro de una ejecución cada registro tiene un único
  tiempo (constante para todo el lote), así que no hay pares por paciente para
  comparar arquitecturas con una prueba pareada.
- La tabla `calculo_mimd` no existe en esta base; los datos MIMD provienen de
  `calculo_mimd_etapas`. La tabla `calcular` tampoco existe.
            """
        )


# ==========================================================
# 9. PESTAÑA 6: RELACIÓN ENTRE VARIABLES Y TIEMPOS
# ==========================================================


def render_relaciones(ctx):
    datos = ctx["filtrado"]
    st.subheader("Relación entre variables fisiológicas y tiempos de ejecución")
    st.caption(
        "Se comprueba primero si el tiempo almacenado varía por paciente. Si no varía, "
        "no se calculan correlaciones de rendimiento para no presentar resultados "
        "artificiales."
    )

    if datos.empty:
        st.warning("No hay registros para analizar con los filtros actuales.")
        return

    columnas_tiempo = {
        "SIMD": "tiempo_simd_us",
        "MISD": "tiempo_misd_us",
        "MIMD": "mimd_tiempo_us",
    }
    disponibles = {
        arquitectura: columna
        for arquitectura, columna in columnas_tiempo.items()
        if columna in datos.columns
    }

    if not disponibles:
        st.info(
            "No hay columnas de tiempo disponibles en la vista actual "
            "(por ejemplo, porque estás usando «Solo CSV»). Cambia la fuente de datos "
            "para incluir los resultados de MySQL."
        )

    if disponibles:
        st.markdown("#### Diagnóstico: ¿el tiempo varía por paciente?")
        filas = []
        for arquitectura, columna in disponibles.items():
            serie = pd.to_numeric(datos[columna], errors="coerce").dropna()
            if serie.empty:
                continue
            distintos = int(serie.round(4).nunique())

            if arquitectura == "MIMD" and "mimd_etapa" in datos.columns:
                por_etapa = datos.groupby("mimd_etapa", observed=True)[
                    columna
                ].nunique(dropna=True)
                constante_por_etapa = bool((por_etapa <= 1).all())
                if constante_por_etapa:
                    varia = "No (depende de la etapa)"
                    motivo = (
                        "Cada etapa MIMD tiene un único tiempo; el valor depende de la "
                        "instrucción ejecutada, no del paciente."
                    )
                else:
                    varia = "Sí"
                    motivo = "Hay más de un tiempo dentro de alguna etapa MIMD."
            elif distintos <= 1:
                varia = "No"
                motivo = (
                    "Tiempo constante: la ejecución registró un solo valor y se repite "
                    "en todas las filas."
                )
            else:
                varia = "Sí"
                motivo = "Existen varios tiempos distintos en el conjunto filtrado."

            if distintos <= 1:
                desviacion = 0.0
            else:
                desviacion = (
                    float(serie.std(ddof=1)) if serie.size > 1 else float("nan")
                )

            filas.append(
                {
                    "Arquitectura": arquitectura,
                    "Registros con tiempo": int(serie.size),
                    "Tiempos distintos": distintos,
                    "Desv. est. (µs)": desviacion,
                    "¿Varía por paciente?": varia,
                    "Motivo": motivo,
                }
            )

        st.dataframe(
            pd.DataFrame(filas),
            width="stretch",
            hide_index=True,
            column_config=configuracion_numerica(
                {
                    "Registros con tiempo": "%d",
                    "Tiempos distintos": "%d",
                    "Desv. est. (µs)": "%.4f",
                }
            ),
        )

        st.markdown("#### Tiempo medio por práctica de ejercicio")
        filas = []
        for arquitectura, columna in disponibles.items():
            for grupo in ["No", "Sí"]:
                subconjunto = datos.loc[
                    datos["ejercicio_desc"] == grupo, columna
                ].dropna()
                if subconjunto.empty:
                    continue
                distintos_grupo = int(subconjunto.round(4).nunique())
                filas.append(
                    {
                        "Arquitectura": arquitectura,
                        "Grupo": grupo,
                        "n": int(subconjunto.size),
                        "Media (µs)": float(subconjunto.mean()),
                        "Desv. est. (µs)": (
                            0.0
                            if distintos_grupo <= 1
                            else float(subconjunto.std(ddof=1))
                        ),
                        "Tiempos distintos": distintos_grupo,
                    }
                )
        if filas:
            st.dataframe(
                pd.DataFrame(filas),
                width="stretch",
                hide_index=True,
                column_config=configuracion_numerica(
                    {
                        "n": "%d",
                        "Media (µs)": "%.4f",
                        "Desv. est. (µs)": "%.4f",
                        "Tiempos distintos": "%d",
                    }
                ),
            )
            st.caption(
                "En SIMD y MISD las medias por grupo son idénticas porque el tiempo es "
                "una propiedad de la ejecución, no del paciente. En MIMD las pequeñas "
                "diferencias reflejan qué proporción de cada grupo cayó en cada etapa "
                "(IMC, S/F o ventilación), no una relación con la fisiología. No hay "
                "evidencia para relacionar el tiempo con edad, IMC, S/F o ventilación."
            )

        aptos = []
        for arquitectura, columna in disponibles.items():
            serie = pd.to_numeric(datos[columna], errors="coerce").dropna()
            if serie.round(4).nunique() <= 1:
                continue
            if arquitectura == "MIMD" and "mimd_etapa" in datos.columns:
                por_etapa = datos.groupby("mimd_etapa", observed=True)[
                    columna
                ].nunique(dropna=True)
                if (por_etapa <= 1).all():
                    continue
            aptos.append(arquitectura)

        if aptos:
            st.markdown("#### Correlación tiempo–variable por arquitectura")
            metodo = st.radio(
                "Coeficiente de correlación",
                ["Spearman", "Pearson"],
                horizontal=True,
                key="metodo_tiempo",
            )
            for arquitectura in aptos:
                columna = disponibles[arquitectura]
                pares = pd.DataFrame(
                    {
                        "Tiempo (µs)": datos[columna],
                        "Edad (años)": datos["edad"],
                        "IMC (kg/m²)": datos["imc_calculado"],
                        "Relación S/F": datos["relacion_sf_calculada"],
                        "Ventilación (L/min)": datos["ventilacion_l_min_calculada"],
                    }
                ).dropna()
                st.markdown(f"**{arquitectura}**")
                if len(pares) < 10:
                    st.info(
                        f"Muestra insuficiente ({len(pares)} pares) para calcular "
                        "correlaciones fiables."
                    )
                    continue
                correlaciones = (
                    pares.corr(method=metodo.lower(), numeric_only=True)["Tiempo (µs)"]
                    .drop("Tiempo (µs)")
                    .rename("Correlación")
                    .reset_index()
                    .rename(columns={"index": "Variable"})
                )
                st.dataframe(
                    correlaciones,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Correlación": st.column_config.NumberColumn(format="%.3f")
                    },
                )
        else:
            st.info(
                "No es posible analizar la relación entre el tiempo de ejecución y las "
                "variables fisiológicas: los tiempos son constantes por ejecución "
                "(SIMD y MISD) o dependen de la etapa MIMD, no del paciente. "
                "Por eso se omiten las correlaciones de rendimiento."
            )

    st.divider()
    st.markdown("#### Complemento: correlación entre variables fisiológicas")
    st.caption(
        "Este análisis no relaciona rendimiento con fisiología; describe únicamente "
        "asociaciones entre las variables del dataset sintético."
    )

    columnas_numericas = [
        columna for columna in ETIQUETAS_NUMERICAS if columna in datos.columns
    ]
    if len(columnas_numericas) < 2:
        st.info("No hay suficientes variables numéricas para la matriz de correlación.")
        return

    metodo_fisio = st.radio(
        "Coeficiente",
        ["Spearman", "Pearson"],
        horizontal=True,
        key="metodo_fisio",
    )
    correlacion = (
        datos[columnas_numericas]
        .corr(method=metodo_fisio.lower(), numeric_only=True)
        .rename(index=ETIQUETAS_NUMERICAS, columns=ETIQUETAS_NUMERICAS)
    )

    figura = px.imshow(
        correlacion,
        text_auto=".2f",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        aspect="auto",
        title=f"Matriz de correlación ({metodo_fisio}) — variables fisiológicas",
    )
    figura.update_layout(height=640)
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "Correlación descriptiva, no causal. Los datos son sintéticos y no permiten "
        "conclusiones clínicas. Spearman es más robusto ante relaciones no lineales y "
        "valores extremos; Pearson mide relación lineal."
    )


# ==========================================================
# 10. CARGA PRINCIPAL, FILTROS Y PESTAÑAS
# ==========================================================

st.title("Dashboard fisiológico · arquitecturas SIMD, MISD y MIMD")
st.caption(
    "Análisis de 5 001 registros sintéticos del proyecto de Computación Paralela. "
    "Fuentes: `dataset_5001.csv` y MySQL (`proyecto_paralela`). Todas las consultas "
    "son de solo lectura: no se modifican tablas ni el CSV."
)

esquema, error_bd = cargar_esquema()
tablas, errores_tablas = cargar_tablas(esquema)

try:
    csv = cargar_csv()
    error_csv = None
except Exception as error:
    csv = None
    error_csv = str(error)

st.sidebar.header("Panel de control")

if st.sidebar.button("🔄 Actualizar datos", width="stretch"):
    st.cache_data.clear()
    st.rerun()

opciones_fuente = (
    ["CSV + MySQL", "Solo CSV", "Solo MySQL"] if tablas else ["Solo CSV"]
)
fuente = st.sidebar.radio(
    "Fuente de datos",
    opciones_fuente,
    index=0,
    key="fuente_datos",
    help=(
        "CSV + MySQL combina las entradas del CSV con los resultados almacenados. "
        "Solo CSV calcula todas las métricas en el dashboard. "
        "Solo MySQL usa datos_fisiologicos como fuente de entrada."
    ),
)

if error_bd:
    st.sidebar.error("MySQL no disponible: se muestran solo datos del CSV.")
    with st.sidebar.expander("Detalle del error de conexión"):
        st.code(error_bd[:800])
if error_csv:
    st.sidebar.error(f"No se pudo leer `{ARCHIVO_CSV}`: {error_csv[:200]}")

avisos = []
if error_bd:
    avisos.append(f"MySQL no disponible: {error_bd}")
for error in errores_tablas:
    avisos.append(f"Error leyendo una tabla: {error}")

base = None

if fuente == "Solo MySQL":
    db_inputs = tablas.get("datos_fisiologicos")
    if db_inputs is not None and not db_inputs.empty:
        base = preparar_entrada(db_inputs, "MySQL")
    else:
        st.sidebar.warning(
            "No hay `datos_fisiologicos` disponible; se usará el CSV."
        )
        fuente = "Solo CSV"

if base is None:
    try:
        if csv is not None:
            base = preparar_entrada(
                csv, "CSV" if fuente == "Solo CSV" else "CSV + MySQL"
            )
        elif tablas.get("datos_fisiologicos") is not None:
            base = preparar_entrada(tablas["datos_fisiologicos"], "MySQL")
        else:
            st.error(
                "No se pudo cargar `dataset_5001.csv` ni `datos_fisiologicos` desde "
                "MySQL. Revisa la ruta del CSV y la conexión."
            )
            st.stop()
    except Exception as error:
        st.error(f"No fue posible preparar los datos de entrada: {error}")
        st.stop()

if fuente == "Solo CSV" or not tablas:
    datos = base.copy()
else:
    datos = agregar_resultados(base, tablas, avisos)

if not tablas:
    fuente_etiqueta = "Solo CSV (MySQL no disponible)"
elif fuente == "Solo MySQL":
    fuente_etiqueta = "Solo MySQL (datos_fisiologicos + resultados)"
elif fuente == "Solo CSV":
    fuente_etiqueta = "Solo CSV (métricas calculadas en el dashboard)"
else:
    fuente_etiqueta = "CSV + resultados de MySQL"

# ---------------- Filtros globales ----------------

st.sidebar.divider()
st.sidebar.subheader("Filtros globales")

generos = sorted(datos["genero_desc"].unique().tolist())
sel_genero = st.sidebar.multiselect(
    "Género", generos, default=generos, key="filtro_genero"
)

ejercicios = [
    valor for valor in ["Sí", "No", "Sin dato"] if valor in set(datos["ejercicio_desc"])
]
sel_ejercicio = st.sidebar.multiselect(
    "Práctica de ejercicio", ejercicios, default=ejercicios, key="filtro_ejercicio"
)

edades = datos["edad"].dropna()
if edades.empty:
    rango_edad = (0, 0)
else:
    edad_min, edad_max = int(edades.min()), int(edades.max())
    if edad_min == edad_max:
        st.sidebar.caption(f"Edad: {edad_min} años")
        rango_edad = (edad_min, edad_max)
    else:
        rango_edad = st.sidebar.slider(
            "Rango de edad (años)",
            min_value=edad_min,
            max_value=edad_max,
            value=(edad_min, edad_max),
            key="filtro_edad",
        )

filtrado = datos[
    datos["genero_desc"].isin(sel_genero)
    & datos["ejercicio_desc"].isin(sel_ejercicio)
    & datos["edad"].between(rango_edad[0], rango_edad[1])
].copy()

st.sidebar.caption(
    f"Mostrando **{len(filtrado):,}** de **{len(datos):,}** registros · "
    f"**{filtrado['id'].nunique():,}** pacientes únicos."
)
st.sidebar.caption(
    "Los tiempos se registran por ejecución, no por paciente: los filtros no "
    "modifican los valores almacenados."
)

# ---------------- Pestañas ----------------

contexto = {
    "datos": datos,
    "filtrado": filtrado,
    "csv": csv,
    "tablas": tablas,
    "esquema": esquema,
    "fuente": fuente,
    "fuente_etiqueta": fuente_etiqueta,
    "avisos": avisos,
    "error_bd": error_bd,
}

pestanas = st.tabs(
    [
        "📌 Resumen general",
        "📋 Registros y filtros",
        "📈 Estadísticas fisiológicas",
        "🏃 Ejercicio: comparación",
        "⚙️ SIMD vs MISD vs MIMD",
        "🔗 Variables y tiempos",
    ]
)

with pestanas[0]:
    render_resumen(contexto)

with pestanas[1]:
    render_registros(contexto)

with pestanas[2]:
    render_fisiologicas(contexto)

with pestanas[3]:
    render_ejercicio(contexto)

with pestanas[4]:
    render_arquitecturas(contexto)

with pestanas[5]:
    render_relaciones(contexto)

st.divider()
st.caption(
    "Dashboard de solo lectura. Tablas usadas: `datos_fisiologicos`, `calculo_simd`, "
    "`calculo_misd` y `calculo_mimd_etapas`. Para actualizar los resultados ejecuta "
    "`python main.py`, `python misd.py` y `python mimd.py`; después pulsa "
    "«Actualizar datos»."
)






