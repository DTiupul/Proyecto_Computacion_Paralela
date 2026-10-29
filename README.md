# Indicadores Respiratorios con Arquitecturas SIMD, MISD y MIMD

Proyecto académico de **Computación Paralela** que procesa un dataset clínico de 5001
pacientes, calcula indicadores respiratorios y antropométricos, almacena los resultados
en **MySQL** y los visualiza en un **dashboard interactivo de Streamlit**.

El objetivo es comparar tres formas de organizar el mismo trabajo:

| Enfoque | Script | Hilos | Qué reparte |
|---|---|---|---|
| Secuencial (base) | `main.py` | 1 | Nada: un solo flujo sobre todo el dataset |
| MISD | `misd.py` | 4 | Instrucciones: cada hilo aplica una operación distinta sobre **todo** el dataset |
| MIMD | `mimd.py` | 3 | Datos e instrucciones: el dataset se parte en 3 y cada hilo hace una operación distinta sobre su tercio |

## Indicadores calculados

| Indicador | Fórmula | Dónde se calcula |
|---|---|---|
| IMC | `peso_kg / estatura_m²` | `main.py`, `misd.py`, `mimd.py` |
| Relación SpO₂/FiO₂ | `spo2_pct / fio2` | `misd.py`, `mimd.py` |
| Ventilación por minuto | `volumen_corriente_ml × frecuencia_respiratoria_rpm` | `misd.py`, `mimd.py` |
| Conversión de ventilación | `ml/min ÷ 1000` → `L/min` | `misd.py`, `mimd.py` |

## Estructura del repositorio

```
python_paralela/
├── main.py                # Procesamiento secuencial (línea base) -> calculo_simd
├── misd.py                # Multihilo MISD -> datos_fisiologicos + calculo_misd
├── mimd.py                # Multihilo MIMD por etapas -> calculo_mimd_etapas
├── conexion.py            # Función conectar_mysql() con los datos de conexión
├── dashboard.py           # Dashboard Streamlit (3 pestañas: SIMD / MISD / MIMD)
├── dataset_5001.csv       # Dataset de entrada (5001 registros)
├── esquema.sql            # Creación de la base de datos y sus tablas
└── requirements.txt       # Dependencias con versiones fijadas
```

## Dataset

`dataset_5001.csv` contiene 5001 filas y 10 columnas:

```
id, genero, edad, practica_ejercicio, peso_kg, estatura_m,
spo2_pct, fio2, volumen_corriente_ml, frecuencia_respiratoria_rpm
```

`genero`: `1` = masculino, `0` = femenino. `practica_ejercicio`: `1` = sí, `0` = no.

---

# Instalación en otra computadora

## 1. Requisitos previos

- **Python 3.14** (el proyecto fue probado con `3.14.7`). Versiones anteriores pueden no
  tener ruedas (wheels) para `pandas 3.x`, `numpy 2.5` ni `pyarrow 26`.
- **MySQL 8.x** escuchando en el puerto **3307** (o ajustar el puerto en `conexion.py`).
- **Git** para clonar el repositorio.

Verificar versiones:

```bash
python --version
mysql --version
git --version
```

## 2. Clonar el repositorio

```bash
git clone https://github.com/DTiupul/Proyecto_Computacion_Paralela.git
cd Proyecto_Computacion_Paralela
```

## 3. Crear y activar un entorno virtual

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Si PowerShell bloquea el script de activación, ejecutar una vez:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4. Instalar las dependencias

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` fija las versiones exactas de las 43 dependencias del proyecto.
Las principales son:

| Paquete | Uso en el proyecto |
|---|---|
| `streamlit` | Dashboard web (`dashboard.py`) |
| `pandas` | Consultas SQL a `DataFrame` y transformación de datos |
| `numpy` | Operaciones numéricas auxiliares |
| `plotly` | Gráficos interactivos del dashboard |
| `matplotlib` | Gráficos de apoyo |
| `mysql-connector-python` | Conexión y escritura en MySQL |
| `pyarrow` | Motor de tipos de pandas/streamlit |
| `altair`, `pydeck`, `pillow` | Visualizaciones y recursos gráficos de Streamlit |
| `uvicorn`, `starlette`, `websockets` | Servidor ASGI que usa Streamlit |

Verificar la instalación:

```bash
python -c "import streamlit, pandas, mysql.connector; print('OK')"
```

## 5. Preparar la base de datos MySQL

El proyecto usa la base de datos `proyecto_paralela`. Para crearla junto con sus tablas:

```bash
mysql -u root -p -P 3307 < esquema.sql
```

O desde MySQL Workbench / phpMyAdmin: abrir `esquema.sql` y ejecutarlo completo.

Tablas creadas:

| Tabla | Contenido |
|---|---|
| `datos_fisiologicos` | Datos crudos del paciente (una fila por `id`) |
| `calculo_simd` | Resultado del IMC por paciente (`main.py`) |
| `calculo_misd` | Resultados de las 4 operaciones por ejecución (`misd.py`) |
| `calculo_mimd_etapas` | Una fila por paciente **y** etapa (`mimd.py`) |

## 6. Configurar la conexión

Editar `conexion.py` con los datos de la máquina donde se ejecute:

```python
conexion = mysql.connector.connect(
    host="127.0.0.1",
    port=3307,            # cambiar si MySQL usa 3306
    user="root",
    password="",          # colocar la contraseña real
    database="proyecto_paralela"
)
```

Comprobar la conexión:

```bash
python conexion.py
```

Debe imprimir `Conexion exitosa a la base de datos MySQL`.

## 7. Ejecutar el procesamiento

> **Importante — orden de ejecución.** `calculo_simd`, `calculo_misd` y
> `calculo_mimd_etapas` tienen una clave foránea hacia `datos_fisiologicos.id`, y esa
> tabla la llena `misd.py`. Por eso, en una base de datos vacía, **el primer script debe
> ser `misd.py`**.

```bash
# 1) Llena datos_fisiologicos y calculo_misd
python misd.py

