# Diagramas del proyecto

Diagramas que explican el funcionamiento del programa y las tres arquitecturas de
procesamiento empleadas. Están escritos en **Mermaid**, por lo que GitHub los renderiza
directamente en este mismo archivo.

Cada diagrama tiene además su fuente en un archivo `.mmd` para poder editarlo o exportarlo.

| # | Diagrama | Archivo | Qué muestra |
|---|---|---|---|
| 1 | Arquitectura general | [`01-arquitectura-general.mmd`](01-arquitectura-general.mmd) | Flujo completo: CSV → scripts → MySQL → dashboard |
| 2 | Flujo de `main.py` | [`02-flujo-main.mmd`](02-flujo-main.mmd) | Procesamiento secuencial del IMC |
| 3 | Flujo de `misd.py` | [`03-flujo-misd.mmd`](03-flujo-misd.mmd) | 4 hilos con 4 instrucciones sobre el mismo dataset |
| 4 | Flujo de `mimd.py` | [`04-flujo-mimd.mmd`](04-flujo-mimd.mmd) | Dataset partido en 3 y una instrucción por bloque |
| 5 | Comparación de arquitecturas | [`05-comparacion-arquitecturas.mmd`](05-comparacion-arquitecturas.mmd) | SISD vs MISD vs MIMD lado a lado |
| 6 | Modelo de datos | [`06-modelo-datos.mmd`](06-modelo-datos.mmd) | Tablas, columnas y claves foráneas |
| 7 | Secuencia de ejecución | [`07-secuencia-ejecucion.mmd`](07-secuencia-ejecucion.mmd) | Orden en que se ejecutan los scripts y el dashboard |

También hay una versión en imagen de cada diagrama (PNG a 2x) en la carpeta
[`img/`](img/), útil para pegar en informes o presentaciones.

---

## 1. Arquitectura general

El dataset es la única entrada. Los tres scripts lo leen de forma independiente y cada uno
escribe en su propia tabla de resultados. El dashboard solo lee de MySQL, nunca del CSV, y
une las tablas por la clave foránea `paciente_id`.

```mermaid
flowchart TB
    subgraph ENTRADA["Entrada"]
        CSV["dataset_5001.csv<br/>5001 registros x 10 columnas"]
    end

    subgraph PROC["Procesamiento en Python"]
        MAIN["main.py<br/>Secuencial - 1 hilo<br/>calcula IMC"]
        MISD["misd.py<br/>4 hilos - MISD<br/>4 operaciones sobre todo el dataset"]
        MIMD["mimd.py<br/>3 hilos - MIMD<br/>dataset partido en 3"]
    end

    subgraph BD["MySQL - base de datos proyecto_paralela"]
        DF[("datos_fisiologicos<br/>datos crudos del paciente")]
        CS[("calculo_simd<br/>IMC secuencial")]
        CM[("calculo_misd<br/>IMC, S/F, ventilacion")]
        CME[("calculo_mimd_etapas<br/>una fila por paciente y etapa")]
    end

    subgraph VIS["Visualizacion"]
        DASH["dashboard.py<br/>Streamlit - puerto 8501"]
    end

    CSV --> MAIN
    CSV --> MISD
    CSV --> MIMD

    MISD -->|"INSERT / UPDATE"| DF
    MISD -->|"INSERT"| CM
    MAIN -->|"INSERT / UPDATE"| CS
    MIMD -->|"INSERT / UPDATE"| CME

    DF -.->|"FK paciente_id"| CS
    DF -.->|"FK paciente_id"| CM
    DF -.->|"FK paciente_id"| CME

    DF --> DASH
    CS --> DASH
    CM --> DASH
    CME --> DASH

    DASH --> USR["Usuario<br/>3 pestanas: SIMD / MISD / MIMD"]
```

---

## 2. Flujo de `main.py` (secuencial)

Un solo hilo recorre los 5001 registros. El cronómetro envuelve únicamente el bucle de
cálculo: la carga del CSV y la escritura en MySQL quedan fuera de la medición.

