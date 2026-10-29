import pandas as pd
import plotly.express as px
import streamlit as st

from conexion import conectar_mysql

# ==========================================
# 1. CONFIGURACION DEL DASHBOARD
# ==========================================

st.set_page_config(
    page_title="Dashboard SIMD / MISD / MIMD - Indicadores Respiratorios",
    page_icon="📊",
    layout="wide"
)

st.title("Evaluación de Indicadores Respiratorios mediante las Arquitecturas SIMD, MISD y MIMD")
st.caption(
    "Computación Paralela | Procesamiento SIMD secuencial (main.py), MISD multihilo "
    "(misd.py) y MIMD por etapas (mimd.py) | Python + MySQL"
)


# ==========================================
# 2. CONSTANTES Y UTILIDADES
# ==========================================

# datos_fisiologicos.genero: 1 = Masculino, 0 = Femenino
GENERO_MAP = {1: "Masculino", 0: "Femenino"}

# datos_fisiologicos.practica_ejercicio: 1 = Sí, 0 = No
EJERCICIO_MAP = {1: "Sí", 0: "No"}

# calculo_mimd_etapas.etapa: cada tercio del dataset calcula una métrica distinta
ETAPAS_MIMD = ["IMC", "RELACION_SF", "VENTILACION"]
ETIQUETAS_ETAPA_MIMD = {
    "IMC": "IMC",
    "RELACION_SF": "Relación SpO₂/FiO₂",
    "VENTILACION": "Ventilación",
}
# etapa -> (columna, nombre de la métrica, unidad, decimales)
METRICAS_ETAPA_MIMD = {
    "IMC": ("imc", "IMC", "kg/m²", 2),
    "RELACION_SF": ("relacion_sf", "Relación SpO₂/FiO₂", "adimensional", 2),
    "VENTILACION": ("ventilacion_l_min", "Ventilación", "L/min", 2),
}

CATEGORIAS_IMC = ["Bajo peso", "Normal", "Sobrepeso", "Obesidad"]
COLOR_CATEGORIA_IMC = {
    "Bajo peso": "#3498DB",
    "Normal": "#27AE60",
    "Sobrepeso": "#F39C12",
    "Obesidad": "#E74C3C",
}
COLOR_GENERO = {"Masculino": "#2E86DE", "Femenino": "#E84393", "Sin dato": "#95A5A6"}
COLOR_EJERCICIO = {"Sí": "#27AE60", "No": "#E67E22", "Sin dato": "#95A5A6"}

ETIQUETAS_NUMERICAS = {
    "edad": "Edad",
    "peso_kg": "Peso (kg)",
    "estatura_m": "Estatura (m)",
    "imc": "IMC",
    "spo2_pct": "SpO₂ (%)",
    "fio2": "FiO₂",
    "relacion_sf": "Relación SpO₂/FiO₂",
    "volumen_corriente_ml": "Vol. corriente (ml)",
    "frecuencia_respiratoria_rpm": "Frec. respiratoria (rpm)",
    "ventilacion_ml_min": "Ventilación (ml/min)",
    "ventilacion_l_min": "Ventilación (L/min)",
}

UNIDADES_TIEMPO = {
    "Microsegundos (µs)": ("µs", 1.0),
    "Milisegundos (ms)": ("ms", 0.001),
}


def clasificar_imc(imc: float) -> str:
    """Clasificación de la OMS para el Índice de Masa Corporal."""
    if pd.isna(imc):
        return "Sin dato"
    if imc < 18.5:
        return "Bajo peso"
    if imc < 25:
        return "Normal"
    if imc < 30:
        return "Sobrepeso"
    return "Obesidad"


def preparar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos y agrega columnas descriptivas a partir de las FK."""
    if df.empty:
        return df

    df = df.copy()

    for columna in ["paciente_id", "genero", "edad", "practica_ejercicio"]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int64")

    for columna in [
        "peso_kg", "estatura_m", "imc", "spo2_pct", "fio2",
        "relacion_sf", "ventilacion_ml_min", "ventilacion_l_min",
        "tiempo_microsegundos",
    ]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")

    if "fecha_procesamiento" in df.columns:
        df["fecha_procesamiento"] = pd.to_datetime(df["fecha_procesamiento"], errors="coerce")

    # El detalle de MIMD incluye la etapa que calculó cada paciente.
    if "etapa" in df.columns:
        df["etapa"] = df["etapa"].astype("string")
        df["etapa_desc"] = df["etapa"].map(ETIQUETAS_ETAPA_MIMD).fillna(df["etapa"])

    # Columnas explicativas derivadas (la FK datos_fisiologicos.id aporta estos datos)
    df["genero_desc"] = df["genero"].map(GENERO_MAP).fillna("Sin dato")
    df["ejercicio_desc"] = df["practica_ejercicio"].map(EJERCICIO_MAP).fillna("Sin dato")
    df["categoria_imc"] = pd.cut(
        df["imc"],
        bins=[float("-inf"), 18.5, 25.0, 30.0, float("inf")],
        labels=CATEGORIAS_IMC,
        right=False,
    )
    df["grupo_etario"] = pd.cut(
        df["edad"],
        bins=[17, 29, 44, 59, 74, 200],
        labels=["18-29", "30-44", "45-59", "60-74", "75+"],
        right=True,
    )
    return df


def consultar_dataframe(consulta: str) -> pd.DataFrame:
    """Ejecuta una consulta y la devuelve como DataFrame."""
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


def formatear_tiempo(tiempo_us: float, unidad: str) -> str:
    """Convierte el tiempo almacenado (µs) a la unidad elegida."""
    simbolo, factor = UNIDADES_TIEMPO[unidad]
    return f"{tiempo_us * factor:,.4f} {simbolo}"


def promediar(serie: pd.Series, decimales: int = 2, sufijo: str = "") -> str:
    """Promedio de una serie, mostrando '—' si no hay valores válidos."""
    serie = pd.to_numeric(serie, errors="coerce").dropna()
    if serie.empty:
        return "—"
    return f"{serie.mean():,.{decimales}f}{sufijo}"


def slider_rango(etiqueta: str, minimo: int, maximo: int, clave: str):
    """Crea un slider tolerante a columnas con un único valor distinto."""
    if minimo >= maximo:
        st.caption(f"{etiqueta}: **{minimo}**")
        return minimo, maximo
    return st.slider(
        etiqueta,
        min_value=int(minimo),
        max_value=int(maximo),
        value=(int(minimo), int(maximo)),
        step=1,
        key=clave,
    )


def rango_entero(serie: pd.Series) -> tuple[int, int]:
    """Devuelve (mínimo, máximo) enteros, tolerando columnas con valores nulos."""
    if serie.dropna().empty:
        return 0, 0
    return int(serie.min()), int(serie.max())


# ==========================================
# 3. CONSULTAS A MYSQL (PK / FK)
# ==========================================

SQL_SIMD = """
    SELECT
        s.paciente_id          AS paciente_id,
        d.genero               AS genero,
        d.edad                 AS edad,
        d.practica_ejercicio   AS practica_ejercicio,
        d.peso_kg              AS peso_kg,
        d.estatura_m           AS estatura_m,
        s.imc                  AS imc,
        s.tiempo_microsegundos AS tiempo_microsegundos,
        s.fecha_procesamiento  AS fecha_procesamiento
    FROM calculo_simd s
    INNER JOIN datos_fisiologicos d
        ON d.id = s.paciente_id
    ORDER BY s.paciente_id ASC