# 2) Calcula el IMC secuencial sobre los mismos pacientes
python main.py

# 3) Ejecuta el reparto MIMD por etapas
python mimd.py
```

Cada script imprime en consola los resultados, el tiempo medido en microsegundos y el
número de registros guardados. Los tiempos quedan almacenados en la columna
`tiempo_microsegundos` para poder compararlos en el dashboard.

## 8. Abrir el dashboard

```bash
streamlit run dashboard.py
```

Streamlit abrirá `http://localhost:8501`. El dashboard tiene tres pestañas (SIMD, MISD y
MIMD), filtros por género, práctica de ejercicio y categoría de IMC, gráficos comparativos
y una sección de integridad de la base de datos. Usar el botón
**Actualizar datos consultados** después de volver a ejecutar los scripts.

---

# Cómo funciona cada script

## `main.py` — línea base secuencial

1. Lee solo `id`, `peso_kg` y `estatura_m` del CSV.
2. Recorre los 5001 registros en un único bucle calculando el IMC (redondeado a 2 decimales).
3. Mide únicamente el cálculo con `time.perf_counter_ns()` y convierte a microsegundos.
4. Inserta en `calculo_simd` con `INSERT ... ON DUPLICATE KEY UPDATE`, guardando el mismo
   tiempo total para cada fila.

## `misd.py` — multihilo MISD

1. Lee las 10 columnas del CSV.
2. Define cuatro funciones, cada una recorriendo **todo** el dataset:
   IMC, relación SpO₂/FiO₂, ventilación ml/min y conversión a L/min.
3. Lanza cuatro `threading.Thread` y espera con `join()`.
4. Guarda los datos crudos en `datos_fisiologicos` y los resultados en `calculo_misd`.

## `mimd.py` — multihilo MIMD por etapas

1. Lee las 10 columnas y divide el dataset en 3 bloques de `len(id) // 3`.
2. Asigna una operación distinta a cada bloque: IMC, relación SpO₂/FiO₂ y ventilación.
3. Cada hilo mide su propio tiempo, y también se mide el tiempo total en paralelo.
4. Crea `calculo_mimd_etapas` si no existe e inserta una fila por paciente y etapa
   (`IMC`, `RELACION_SF`, `VENTILACION`).

## `conexion.py`

Centraliza la conexión a MySQL en la función `conectar_mysql()`, usada por los tres
scripts de procesamiento y por el dashboard.

---

# Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Access denied for user 'root'@'localhost'` | Contraseña incorrecta en `conexion.py` | Actualizar `password` |
| `Can't connect to MySQL server on '127.0.0.1'` | MySQL apagado o en otro puerto | Iniciar el servicio y ajustar `port` (3306 por defecto) |
| `Unknown database 'proyecto_paralela'` | No se ejecutó el esquema | Ejecutar `esquema.sql` |
| `Cannot add or update a child row: a foreign key constraint fails` | Se ejecutó `main.py` o `mimd.py` antes de llenar `datos_fisiologicos` | Ejecutar `misd.py` primero |
| `ModuleNotFoundError: No module named 'streamlit'` | Entorno virtual no activado | Activar `.venv` e instalar `requirements.txt` |
| `Duplicate entry` al repetir `misd.py` | `calculo_misd` no tiene `ON DUPLICATE KEY UPDATE` | Es esperado: cada ejecución agrega filas; el dashboard muestra la última por paciente |
| `pip` falla al compilar `numpy`/`pandas` | Python distinto de 3.14 o sin wheels | Usar Python 3.14 de 64 bits |
| El dashboard no muestra datos | Scripts no ejecutados o filtros activos | Ejecutar los scripts y pulsar **Actualizar datos consultados** |

# Consideraciones sobre la medición de tiempos

- En `misd.py` cada hilo procesa los **5001** registros, mientras que en `mimd.py` cada
  hilo procesa ~1667. Los tiempos no son directamente comparables: hay que normalizar por
  cantidad de trabajo.
- En `misd.py` los cuatro hilos arrancan a la vez, pero la conversión a L/min depende del
  resultado de la ventilación en ml/min. Al no existir sincronización entre `h3` y `h4`,
  esa conversión puede leer ceros según el orden de ejecución.
- El tiempo impreso por `main.py` corresponde solo al cálculo; la carga del CSV y la
  escritura en MySQL quedan fuera de la medición.

# Participantes

Proyecto desarrollado en conjunto por:

| Participante | Aportes |
|---|---|
| **Danny Tiupul** | Creación del proyecto, captura de datos y desarrollo de las arquitecturas **MISD** y **MIMD** |
| **Melany Iza** | Desarrollo de la arquitectura **SIMD** y desarrollo de la base de datos |

Ambos participantes trabajaron en conjunto en el desarrollo de los dashboards.

Proyecto académico de Computación Paralela — ESPE.
