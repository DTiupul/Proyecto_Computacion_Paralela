-- ============================================================
-- Esquema de la base de datos del proyecto
-- Indicadores respiratorios con arquitecturas SIMD / MISD / MIMD
--
-- Uso:
--   mysql -u root -p -P 3307 < esquema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS proyecto_paralela
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE proyecto_paralela;

-- ------------------------------------------------------------
-- 1. Datos fisiologicos (los llena misd.py desde dataset_5001.csv)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS datos_fisiologicos (
    id                         INT(10) UNSIGNED NOT NULL,
    genero                     TINYINT(1)       NOT NULL,
    edad                       INT(10) UNSIGNED NOT NULL,
    practica_ejercicio         TINYINT(1)       NOT NULL,
    peso_kg                    DECIMAL(6,2)     NOT NULL,
    estatura_m                 DECIMAL(4,2)     NOT NULL,
    spo2_pct                   DECIMAL(5,2)     NOT NULL,
    fio2                       DECIMAL(4,2)     NOT NULL,
    volumen_corriente_ml       INT(10) UNSIGNED NOT NULL,
    frecuencia_respiratoria_rpm INT(10) UNSIGNED NOT NULL,
    fecha_registro             TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 2. Resultados del procesamiento secuencial (main.py)
--    Una fila por paciente: ON DUPLICATE KEY UPDATE sobre paciente_id
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculo_simd (
    id                     INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id            INT(10) UNSIGNED NOT NULL,
    imc                    DECIMAL(5,2)     NOT NULL,
    tiempo_microsegundos   DOUBLE           NOT NULL,
    fecha_procesamiento    TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_simd_paciente (paciente_id),
    CONSTRAINT fk_simd_paciente FOREIGN KEY (paciente_id)
        REFERENCES datos_fisiologicos (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 3. Resultados del procesamiento MISD multihilo (misd.py)
--    Acumula una fila por ejecucion (sin ON DUPLICATE KEY),
--    por eso no lleva clave unica sobre paciente_id.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculo_misd (
    id                     INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id            INT(10) UNSIGNED NOT NULL,
    imc                    DECIMAL(5,2)     NOT NULL,
    relacion_sf            DECIMAL(7,2)     NOT NULL,
    ventilacion_ml_min     INT(10) UNSIGNED NOT NULL,
    ventilacion_l_min      DECIMAL(6,2)     NOT NULL,
    tiempo_microsegundos   DOUBLE           NOT NULL,
    fecha_procesamiento    TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_misd_paciente (paciente_id),
    CONSTRAINT fk_misd_paciente FOREIGN KEY (paciente_id)
        REFERENCES datos_fisiologicos (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 4. Resultados del procesamiento MIMD por etapas (mimd.py)
--    Una fila por paciente y etapa calculada.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculo_mimd_etapas (
    id                     INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id            INT(10) UNSIGNED NOT NULL,
    etapa                  VARCHAR(20)      NOT NULL,
    imc                    DECIMAL(5,2)     NULL,
    relacion_sf            DECIMAL(7,2)     NULL,
    ventilacion_ml_min     INT(10) UNSIGNED NULL,
    ventilacion_l_min      DECIMAL(6,2)     NULL,
    tiempo_microsegundos   DOUBLE           NOT NULL,
    fecha_procesamiento    TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_mimd_etapa_paciente (paciente_id, etapa),
    CONSTRAINT fk_mimd_etapa_paciente FOREIGN KEY (paciente_id)
        REFERENCES datos_fisiologicos (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;