```mermaid
flowchart TB
    A["Inicio"] --> B["Abrir dataset_5001.csv<br/>encoding utf-8-sig"]
    B --> C["Leer solo 3 columnas:<br/>id, peso_kg, estatura_m"]
    C --> D["Reservar vector imc = [0.0] * 5001"]
    D --> E["inicio = time.perf_counter_ns()"]

    subgraph CALC["Unico flujo de procesamiento"]
        direction TB
        F["for i in range(5001):"]
        G["imc[i] = round(peso_kg[i] / estatura_m[i]^2, 2)"]
        F --> G
        G -->|"siguiente i"| F
    end

    E --> F
    F -->|"i = 5000"| H["fin = time.perf_counter_ns()<br/>tiempo = (fin - inicio) / 1000 us"]
    H --> I["Imprimir los 5001 registros"]
    I --> J["conectar_mysql()"]
    J --> K["INSERT INTO calculo_simd<br/>ON DUPLICATE KEY UPDATE"]
    K --> L["commit()"]
    L --> M["Cerrar cursor y conexion"]
    M --> N["Fin"]
```

---

## 3. Flujo de `misd.py` (MISD)

Los cuatro hilos leen **el mismo dataset completo** y cada uno ejecuta una instrucción
distinta. El tiempo se mide desde el primer `start()` hasta el último `join()`.

```mermaid
flowchart TB
    A["Inicio"] --> B["Leer dataset_5001.csv<br/>10 columnas - 5001 registros"]
    B --> C["Reservar vectores de resultados<br/>imc, relacion_sf, ventilacion_ml_min, ventilacion_l_min"]
    C --> D["Crear 4 hilos con threading.Thread"]
    D --> E["inicio = time.perf_counter_ns()"]
    E --> S["h1.start() / h2.start() / h3.start() / h4.start()"]

    subgraph DATOS["Mismo flujo de datos para los 4 hilos (el dataset completo)"]
        direction LR
        H1["Hilo 1 - calcular_imc()<br/>i = 0 .. 5000<br/>imc = peso / estatura^2"]
        H2["Hilo 2 - calcular_relacion_sf()<br/>i = 0 .. 5000<br/>relacion_sf = spo2 / fio2"]
        H3["Hilo 3 - calcular_ventilacion_ml_min()<br/>i = 0 .. 5000<br/>volumen_corriente * frecuencia_respiratoria"]
        H4["Hilo 4 - convertir_ventilacion_ml_a_l()<br/>i = 0 .. 5000<br/>ventilacion_ml_min / 1000"]
    end

    S --> H1
    S --> H2
    S --> H3
    S --> H4

    H3 -.->|"H4 depende de este resultado<br/>sin sincronizacion (condicion de carrera)"| H4

    H1 --> J["h1.join() / h2.join() / h3.join() / h4.join()"]
    H2 --> J
    H3 --> J
    H4 --> J

    J --> F["fin = time.perf_counter_ns()<br/>tiempo = (fin - inicio) / 1000 us"]
    F --> G["Imprimir los 5001 registros"]
    G --> K["MySQL: INSERT datos_fisiologicos<br/>INSERT calculo_misd"]
    K --> L["commit() y cierre"]
    L --> M["Fin"]
```

> **Detalle importante:** la línea punteada marca una dependencia real de datos. `h4`
> convierte a L/min el vector que llena `h3`, pero ambos arrancan al mismo tiempo y no hay
> `join()` intermedio, así que la conversión puede ejecutarse antes de que `h3` termine.

---

## 4. Flujo de `mimd.py` (MIMD)

Aquí se reparten **los datos y las instrucciones**: el dataset se divide en tres bloques
de 1667 registros y cada hilo aplica una operación distinta sobre su propio bloque. Cada
hilo mide su tiempo y se guarda el tiempo de la etapa en la base de datos.