"""

# calculo_misd acumula una fila por ejecución (no tiene ON DUPLICATE KEY),
# por eso se toma el último cálculo de cada paciente: MAX(id) por paciente_id.
SQL_MISD = """
    SELECT
        m.paciente_id             AS paciente_id,
        d.genero                  AS genero,
        d.edad                    AS edad,
        d.practica_ejercicio      AS practica_ejercicio,
        d.peso_kg                 AS peso_kg,
        d.estatura_m              AS estatura_m,
        d.spo2_pct                AS spo2_pct,
        d.fio2                    AS fio2,
        d.volumen_corriente_ml    AS volumen_corriente_ml,
        d.frecuencia_respiratoria_rpm AS frecuencia_respiratoria_rpm,
        m.imc                     AS imc,
        m.relacion_sf             AS relacion_sf,
        m.ventilacion_ml_min      AS ventilacion_ml_min,
        m.ventilacion_l_min       AS ventilacion_l_min,
        m.tiempo_microsegundos    AS tiempo_microsegundos,
        m.fecha_procesamiento     AS fecha_procesamiento
    FROM calculo_misd m
    INNER JOIN datos_fisiologicos d
        ON d.id = m.paciente_id
    INNER JOIN (
        SELECT paciente_id, MAX(id) AS ultimo_id
        FROM calculo_misd
        GROUP BY paciente_id
    ) u ON u.ultimo_id = m.id
    ORDER BY m.paciente_id ASC
"""

SQL_MIMD = """
    SELECT
        e.paciente_id             AS paciente_id,
        d.genero                  AS genero,
        d.edad                    AS edad,
        d.practica_ejercicio      AS practica_ejercicio,
        d.peso_kg                 AS peso_kg,
        d.estatura_m              AS estatura_m,
        d.spo2_pct                AS spo2_pct,
        d.fio2                    AS fio2,
        d.volumen_corriente_ml    AS volumen_corriente_ml,
        d.frecuencia_respiratoria_rpm AS frecuencia_respiratoria_rpm,
        e.etapa                   AS etapa,
        e.imc                     AS imc,
        e.relacion_sf             AS relacion_sf,
        e.ventilacion_ml_min      AS ventilacion_ml_min,
        e.ventilacion_l_min       AS ventilacion_l_min,
        e.tiempo_microsegundos    AS tiempo_microsegundos,
        e.fecha_procesamiento     AS fecha_procesamiento
    FROM calculo_mimd_etapas e
    INNER JOIN datos_fisiologicos d
        ON d.id = e.paciente_id
    ORDER BY e.etapa ASC, e.paciente_id ASC
"""

SQL_INTEGRIDAD = """
    SELECT
        (SELECT COUNT(*) FROM datos_fisiologicos) AS pacientes,
        (SELECT COUNT(*) FROM calculo_simd) AS filas_simd,
        (SELECT COUNT(*) FROM calculo_misd) AS filas_misd,
        (SELECT COUNT(*) FROM calculo_simd s
            LEFT JOIN datos_fisiologicos d ON d.id = s.paciente_id
            WHERE d.id IS NULL) AS huerfanos_simd,
        (SELECT COUNT(*) FROM calculo_misd m
            LEFT JOIN datos_fisiologicos d ON d.id = m.paciente_id
            WHERE d.id IS NULL) AS huerfanos_misd
"""

SQL_INTEGRIDAD_MIMD = """
    SELECT
        (SELECT COUNT(*) FROM calculo_mimd_etapas) AS filas_mimd,
        (SELECT COUNT(DISTINCT paciente_id) FROM calculo_mimd_etapas) AS pacientes_mimd,
        (SELECT COUNT(*) FROM calculo_mimd_etapas e
            LEFT JOIN datos_fisiologicos d ON d.id = e.paciente_id
            WHERE d.id IS NULL) AS huerfanos_mimd,
        (SELECT COUNT(*) FROM (
            SELECT paciente_id
            FROM calculo_mimd_etapas
            GROUP BY paciente_id
            HAVING COUNT(DISTINCT etapa) > 1
        ) x) AS multi_etapa_mimd
"""


@st.cache_data(ttl=300, show_spinner="Consultando resultados SIMD en MySQL...")
def cargar_datos_simd() -> pd.DataFrame:
    return preparar_datos(consultar_dataframe(SQL_SIMD))


@st.cache_data(ttl=300, show_spinner="Consultando resultados MISD en MySQL...")
def cargar_datos_misd() -> pd.DataFrame:
    return preparar_datos(consultar_dataframe(SQL_MISD))


@st.cache_data(ttl=300, show_spinner="Consultando resultados MIMD en MySQL...")
def cargar_datos_mimd() -> pd.DataFrame:
    return preparar_datos(consultar_dataframe(SQL_MIMD))


@st.cache_data(ttl=300, show_spinner=False)
def cargar_integridad() -> dict:
    integridad = consultar_dataframe(SQL_INTEGRIDAD).iloc[0].to_dict()
    try:
        integridad.update(consultar_dataframe(SQL_INTEGRIDAD_MIMD).iloc[0].to_dict())
        integridad["mimd_disponible"] = 1
    except Exception:
        # Si mimd.py todavía no se ha ejecutado, la tabla puede no existir.
        integridad.update(
            {
                "filas_mimd": 0,
                "pacientes_mimd": 0,
                "huerfanos_mimd": 0,
                "multi_etapa_mimd": 0,
                "mimd_disponible": 0,
            }
        )
    return integridad


# ==========================================
# 4. PANEL LATERAL
# ==========================================

st.sidebar.header("Panel de Control")

if st.sidebar.button("🔄 Actualizar datos consultados", width="stretch"):
    st.cache_data.clear()
    st.rerun()

unidad_tiempo = st.sidebar.selectbox(
    "Unidad de visualización del tiempo",
    options=list(UNIDADES_TIEMPO.keys()),
    help="El tiempo se almacena como tiempo_microsegundos (µs) en las tablas de resultados.",
)

st.sidebar.divider()
st.sidebar.caption(
    "**Fuente de datos**\n\n"
    "- `main.py` → `calculo_simd`\n"
    "- `misd.py` → `calculo_misd` + `datos_fisiologicos`\n"
    "- `mimd.py` → `calculo_mimd_etapas` (una fila por paciente y etapa)\n\n"
    "Los tres dashboards se enriquecen por la FK "
    "`paciente_id → datos_fisiologicos.id` (género, edad y práctica de ejercicio)."
)

# ==========================================
# 5. CARGA DE DATOS
# ==========================================

error_simd = None
error_misd = None
error_mimd = None

try:
    datos_simd = cargar_datos_simd()
except Exception as error:
    datos_simd = pd.DataFrame()
    error_simd = str(error)

try:
    datos_misd = cargar_datos_misd()
except Exception as error:
    datos_misd = pd.DataFrame()
    error_misd = str(error)

try:
    datos_mimd = cargar_datos_mimd()
except Exception as error:
    datos_mimd = pd.DataFrame()
    error_mimd = str(error)


# ==========================================
# 6. ESTRUCTURA RELACIONAL E INTEGRIDAD
# ==========================================

with st.expander("🔗 Estructura relacional (PK / FK) e integridad referencial", expanded=False):
    st.markdown(
        """
**Llaves utilizadas por los dashboards**

- `datos_fisiologicos.id` → **PK** del paciente (género, edad, práctica de ejercicio, peso, estatura y variables respiratorias).
- `calculo_simd.id` → **PK** del resultado; `calculo_simd.paciente_id` → **FK** hacia `datos_fisiologicos.id` (relación 1:N).
- `calculo_misd.id` → **PK** del resultado; `calculo_misd.paciente_id` → **FK** hacia `datos_fisiologicos.id` (relación 1:N).
- `calculo_mimd_etapas.id` → **PK** del resultado; `calculo_mimd_etapas.paciente_id` → **FK** hacia `datos_fisiologicos.id`; `etapa` indica qué métrica calculó ese tercio del dataset (1:N).

