"""Rutas compartidas del proyecto.

Centraliza la ubicacion de los archivos para que los scripts funcionen
sin importar desde que carpeta se ejecuten.
"""

from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_DATASET = RAIZ_PROYECTO / "data" / "dataset_5001.csv"
