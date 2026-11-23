"""Utilidades para RUT chileno (formato y dígito verificador módulo 11)."""
import re

from django.core.exceptions import ValidationError

_PATRON = re.compile(r"^\d{7,8}-[\dK]$")


def normalizar_rut(valor):
    """Devuelve el RUT sin puntos ni espacios, en mayúsculas y con guion (12345678-5)."""
    if valor is None:
        return ""
    limpio = re.sub(r"[.\s]", "", str(valor)).upper()
    if limpio and "-" not in limpio and len(limpio) > 1:
        limpio = f"{limpio[:-1]}-{limpio[-1]}"
    return limpio


def calcular_dv(cuerpo):
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def rut_es_valido(valor):
    rut = normalizar_rut(valor)
    if not _PATRON.match(rut):
        return False
    cuerpo, dv = rut.split("-")
    return calcular_dv(cuerpo) == dv


def validar_rut(valor):
    if not rut_es_valido(valor):
        raise ValidationError("RUT inválido. Use el formato 12345678-5 con dígito verificador correcto.")