```mermaid
flowchart TB
    A["Inicio"] --> B["Leer dataset_5001.csv<br/>10 columnas - 5001 registros"]
    B --> C["tamano_parte = 5001 // 3 = 1667"]
    C --> D["Dividir el dataset en 3 bloques"]

    D --> P1["Parte 1<br/>indices 0 .. 1666<br/>1667 registros"]
    D --> P2["Parte 2<br/>indices 1667 .. 3333<br/>1667 registros"]
    D --> P3["Parte 3<br/>indices 3334 .. 5000<br/>1667 registros"]

    P1 --> H1["Hilo 1 - calcular_imc(inicio, fin)<br/>imc = peso / estatura^2"]
    P2 --> H2["Hilo 2 - calcular_relacion_sf(inicio, fin)<br/>relacion_sf = spo2 / fio2"]
    P3 --> H3["Hilo 3 - calcular_ventilacion(inicio, fin)<br/>ml/min y conversion a L/min"]

    H1 --> T1["tiempos['IMC']"]
    H2 --> T2["tiempos['RELACION_SF']"]
    H3 --> T3["tiempos['VENTILACION']"]

    T1 --> J["join() de los 3 hilos<br/>tiempo_total start - join"]
    T2 --> J
    T3 --> J

    J --> R["Imprimir 3 registros por parte<br/>+ tiempo de cada instruccion"]
    R --> DB["MySQL:<br/>CREATE TABLE IF NOT EXISTS calculo_mimd_etapas<br/>INSERT una fila por paciente y etapa"]
    DB --> F["commit() y cierre"]
    F --> G["Fin"]
```

---

## 5. Comparación de las arquitecturas

```mermaid
flowchart LR
    subgraph SISD["Secuencial - main.py"]
        direction TB
        S1["1 instruccion activa"] --> S2["1 procesador<br/>(1 hilo principal)"]
        S2 --> S3["Dataset completo<br/>5001 registros"]
        S3 --> S4["1 resultado por iteracion"]
    end

    subgraph MISD_A["MISD - misd.py"]
        direction TB
        M1["4 instrucciones distintas<br/>IMC / S-F / ventilacion / conversion"] --> M2["4 procesadores<br/>(4 hilos)"]
        M2 --> M3["El mismo dataset completo<br/>en los 4 hilos"]
        M3 --> M4["4 resultados en paralelo<br/>sobre los mismos 5001 pacientes"]
    end

    subgraph MIMD_A["MIMD - mimd.py"]
        direction TB
        D1["3 instrucciones distintas<br/>IMC / S-F / ventilacion"] --> D2["3 procesadores<br/>(3 hilos)"]
        D2 --> D3["1/3 del dataset por hilo<br/>1667 registros cada uno"]
        D3 --> D4["3 resultados parciales<br/>cada paciente procesado 1 sola vez"]
    end

    SISD ~~~ MISD_A
    MISD_A ~~~ MIMD_A

    NOTE["Nota: main.py se etiqueta como SIMD en la tabla calculo_simd,<br/>pero su ejecucion real es secuencial (SISD), sin hilos."]
```

### Mapa arquitectura → código → tabla

| Arquitectura | Archivo | Hilos | Datos por hilo | Tabla de resultados |
|---|---|---|---|---|
| Secuencial (etiquetada SIMD) | `main.py` | 1 | 5001 registros | `calculo_simd` |
| MISD | `misd.py` | 4 | 5001 registros en cada hilo | `calculo_misd` |
| MIMD | `mimd.py` | 3 | 1667 registros por hilo | `calculo_mimd_etapas` |

---

## 6. Modelo de datos

