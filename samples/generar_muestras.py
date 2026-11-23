"""Genera los archivos de ejemplo para probar la carga masiva (ejecutar desde la raíz del proyecto)."""
import csv
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nuam.settings")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from calificaciones.services.rut import calcular_dv  # noqa: E402

DESTINO = Path(__file__).resolve().parent
NEMOS = ["CHILE", "FALABELLA", "COPEC", "SQM-B", "BAP", "SCCO", "BCOLOMBIA", "ECOPETROL"]
azar = random.Random(7)


def rut(n):
    return f"{n}-{calcular_dv(n)}"


def escribir_csv(nombre, filas, delim=","):
    with open(DESTINO / nombre, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=delim).writerows(filas)


# 30 filas válidas de montos (DJ1948) con RUT nuevos
base = [(rut(18000000 + i * 211), NEMOS[i % 8], 2025) for i in range(30)]
escribir_csv("montos_dj1948_valido.csv",
             [["rut", "nemotecnico", "ejercicio", "monto"]] +
             [[r, n, e, azar.randint(1000000, 80000000)] for r, n, e in base])

# 10 filas: 6 correctas y 4 con error (RUT inválido, celda vacía, instrumento inexistente, monto negativo)
escribir_csv("montos_con_errores.csv", [
    ["rut", "nemotecnico", "ejercicio", "monto"],
    [rut(19000000), "CHILE", 2025, 1200000],
    [rut(19000500), "COPEC", 2025, 2500000],
    ["12345678-0", "CHILE", 2025, 900000],            # RUT inválido
    [rut(19001000), "FALABELLA", 2025, ""],           # celda vacía
    [rut(19001500), "SQM-B", 2025, 4100000],
    [rut(19002000), "NOEXISTE", 2025, 700000],        # instrumento inexistente
    [rut(19002500), "BAP", 2025, 3300000],
    [rut(19003000), "SCCO", 2025, -500],              # monto negativo
    [rut(19003500), "ECOPETROL", 2025, 5600000],
    [rut(19004000), "BCOLOMBIA", 2025, 1800000],
], delim=";")

# sin columnas requeridas / vacío / PDF falso
escribir_csv("sin_columnas.csv", [["codigo", "valor"], ["A1", 100], ["A2", 200]])
(DESTINO / "vacio.csv").write_bytes(b"")
(DESTINO / "documento.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")

# factores (.xlsx): 10 filas que actualizan registros de montos + 10 nuevas
from openpyxl import Workbook  # noqa: E402
libro = Workbook()
hoja = libro.active
hoja.append(["rut", "nemotecnico", "ejercicio", "factor"])
for r, n, e in base[:10]:
    hoja.append([r, n, e, round(azar.uniform(0.05, 0.95), 4)])
for i in range(10):
    hoja.append([rut(20000000 + i * 311), NEMOS[i % 8], 2025, round(azar.uniform(0.05, 0.95), 4)])
libro.save(DESTINO / "factores_valido.xlsx")
print("Muestras generadas en", DESTINO)