```
datos_fisiologicos (PK id)
        │ 1
        ├──────────< N  calculo_simd  (PK id, FK paciente_id)
        ├──────────< N  calculo_misd  (PK id, FK paciente_id)
        └──────────< N  calculo_mimd_etapas  (PK id, FK paciente_id, etapa)
```

El **INNER JOIN** por la FK es lo que permite mostrar el **género**, la **edad** y la
**práctica de ejercicio** de cada paciente junto a sus resultados.

`mimd.py` divide el dataset en tres tercios: el primero calcula IMC, el segundo la
relación SpO₂/FiO₂ y el tercero la ventilación por minuto. Por eso `calculo_mimd_etapas`
guarda una fila por paciente y etapa, y solo la métrica de esa etapa tiene valor.
        """
    )

    try:
        integridad = cargar_integridad()
        mimd_disponible = bool(integridad.get("mimd_disponible"))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Pacientes (PK)", f"{int(integridad['pacientes']):,}")
        c2.metric("Filas en calculo_simd", f"{int(integridad['filas_simd']):,}")
        c3.metric("Filas en calculo_misd", f"{int(integridad['filas_misd']):,}")
        c4.metric(
            "Filas en calculo_mimd_etapas",
            f"{int(integridad['filas_mimd']):,}" if mimd_disponible else "—",
        )
        c5.metric(
            "Pacientes con resultado MIMD",
            f"{int(integridad['pacientes_mimd']):,}" if mimd_disponible else "—",
        )

        c6, c7, c8, c9 = st.columns(4)
        c6.metric("SIMD sin paciente (FK rota)", f"{int(integridad['huerfanos_simd']):,}")
        c7.metric("MISD sin paciente (FK rota)", f"{int(integridad['huerfanos_misd']):,}")
        c8.metric(
            "MIMD sin paciente (FK rota)",
            f"{int(integridad['huerfanos_mimd']):,}" if mimd_disponible else "—",
        )
        c9.metric(
            "Pacientes MIMD en >1 etapa",
            f"{int(integridad['multi_etapa_mimd']):,}" if mimd_disponible else "—",
        )

        huerfanos = sum(
            int(integridad[clave])
            for clave in ("huerfanos_simd", "huerfanos_misd", "huerfanos_mimd")
        )
        if huerfanos:
            st.warning(
                "Existen resultados cuya FK `paciente_id` no coincide con ningún "
                "`datos_fisiologicos.id`; esos registros no aparecen en los dashboards."
            )
        if mimd_disponible and int(integridad["multi_etapa_mimd"]):
            st.warning(
                "Hay pacientes con resultados en más de una etapa MIMD. El dashboard "
                "muestra todas las filas; revisa la asignación de tercios en `mimd.py`."
            )
        if not mimd_disponible:
            st.info(
                "La tabla `calculo_mimd_etapas` todavía no existe. Ejecute "
                "`python mimd.py` para generar los resultados MIMD."
            )
    except Exception as error:
        st.info(f"No fue posible calcular la integridad referencial: {error}")


# ==========================================
# 7. FILTROS COMPARTIDOS
# ==========================================

def filtros_pacientes(
    df: pd.DataFrame,
    clave: str,
    incluir_categoria_imc: bool = True,
    incluir_etapa: bool = False,
) -> pd.DataFrame:
    """Filtros por los datos que aporta la FK: género, edad y ejercicio.

    En MIMD se sustituye la categoría de IMC (solo existe en un tercio de las
    filas) por un filtro de etapa.
    """
    generos = sorted(df["genero_desc"].unique().tolist())
    ejercicios = [e for e in ["Sí", "No", "Sin dato"] if e in set(df["ejercicio_desc"])]

    categorias_sel = None
    etapas_sel = None

    with st.expander("🎛️ Filtros de pacientes", expanded=True):
        columna_izq, columna_der = st.columns(2)

        with columna_izq:
            generos_sel = st.multiselect(
                "Género",
                options=generos,
                default=generos,
                key=f"genero_{clave}",
            )
            ejercicios_sel = st.multiselect(
                "Práctica de ejercicio",
                options=ejercicios,
                default=ejercicios,
                key=f"ejercicio_{clave}",
            )
            if incluir_etapa and "etapa" in df.columns:
                etapas = [e for e in ETAPAS_MIMD if e in set(df["etapa"])]
                etapas_sel = st.multiselect(
                    "Etapa MIMD",
                    options=etapas,
                    default=etapas,
                    format_func=lambda etapa: ETIQUETAS_ETAPA_MIMD.get(etapa, etapa),
                    key=f"etapa_{clave}",
                )
            elif incluir_categoria_imc:
                categorias = [
                    c
                    for c in CATEGORIAS_IMC
                    if c in set(df["categoria_imc"].astype(str))
                ]
                categorias_sel = st.multiselect(
                    "Categoría de IMC",
                    options=categorias,
                    default=categorias,
                    key=f"categoria_{clave}",
                )

        with columna_der:
            rango_edad = slider_rango(
                "Rango de edad (años)",
                *rango_entero(df["edad"]),
                clave=f"edad_{clave}",
            )
            rango_id = slider_rango(
                "Rango de ID de paciente (PK)",
                *rango_entero(df["paciente_id"]),
                clave=f"id_{clave}",
            )

    mascara = (
        df["genero_desc"].isin(generos_sel)
        & df["ejercicio_desc"].isin(ejercicios_sel)
        & df["edad"].between(rango_edad[0], rango_edad[1])
        & df["paciente_id"].between(rango_id[0], rango_id[1])
    )
    if categorias_sel is not None:
        mascara &= df["categoria_imc"].astype(str).isin(categorias_sel)
    if etapas_sel is not None:
        mascara &= df["etapa"].isin(etapas_sel)

    filtrado = df[mascara].copy()

    st.caption(
        f"Mostrando **{len(filtrado):,}** de **{len(df):,}** registros "
        f"({len(filtrado) / len(df) * 100:.1f}% del total)."
    )
    return filtrado


def tabla_resumen(df: pd.DataFrame, columnas_extra: dict) -> pd.DataFrame:
    """Resumen descriptivo por género y práctica de ejercicio."""
    agregaciones = {
        "Pacientes": ("paciente_id", "size"),
        "Edad promedio": ("edad", "mean"),
        "IMC promedio": ("imc", "mean"),
    }
    agregaciones.update(columnas_extra)

    resumen = (
        df.groupby(["genero_desc", "ejercicio_desc"], observed=True)
        .agg(**agregaciones)
        .reset_index()
        .rename(columns={"genero_desc": "Género", "ejercicio_desc": "Practica ejercicio"})
    )

    for columna in resumen.columns:
        if columna not in ("Género", "Practica ejercicio", "Pacientes"):
            resumen[columna] = resumen[columna].round(2)

    return resumen


def descargar_csv(tabla: pd.DataFrame, nombre: str, clave: str) -> None:
    st.download_button(
        label="📥 Descargar resultados en CSV",
        data=tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name=nombre,
        mime="text/csv",
        key=f"csv_{clave}",
    )


def barras_promedio(
    df: pd.DataFrame,
    columna: str,
    titulo: str,
    etiqueta_x: str,
    color_map: dict,
    categoria: str = "imc",
    etiqueta_y: str = "IMC promedio",
) -> None:
    resumen = (
        df.groupby(columna, observed=True, as_index=False)
        .agg(promedio=(categoria, "mean"), pacientes=(categoria, "size"))
    )

    fig = px.bar(
        resumen,
        x=columna,
        y="promedio",
        color=columna,
        color_discrete_map=color_map,
        text_auto=".2f",
        title=titulo,
        labels={columna: etiqueta_x, "promedio": etiqueta_y, "pacientes": "Pacientes"},
        hover_data={"pacientes": True},
    )
    fig.update_layout(showlegend=False, yaxis_title=etiqueta_y, xaxis_title=etiqueta_x)
    st.plotly_chart(fig, width="stretch")


# ==========================================
# 8. DASHBOARD SIMD (main.py)
# ==========================================

def render_dashboard_simd(datos: pd.DataFrame, error: str | None, unidad: str) -> None:
    st.subheader("SIMD secuencial · `main.py`")
    st.caption(
        "Un único flujo de procesamiento calcula el IMC de los 5 001 registros. "
        "La tabla `calculo_simd` guarda el resultado por paciente y se une por FK con "
        "`datos_fisiologicos` para incorporar género, edad y práctica de ejercicio."
    )

    if error:
        st.error(f"Error de conexión con la base de datos MySQL: {error}")
        return

    if datos.empty:
        st.info(
            "No existen resultados en `calculo_simd`. Ejecute primero "
            "`python main.py` para realizar el procesamiento SIMD."
        )
        return

    filtrados = filtros_pacientes(datos, "simd")
    if filtrados.empty:
        st.warning("Ningún registro coincide con los filtros seleccionados.")
        return

    simbolo, _ = UNIDADES_TIEMPO[unidad]
    tiempo_us = float(filtrados["tiempo_microsegundos"].max())
    con_ejercicio = filtrados[filtrados["ejercicio_desc"] == "Sí"]
    sin_ejercicio = filtrados[filtrados["ejercicio_desc"] == "No"]

    # ---------- Indicadores ----------
    st.markdown("#### Indicadores generales")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Registros", f"{len(filtrados):,}")
    col2.metric("Pacientes únicos (PK)", f"{filtrados['paciente_id'].nunique():,}")
    col3.metric("IMC promedio", f"{filtrados['imc'].mean():.2f}")
    col4.metric("IMC mínimo", f"{filtrados['imc'].min():.2f}")
    col5.metric("IMC máximo", f"{filtrados['imc'].max():.2f}")

    col6, col7, col8, col9, col10 = st.columns(5)
    col6.metric("Edad promedio", f"{filtrados['edad'].mean():.1f} años")
    col7.metric(
        "Practica ejercicio",
        f"{(filtrados['ejercicio_desc'] == 'Sí').mean() * 100:.1f} %",
    )
    col8.metric(
        "IMC con ejercicio",
        f"{con_ejercicio['imc'].mean():.2f}" if not con_ejercicio.empty else "—",
    )
    col9.metric(
        "IMC sin ejercicio",
        f"{sin_ejercicio['imc'].mean():.2f}" if not sin_ejercicio.empty else "—",
    )
    col10.metric("Tiempo del run SIMD", formatear_tiempo(tiempo_us, unidad))
    st.caption(
        f"El tiempo se registra una sola vez por ejecución, por eso es idéntico en los "
        f"{len(datos):,} registros procesados (valor mostrado: {tiempo_us:,.2f} µs)."
    )

    # ---------- Graficos ----------
    st.markdown("#### Distribución del IMC y perfil de los pacientes")

    columna_a, columna_b = st.columns(2)

    with columna_a:
        fig_hist = px.histogram(
            filtrados,
            x="imc",
            color="categoria_imc",
            nbins=30,
            title="Distribución del IMC por categoría (OMS)",
            labels={"imc": "Índice de Masa Corporal (IMC)", "count": "Pacientes"},
            color_discrete_map=COLOR_CATEGORIA_IMC,
            category_orders={"categoria_imc": CATEGORIAS_IMC},
        )
        fig_hist.update_layout(
            yaxis_title="Cantidad de pacientes",
            xaxis_title="Índice de Masa Corporal (IMC)",
            legend_title="Categoría",
        )
        st.plotly_chart(fig_hist, width="stretch")

    with columna_b:
        barras_promedio(
            filtrados,
            columna="genero_desc",
            titulo="IMC promedio por género",
            etiqueta_x="Género",
            color_map=COLOR_GENERO,
        )

    columna_c, columna_d = st.columns(2)

    with columna_c:
        barras_promedio(
            filtrados,
            columna="ejercicio_desc",
            titulo="IMC promedio según práctica de ejercicio",
            etiqueta_x="Practica ejercicio",
            color_map=COLOR_EJERCICIO,
        )

    with columna_d:
        fig_dispersion = px.scatter(
            filtrados,
            x="edad",
            y="imc",
            color="genero_desc",
            symbol="ejercicio_desc",
            opacity=0.55,
            render_mode="webgl",
            title="IMC vs. edad (color = género, símbolo = ejercicio)",
            labels={
                "edad": "Edad (años)",
                "imc": "IMC",
                "genero_desc": "Género",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_GENERO,
        )
        fig_dispersion.update_traces(marker={"size": 7})
        st.plotly_chart(fig_dispersion, width="stretch")

    columna_e, columna_f = st.columns(2)

    with columna_e:
        fig_barnorm = px.histogram(
            filtrados,
            x="genero_desc",
            color="categoria_imc",
            barnorm="percent",
            text_auto=".1f",
            title="Composición porcentual del IMC por género",
            labels={"genero_desc": "Género", "categoria_imc": "Categoría"},
            color_discrete_map=COLOR_CATEGORIA_IMC,
            category_orders={
                "categoria_imc": CATEGORIAS_IMC,
                "genero_desc": ["Masculino", "Femenino", "Sin dato"],
            },
        )
        fig_barnorm.update_layout(
            yaxis_title="Porcentaje de pacientes (%)",
            xaxis_title="Género",
            legend_title="Categoría",
        )
        st.plotly_chart(fig_barnorm, width="stretch")

    with columna_f:
        fig_caja = px.box(
            filtrados,
            x="ejercicio_desc",
            y="imc",
            color="genero_desc",
            points=False,
            title="Dispersión del IMC por ejercicio y género",
            labels={
                "ejercicio_desc": "Practica ejercicio",
                "imc": "IMC",
                "genero_desc": "Género",
            },
            color_discrete_map=COLOR_GENERO,
            category_orders={"ejercicio_desc": ["Sí", "No", "Sin dato"]},
        )
        fig_caja.update_layout(boxmode="group")
        st.plotly_chart(fig_caja, width="stretch")

    # ---------- Resumen por grupos ----------
    st.markdown("#### Resumen por género y práctica de ejercicio")
    resumen = tabla_resumen(
        filtrados,
        {"IMC mínimo": ("imc", "min"), "IMC máximo": ("imc", "max")},
    )
    st.dataframe(
        resumen,
        width="stretch",
        hide_index=True,
        column_config={
            "Edad promedio": st.column_config.NumberColumn(format="%.1f"),
            "IMC promedio": st.column_config.NumberColumn(format="%.2f"),
            "IMC mínimo": st.column_config.NumberColumn(format="%.2f"),
            "IMC máximo": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    # ---------- Tabla detallada ----------
    st.markdown("#### Resultados almacenados en MySQL (`calculo_simd`)")

    tabla = filtrados[
        [
            "paciente_id", "genero_desc", "edad", "ejercicio_desc",
            "peso_kg", "estatura_m", "imc", "categoria_imc",
            "fecha_procesamiento",
        ]
    ].copy()

    tabla.insert(
        len(tabla.columns) - 1,
        "tiempo_mostrado",
        filtrados["tiempo_microsegundos"] * UNIDADES_TIEMPO[unidad][1],
    )

    tabla = tabla.rename(
        columns={
            "paciente_id": "ID del paciente (PK/FK)",
            "genero_desc": "Género",
            "edad": "Edad (años)",
            "ejercicio_desc": "Practica ejercicio",
            "peso_kg": "Peso (kg)",
            "estatura_m": "Estatura (m)",
            "imc": "IMC",
            "categoria_imc": "Categoría IMC",
            "tiempo_mostrado": f"Tiempo ({simbolo})",
            "fecha_procesamiento": "Fecha del procesamiento",
        }
    )

    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config={
            "ID del paciente (PK/FK)": st.column_config.NumberColumn(format="%d"),
            "Edad (años)": st.column_config.NumberColumn(format="%d"),
            "Peso (kg)": st.column_config.NumberColumn(format="%.2f"),
            "Estatura (m)": st.column_config.NumberColumn(format="%.2f"),
            "IMC": st.column_config.NumberColumn(format="%.2f"),
            f"Tiempo ({simbolo})": st.column_config.NumberColumn(format="%.4f"),
            "Fecha del procesamiento": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm:ss"
            ),
        },
    )

    descargar_csv(tabla, "resultados_simd_imc.csv", "simd")


# ==========================================
# 9. DASHBOARD MISD (misd.py)
# ==========================================

def render_dashboard_misd(datos: pd.DataFrame, error: str | None, unidad: str) -> None:
    st.subheader("MISD multihilo · `misd.py`")
    st.caption(
        "Cuatro hilos calculan en paralelo IMC, relación SpO₂/FiO₂, ventilación "
        "minuto (ml/min) y su conversión a L/min. `calculo_misd` guarda una fila por "
        "ejecución, por lo que aquí se muestra el **último cálculo de cada paciente** "
        "(MAX(id) por `paciente_id`)."
    )

    if error:
        st.error(f"Error de conexión con la base de datos MySQL: {error}")
        return

    if datos.empty:
        st.info(
            "No existen resultados en `calculo_misd`. Ejecute primero "
            "`python misd.py` para realizar el procesamiento MISD."
        )
        return

    filtrados = filtros_pacientes(datos, "misd")
    if filtrados.empty:
        st.warning("Ningún registro coincide con los filtros seleccionados.")
        return

    simbolo, _ = UNIDADES_TIEMPO[unidad]
    tiempo_us = float(filtrados["tiempo_microsegundos"].max())
    con_ejercicio = filtrados[filtrados["ejercicio_desc"] == "Sí"]
    sin_ejercicio = filtrados[filtrados["ejercicio_desc"] == "No"]

    # ---------- Indicadores ----------
    st.markdown("#### Indicadores generales")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Pacientes con resultado", f"{len(filtrados):,}")
    col2.metric("IMC promedio", f"{filtrados['imc'].mean():.2f}")
    col3.metric("Relación SpO₂/FiO₂ promedio", f"{filtrados['relacion_sf'].mean():.1f}")
    col4.metric("Ventilación promedio", f"{filtrados['ventilacion_l_min'].mean():.2f} L/min")
    col5.metric("Tiempo del run MISD", formatear_tiempo(tiempo_us, unidad))

    col6, col7, col8, col9, col10 = st.columns(5)
    col6.metric("Edad promedio", f"{filtrados['edad'].mean():.1f} años")
    col7.metric(
        "Practica ejercicio",
        f"{(filtrados['ejercicio_desc'] == 'Sí').mean() * 100:.1f} %",
    )
    col8.metric(
        "Relación S/F con ejercicio",
        f"{con_ejercicio['relacion_sf'].mean():.1f}" if not con_ejercicio.empty else "—",
    )
    col9.metric(
        "Relación S/F sin ejercicio",
        f"{sin_ejercicio['relacion_sf'].mean():.1f}" if not sin_ejercicio.empty else "—",
    )
    col10.metric("SpO₂ promedio", f"{filtrados['spo2_pct'].mean():.2f} %")
    st.caption(
        "IMC = peso / estatura² · Relación S/F = SpO₂ / FiO₂ · "
        "Ventilación = volumen corriente × frecuencia respiratoria. "
        f"El tiempo multihilo es idéntico en todos los registros de una ejecución "
        f"({tiempo_us:,.2f} µs)."
    )

    # ---------- Graficos ----------
    st.markdown("#### Indicadores respiratorios y perfil de los pacientes")

    columna_a, columna_b = st.columns(2)

    with columna_a:
        fig_hist = px.histogram(
            filtrados,
            x="relacion_sf",
            color="ejercicio_desc",
            nbins=30,
            title="Distribución de la relación SpO₂/FiO₂ según ejercicio",
            labels={
                "relacion_sf": "Relación SpO₂/FiO₂",
                "count": "Pacientes",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_EJERCICIO,
            category_orders={"ejercicio_desc": ["Sí", "No", "Sin dato"]},
        )
        fig_hist.update_layout(
            yaxis_title="Cantidad de pacientes",
            xaxis_title="Relación SpO₂/FiO₂",
            legend_title="Practica ejercicio",
        )
        st.plotly_chart(fig_hist, width="stretch")

    with columna_b:
        imc_grupo = (
            filtrados.groupby(["genero_desc", "ejercicio_desc"], observed=True, as_index=False)
            .agg(promedio=("imc", "mean"), pacientes=("imc", "size"))
        )
        fig_imc = px.bar(
            imc_grupo,
            x="genero_desc",
            y="promedio",
            color="ejercicio_desc",
            barmode="group",
            text_auto=".2f",
            title="IMC promedio por género y práctica de ejercicio",
            labels={
                "genero_desc": "Género",
                "promedio": "IMC promedio",
                "ejercicio_desc": "Practica ejercicio",
                "pacientes": "Pacientes",
            },
            color_discrete_map=COLOR_EJERCICIO,
            category_orders={
                "genero_desc": ["Masculino", "Femenino", "Sin dato"],
                "ejercicio_desc": ["Sí", "No", "Sin dato"],
            },
            hover_data={"pacientes": True},
        )
        fig_imc.update_layout(legend_title="Practica ejercicio")
        st.plotly_chart(fig_imc, width="stretch")

    columna_c, columna_d = st.columns(2)

    with columna_c:
        fig_dispersion = px.scatter(
            filtrados,
            x="edad",
            y="relacion_sf",
            color="genero_desc",
            symbol="ejercicio_desc",
            opacity=0.55,
            render_mode="webgl",
            title="Relación SpO₂/FiO₂ vs. edad (color = género, símbolo = ejercicio)",
            labels={
                "edad": "Edad (años)",
                "relacion_sf": "Relación SpO₂/FiO₂",
                "genero_desc": "Género",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_GENERO,
        )
        fig_dispersion.update_traces(marker={"size": 7})
        st.plotly_chart(fig_dispersion, width="stretch")

    with columna_d:
        barras_promedio(
            filtrados,
            columna="ejercicio_desc",
            titulo="Ventilación promedio según práctica de ejercicio",
            etiqueta_x="Practica ejercicio",
            color_map=COLOR_EJERCICIO,
            categoria="ventilacion_l_min",
            etiqueta_y="Ventilación promedio (L/min)",
        )

    columna_e, columna_f = st.columns(2)

    with columna_e:
        fig_caja = px.box(
            filtrados,
            x="grupo_etario",
            y="ventilacion_l_min",
            color="ejercicio_desc",
            points=False,
            title="Ventilación (L/min) por grupo de edad y ejercicio",
            labels={
                "grupo_etario": "Grupo de edad (años)",
                "ventilacion_l_min": "Ventilación (L/min)",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_EJERCICIO,
            category_orders={
                "grupo_etario": ["18-29", "30-44", "45-59", "60-74", "75+"],
                "ejercicio_desc": ["Sí", "No", "Sin dato"],
            },
        )
        fig_caja.update_layout(boxmode="group", xaxis={"tickangle": -30})
        st.plotly_chart(fig_caja, width="stretch")

    with columna_f:
        columnas_numericas = [
            "edad", "peso_kg", "estatura_m", "imc", "spo2_pct", "fio2",
            "relacion_sf", "volumen_corriente_ml", "frecuencia_respiratoria_rpm",
            "ventilacion_l_min",
        ]
        columnas_numericas = [c for c in columnas_numericas if c in filtrados.columns]
        correlacion = (
            filtrados[columnas_numericas]
            .corr(numeric_only=True)
            .rename(index=ETIQUETAS_NUMERICAS, columns=ETIQUETAS_NUMERICAS)
        )

        fig_correlacion = px.imshow(
            correlacion,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            aspect="auto",
            title="Matriz de correlación de las variables calculadas",
        )
        fig_correlacion.update_layout(height=520)
        st.plotly_chart(fig_correlacion, width="stretch")

    # ---------- Resumen por grupos ----------
    st.markdown("#### Resumen por género y práctica de ejercicio")
    resumen = tabla_resumen(
        filtrados,
        {
            "Relación SpO₂/FiO₂": ("relacion_sf", "mean"),
            "Ventilación (L/min)": ("ventilacion_l_min", "mean"),
            "SpO₂ (%)": ("spo2_pct", "mean"),
        },
    )
    st.dataframe(
        resumen,
        width="stretch",
        hide_index=True,
        column_config={
            "Edad promedio": st.column_config.NumberColumn(format="%.1f"),
            "IMC promedio": st.column_config.NumberColumn(format="%.2f"),
            "Relación SpO₂/FiO₂": st.column_config.NumberColumn(format="%.2f"),
            "Ventilación (L/min)": st.column_config.NumberColumn(format="%.2f"),
            "SpO₂ (%)": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    # ---------- Tabla detallada ----------
    st.markdown("#### Resultados almacenados en MySQL (`calculo_misd`)")

    tabla = filtrados[
        [
            "paciente_id", "genero_desc", "edad", "ejercicio_desc",
            "imc", "categoria_imc", "relacion_sf", "spo2_pct", "fio2",
            "volumen_corriente_ml", "frecuencia_respiratoria_rpm",
            "ventilacion_ml_min", "ventilacion_l_min",
            "fecha_procesamiento",
        ]
    ].copy()

    tabla.insert(
        len(tabla.columns) - 1,
        "tiempo_mostrado",
        filtrados["tiempo_microsegundos"] * UNIDADES_TIEMPO[unidad][1],
    )

    tabla = tabla.rename(
        columns={
            "paciente_id": "ID del paciente (PK/FK)",
            "genero_desc": "Género",
            "edad": "Edad (años)",
            "ejercicio_desc": "Practica ejercicio",
            "imc": "IMC",
            "categoria_imc": "Categoría IMC",
            "relacion_sf": "Relación SpO₂/FiO₂",
            "spo2_pct": "SpO₂ (%)",
            "fio2": "FiO₂",
            "volumen_corriente_ml": "Volumen corriente (ml)",
            "frecuencia_respiratoria_rpm": "Frec. respiratoria (rpm)",
            "ventilacion_ml_min": "Ventilación (ml/min)",
            "ventilacion_l_min": "Ventilación (L/min)",
            "tiempo_mostrado": f"Tiempo ({simbolo})",
            "fecha_procesamiento": "Fecha del procesamiento",
        }
    )

    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config={
            "ID del paciente (PK/FK)": st.column_config.NumberColumn(format="%d"),
            "Edad (años)": st.column_config.NumberColumn(format="%d"),
            "IMC": st.column_config.NumberColumn(format="%.2f"),
            "Relación SpO₂/FiO₂": st.column_config.NumberColumn(format="%.2f"),
            "SpO₂ (%)": st.column_config.NumberColumn(format="%.1f"),
            "FiO₂": st.column_config.NumberColumn(format="%.2f"),
            "Volumen corriente (ml)": st.column_config.NumberColumn(format="%d"),
            "Frec. respiratoria (rpm)": st.column_config.NumberColumn(format="%d"),
            "Ventilación (ml/min)": st.column_config.NumberColumn(format="%.0f"),
            "Ventilación (L/min)": st.column_config.NumberColumn(format="%.2f"),
            f"Tiempo ({simbolo})": st.column_config.NumberColumn(format="%.4f"),
            "Fecha del procesamiento": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm:ss"
            ),
        },
    )

    descargar_csv(tabla, "resultados_misd.csv", "misd")


# ==========================================
# 10. DASHBOARD MIMD (mimd.py)
# ==========================================

def render_dashboard_mimd(datos: pd.DataFrame, error: str | None, unidad: str) -> None:
    st.subheader("MIMD por etapas · `mimd.py`")
    st.caption(
        "Tres hilos dividen el dataset en tercios: un tercio calcula IMC, otro la "
        "relación SpO₂/FiO₂ y otro la ventilación por minuto. Cada paciente aparece "
        "una sola vez, en la etapa que le correspondió, dentro de "
        "`calculo_mimd_etapas`; el tiempo se registra por etapa."
    )

    if error:
        st.error(f"Error de conexión con la base de datos MySQL: {error}")
        return

    if datos.empty:
        st.info(
            "No existen resultados en `calculo_mimd_etapas`. Ejecute primero "
            "`python mimd.py` para realizar el procesamiento MIMD."
        )
        return

    filtrados = filtros_pacientes(
        datos, "mimd", incluir_categoria_imc=False, incluir_etapa=True
    )
    if filtrados.empty:
        st.warning("Ningún registro coincide con los filtros seleccionados.")
        return

    simbolo, factor = UNIDADES_TIEMPO[unidad]
    etapas_presentes = [e for e in ETAPAS_MIMD if e in set(filtrados["etapa"])]
    tiempos_etapa = (
        filtrados.groupby("etapa", observed=True)["tiempo_microsegundos"].max()
    )

    if tiempos_etapa.empty:
        suma_tiempos = "—"
        tiempo_medio = "—"
        etapa_lenta = "—"
    else:
        suma_tiempos = formatear_tiempo(float(tiempos_etapa.sum()), unidad)
        tiempo_medio = formatear_tiempo(float(tiempos_etapa.mean()), unidad)
        etapa_mas_lenta = str(tiempos_etapa.idxmax())
        etapa_lenta = ETIQUETAS_ETAPA_MIMD.get(etapa_mas_lenta, etapa_mas_lenta)

    def subconjunto_etapa(etapa: str) -> pd.DataFrame:
        if "etapa" not in filtrados.columns:
            return filtrados.iloc[0:0]
        return filtrados[filtrados["etapa"] == etapa]

    sub_imc = subconjunto_etapa("IMC")
    sub_sf = subconjunto_etapa("RELACION_SF")
    sub_vent = subconjunto_etapa("VENTILACION")

    # ---------- Indicadores ----------
    st.markdown("#### Indicadores generales")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Pacientes con resultado", f"{filtrados['paciente_id'].nunique():,}")
    col2.metric("Etapas registradas", f"{filtrados['etapa'].nunique()}")
    col3.metric("IMC promedio (etapa IMC)", promediar(sub_imc["imc"]))
    col4.metric(
        "Relación S/F promedio (su etapa)",
        promediar(sub_sf["relacion_sf"], 1),
    )
    col5.metric(
        "Ventilación promedio (su etapa)",
        promediar(sub_vent["ventilacion_l_min"], 2, " L/min"),
    )

    col6, col7, col8, col9, col10 = st.columns(5)
    col6.metric("Edad promedio", f"{filtrados['edad'].mean():.1f} años")
    col7.metric(
        "Practica ejercicio",
        f"{(filtrados['ejercicio_desc'] == 'Sí').mean() * 100:.1f} %",
    )
    col8.metric("Suma de tiempos por etapa", suma_tiempos)
    col9.metric("Tiempo medio por etapa", tiempo_medio)
    col10.metric("Etapa más lenta", etapa_lenta)

    st.caption(
        "Cada tercio calcula una métrica distinta: los promedios de IMC, S/F y "
        "ventilación usan solo los pacientes de su etapa. La **suma de tiempos** "
        "corresponde a las etapas mostradas y **no es un tiempo de pared**: "
        "`mimd.py` almacena el tiempo de cada etapa, no el total del run. "
        f"Etapas incluidas: {', '.join(etapas_presentes)}."
    )

    # ---------- Graficos ----------
    st.markdown("#### Distribución por etapa y perfil de los pacientes")

    columna_a, columna_b = st.columns(2)

    with columna_a:
        conteo = (
            filtrados.groupby(
                ["etapa_desc", "ejercicio_desc"], observed=True, as_index=False
            )
            .agg(Pacientes=("paciente_id", "size"))
        )
        fig_conteo = px.bar(
            conteo,
            x="etapa_desc",
            y="Pacientes",
            color="ejercicio_desc",
            barmode="group",
            text_auto=True,
            title="Pacientes por etapa MIMD y práctica de ejercicio",
            labels={
                "etapa_desc": "Etapa MIMD",
                "Pacientes": "Pacientes",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_EJERCICIO,
            category_orders={
                "etapa_desc": [ETIQUETAS_ETAPA_MIMD[e] for e in ETAPAS_MIMD],
                "ejercicio_desc": ["Sí", "No", "Sin dato"],
            },
        )
        fig_conteo.update_layout(
            xaxis_title="Etapa MIMD",
            yaxis_title="Pacientes",
            legend_title="Practica ejercicio",
        )
        st.plotly_chart(fig_conteo, width="stretch")

    with columna_b:
        if tiempos_etapa.empty:
            st.info("No hay tiempos por etapa para los filtros actuales.")
        else:
            tiempos = tiempos_etapa.reset_index()
            tiempos["etapa_desc"] = tiempos["etapa"].map(ETIQUETAS_ETAPA_MIMD)
            tiempos["tiempo_mostrado"] = tiempos["tiempo_microsegundos"] * factor
            fig_tiempos = px.bar(
                tiempos,
                x="etapa_desc",
                y="tiempo_mostrado",
                color="etapa_desc",
                text_auto=".4f",
                title=f"Tiempo de procesamiento por etapa ({simbolo})",
                labels={
                    "etapa_desc": "Etapa MIMD",
                    "tiempo_mostrado": f"Tiempo ({simbolo})",
                },
                color_discrete_sequence=["#2E86DE", "#27AE60", "#8E44AD"],
                category_orders={
                    "etapa_desc": [ETIQUETAS_ETAPA_MIMD[e] for e in ETAPAS_MIMD]
                },
            )
            fig_tiempos.update_layout(showlegend=False)
            st.plotly_chart(fig_tiempos, width="stretch")
            st.caption(
                "En `mimd.py` cada etapa guarda un único tiempo de ejecución, "
                "repetido en las filas de su tercio."
            )

    def histograma_etapa(
        subconjunto: pd.DataFrame,
        columna: str,
        titulo: str,
        etiqueta_x: str,
    ) -> None:
        if subconjunto.empty or subconjunto[columna].dropna().empty:
            st.info("No hay datos de esta etapa con los filtros actuales.")
            return
        fig_hist = px.histogram(
            subconjunto,
            x=columna,
            color="ejercicio_desc",
            nbins=30,
            title=titulo,
            labels={
                columna: etiqueta_x,
                "count": "Pacientes",
                "ejercicio_desc": "Practica ejercicio",
            },
            color_discrete_map=COLOR_EJERCICIO,
            category_orders={"ejercicio_desc": ["Sí", "No", "Sin dato"]},
        )
        fig_hist.update_layout(
            yaxis_title="Cantidad de pacientes",
            xaxis_title=etiqueta_x,
            legend_title="Practica ejercicio",
        )
        st.plotly_chart(fig_hist, width="stretch")

    columna_c, columna_d = st.columns(2)

    with columna_c:
        histograma_etapa(
            sub_imc,
            "imc",
            "IMC en la etapa IMC según práctica de ejercicio",
            "Índice de Masa Corporal (IMC)",
        )

    with columna_d:
        histograma_etapa(
            sub_sf,
            "relacion_sf",
            "Relación SpO₂/FiO₂ en su etapa según práctica de ejercicio",
            "Relación SpO₂/FiO₂",
        )

    columna_e, columna_f = st.columns(2)

    with columna_e:
        if sub_vent.empty or sub_vent["ventilacion_l_min"].dropna().empty:
            st.info("No hay datos de la etapa de ventilación con los filtros actuales.")
        else:
            fig_caja = px.box(
                sub_vent,
                x="grupo_etario",
                y="ventilacion_l_min",
                color="ejercicio_desc",
                points=False,
                title="Ventilación (L/min) por grupo de edad y ejercicio (etapa ventilación)",
                labels={
                    "grupo_etario": "Grupo de edad (años)",
                    "ventilacion_l_min": "Ventilación (L/min)",
                    "ejercicio_desc": "Practica ejercicio",
                },
                color_discrete_map=COLOR_EJERCICIO,
                category_orders={
                    "grupo_etario": ["18-29", "30-44", "45-59", "60-74", "75+"],
                    "ejercicio_desc": ["Sí", "No", "Sin dato"],
                },
            )
            fig_caja.update_layout(boxmode="group", xaxis={"tickangle": -30})
            st.plotly_chart(fig_caja, width="stretch")

    with columna_f:
        if sub_imc.empty or sub_imc["imc"].dropna().empty:
            st.info("No hay datos de la etapa IMC con los filtros actuales.")
        else:
            fig_dispersion = px.scatter(
                sub_imc,
                x="edad",
                y="imc",
                color="genero_desc",
                symbol="ejercicio_desc",
                opacity=0.55,
                render_mode="webgl",
                title="IMC vs. edad en la etapa IMC (color = género, símbolo = ejercicio)",
                labels={
                    "edad": "Edad (años)",
                    "imc": "IMC",
                    "genero_desc": "Género",
                    "ejercicio_desc": "Practica ejercicio",
                },
                color_discrete_map=COLOR_GENERO,
            )
            fig_dispersion.update_traces(marker={"size": 7})
            st.plotly_chart(fig_dispersion, width="stretch")

    # ---------- Resumen por etapa ----------
    st.markdown("#### Resumen por etapa")
    filas_etapa = []
    for etapa in etapas_presentes:
        subconjunto = subconjunto_etapa(etapa)
        columna, nombre_metrica, unidad_metrica, _ = METRICAS_ETAPA_MIMD[etapa]
        serie = pd.to_numeric(subconjunto[columna], errors="coerce").dropna()
        filas_etapa.append(
            {
                "Etapa": ETIQUETAS_ETAPA_MIMD.get(etapa, etapa),
                "Métrica": nombre_metrica,
                "Unidad": unidad_metrica,
                "Pacientes": len(subconjunto),
                "ID mínimo": int(subconjunto["paciente_id"].min()),
                "ID máximo": int(subconjunto["paciente_id"].max()),
                "Media": serie.mean() if not serie.empty else None,
                "Mínimo": serie.min() if not serie.empty else None,
                "Máximo": serie.max() if not serie.empty else None,
                f"Tiempo ({simbolo})": (
                    float(subconjunto["tiempo_microsegundos"].max()) * factor
                ),
            }
        )

    if filas_etapa:
        st.dataframe(
            pd.DataFrame(filas_etapa),
            width="stretch",
            hide_index=True,
            column_config={
                "Pacientes": st.column_config.NumberColumn(format="%d"),
                "ID mínimo": st.column_config.NumberColumn(format="%d"),
                "ID máximo": st.column_config.NumberColumn(format="%d"),
                "Media": st.column_config.NumberColumn(format="%.2f"),
                "Mínimo": st.column_config.NumberColumn(format="%.2f"),
                "Máximo": st.column_config.NumberColumn(format="%.2f"),
                f"Tiempo ({simbolo})": st.column_config.NumberColumn(format="%.4f"),
            },
        )
        st.caption(
            "Cada etapa procesa un tercio del dataset con una instrucción distinta; "
            "la media, el mínimo y el máximo corresponden solo a la métrica de esa etapa."
        )

    # ---------- Resumen por etapa, genero y ejercicio ----------
    st.markdown("#### Resumen por etapa, género y práctica de ejercicio")
    filas_resumen = []
    for (etapa, genero, ejercicio), grupo in filtrados.groupby(
        ["etapa", "genero_desc", "ejercicio_desc"], observed=True
    ):
        columna, nombre_metrica, unidad_metrica, _ = METRICAS_ETAPA_MIMD[etapa]
        serie = pd.to_numeric(grupo[columna], errors="coerce").dropna()
        if serie.empty:
            continue
        filas_resumen.append(
            {
                "Etapa": ETIQUETAS_ETAPA_MIMD.get(etapa, etapa),
                "Género": genero,
                "Practica ejercicio": ejercicio,
                "Pacientes": len(grupo),
                "Edad promedio": grupo["edad"].mean(),
                "Métrica": nombre_metrica,
                "Unidad": unidad_metrica,
                "Media": serie.mean(),
                "Mediana": serie.median(),
                "Mínimo": serie.min(),
                "Máximo": serie.max(),
            }
        )

    resumen = pd.DataFrame(filas_resumen)

    if resumen.empty:
        st.info("No hay datos suficientes para el resumen por grupos.")
    else:
        st.dataframe(
            resumen,
            width="stretch",
            hide_index=True,
            column_config={
                "Pacientes": st.column_config.NumberColumn(format="%d"),
                "Edad promedio": st.column_config.NumberColumn(format="%.1f"),
                "Media": st.column_config.NumberColumn(format="%.2f"),
                "Mediana": st.column_config.NumberColumn(format="%.2f"),
                "Mínimo": st.column_config.NumberColumn(format="%.2f"),
                "Máximo": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption(
            "Cada fila describe únicamente la métrica calculada por su etapa. No se "
            "comparan métricas de etapas distintas en una misma columna."
        )

    # ---------- Tabla detallada ----------
    st.markdown("#### Resultados almacenados en MySQL (`calculo_mimd_etapas`)")

    columnas = [
        "paciente_id", "genero_desc", "edad", "ejercicio_desc", "etapa_desc",
        "peso_kg", "estatura_m", "imc", "relacion_sf", "spo2_pct", "fio2",
        "volumen_corriente_ml", "frecuencia_respiratoria_rpm",
        "ventilacion_ml_min", "ventilacion_l_min", "fecha_procesamiento",
    ]
    columnas = [c for c in columnas if c in filtrados.columns]
    tabla = filtrados[columnas].copy()

    if "fecha_procesamiento" in tabla.columns:
        tabla.insert(
            len(tabla.columns) - 1,
            "tiempo_mostrado",
            filtrados["tiempo_microsegundos"] * factor,
        )
    else:
        tabla["tiempo_mostrado"] = filtrados["tiempo_microsegundos"] * factor

    tabla = tabla.rename(
        columns={
            "paciente_id": "ID del paciente (PK/FK)",
            "genero_desc": "Género",
            "edad": "Edad (años)",
            "ejercicio_desc": "Practica ejercicio",
            "etapa_desc": "Etapa MIMD",
            "peso_kg": "Peso (kg)",
            "estatura_m": "Estatura (m)",
            "imc": "IMC (kg/m²)",
            "relacion_sf": "Relación SpO₂/FiO₂",
            "spo2_pct": "SpO₂ (%)",
            "fio2": "FiO₂",
            "volumen_corriente_ml": "Volumen corriente (ml)",
            "frecuencia_respiratoria_rpm": "Frec. respiratoria (rpm)",
            "ventilacion_ml_min": "Ventilación (ml/min)",
            "ventilacion_l_min": "Ventilación (L/min)",
            "tiempo_mostrado": f"Tiempo ({simbolo})",
            "fecha_procesamiento": "Fecha del procesamiento",
        }
    )

    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config={
            "ID del paciente (PK/FK)": st.column_config.NumberColumn(format="%d"),
            "Edad (años)": st.column_config.NumberColumn(format="%d"),
            "Peso (kg)": st.column_config.NumberColumn(format="%.2f"),
            "Estatura (m)": st.column_config.NumberColumn(format="%.2f"),
            "IMC (kg/m²)": st.column_config.NumberColumn(format="%.2f"),
            "Relación SpO₂/FiO₂": st.column_config.NumberColumn(format="%.2f"),
            "SpO₂ (%)": st.column_config.NumberColumn(format="%.1f"),
            "FiO₂": st.column_config.NumberColumn(format="%.2f"),
            "Volumen corriente (ml)": st.column_config.NumberColumn(format="%d"),
            "Frec. respiratoria (rpm)": st.column_config.NumberColumn(format="%d"),
            "Ventilación (ml/min)": st.column_config.NumberColumn(format="%.0f"),
            "Ventilación (L/min)": st.column_config.NumberColumn(format="%.2f"),
            f"Tiempo ({simbolo})": st.column_config.NumberColumn(format="%.4f"),
            "Fecha del procesamiento": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm:ss"
            ),
        },
    )
    st.caption(
        "Cada fila corresponde a un paciente en una etapa. Solo la columna de la "
        "métrica calculada por esa etapa tiene valor; las demás aparecen vacías."
    )

    descargar_csv(tabla, "resultados_mimd.csv", "mimd")


# ==========================================
# 11. PESTAÑAS
# ==========================================

pestana_simd, pestana_misd, pestana_mimd = st.tabs(
    [
        "📊 Dashboard SIMD · main.py",
        "🧵 Dashboard MISD · misd.py",
        "⚙️ Dashboard MIMD · mimd.py",
    ]
)

with pestana_simd:
    render_dashboard_simd(datos_simd, error_simd, unidad_tiempo)

with pestana_misd:
    render_dashboard_misd(datos_misd, error_misd, unidad_tiempo)

with pestana_mimd:
    render_dashboard_mimd(datos_mimd, error_mimd, unidad_tiempo)

st.divider()
st.caption(
    "Los dashboards consultan `calculo_simd`, `calculo_misd`, "
    "`calculo_mimd_etapas` y `datos_fisiologicos`. Ejecute `python main.py`, "
    "`python misd.py` o `python mimd.py` para generar/actualizar los resultados "
    "y luego use **🔄 Actualizar datos consultados**."
)