```mermaid
erDiagram
    datos_fisiologicos ||--o{ calculo_simd : "1:N paciente_id"
    datos_fisiologicos ||--o{ calculo_misd : "1:N paciente_id"
    datos_fisiologicos ||--o{ calculo_mimd_etapas : "1:N paciente_id"

    datos_fisiologicos {
        int id PK "id del CSV"
        tinyint genero "1 masculino, 0 femenino"
        int edad
        tinyint practica_ejercicio "1 si, 0 no"
        decimal peso_kg
        decimal estatura_m
        decimal spo2_pct
        decimal fio2
        int volumen_corriente_ml
        int frecuencia_respiratoria_rpm
        timestamp fecha_registro
    }

    calculo_simd {
        int id PK
        int paciente_id FK
        decimal imc "unico por paciente"
        double tiempo_microsegundos
        timestamp fecha_procesamiento
    }

    calculo_misd {
        int id PK
        int paciente_id FK
        decimal imc
        decimal relacion_sf
        int ventilacion_ml_min
        decimal ventilacion_l_min
        double tiempo_microsegundos
        timestamp fecha_procesamiento
    }

    calculo_mimd_etapas {
        int id PK
        int paciente_id FK
        varchar etapa "IMC / RELACION_SF / VENTILACION"
        decimal imc
        decimal relacion_sf
        int ventilacion_ml_min
        decimal ventilacion_l_min
        double tiempo_microsegundos
        timestamp fecha_procesamiento
    }
```

`datos_fisiologicos` es la tabla padre: la llena `misd.py` y las otras tres tablas apuntan a
ella con `paciente_id`. Por eso, en una base vacía, `misd.py` debe ejecutarse primero.

---

## 7. Secuencia de ejecución

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant CSV as dataset_5001.csv
    participant MISD as misd.py
    participant MAIN as main.py
    participant MIMD as mimd.py
    participant DB as MySQL
    participant DASH as dashboard.py

    Note over U,DB: Paso 1 - misd.py debe ejecutarse primero<br/>porque crea datos_fisiologicos (tabla padre de las FK)
    U->>MISD: python misd.py
    MISD->>CSV: leer 5001 registros x 10 columnas
    MISD->>MISD: 4 hilos sobre todo el dataset
    MISD->>DB: INSERT datos_fisiologicos (ON DUPLICATE KEY UPDATE)
    MISD->>DB: INSERT calculo_misd
    DB-->>U: DATOS GUARDADOS CORRECTAMENTE

    Note over U,DB: Paso 2 - linea base secuencial
    U->>MAIN: python main.py
    MAIN->>CSV: leer id, peso_kg, estatura_m
    MAIN->>MAIN: calcular IMC en un solo bucle
    MAIN->>DB: INSERT calculo_simd (ON DUPLICATE KEY UPDATE)
    DB-->>U: DATOS GUARDADOS CORRECTAMENTE

    Note over U,DB: Paso 3 - procesamiento MIMD por etapas
    U->>MIMD: python mimd.py
    MIMD->>CSV: leer 5001 registros
    MIMD->>MIMD: partir en 3 bloques y lanzar 3 hilos
    MIMD->>DB: CREATE TABLE IF NOT EXISTS calculo_mimd_etapas
    MIMD->>DB: INSERT una fila por paciente y etapa
    DB-->>U: DATOS GUARDADOS CORRECTAMENTE

    Note over U,DASH: Paso 4 - visualizacion
    U->>DASH: streamlit run dashboard.py
    DASH->>DB: SELECT datos_fisiologicos + calculo_simd + calculo_misd + calculo_mimd_etapas
    DB-->>DASH: DataFrames (pandas)
    DASH-->>U: 3 pestanas con graficos, filtros y tiempos
```

---

## Cómo ver o exportar los diagramas

- **GitHub**: se renderizan solos al abrir este archivo.
- **Editor de texto / VS Code**: instalar la extensión *Markdown Preview Mermaid Support*
  o abrir los `.mmd` con la extensión *Mermaid*.
- **En línea**: pegar el contenido de un `.mmd` en <https://mermaid.live> y descargar PNG o SVG.
- **Línea de comandos**:

  ```bash
  npx -y @mermaid-js/mermaid-cli -i 01-arquitectura-general.mmd -o 01-arquitectura-general.png
  ```
