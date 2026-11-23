"""Procesamiento de cargas masivas (.csv / .xlsx) de montos DJ1948 y factores."""
import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Auditoria, Calificacion, CargaMasiva, Instrumento
from .rut import normalizar_rut, rut_es_valido

EXTENSIONES = (".csv", ".xlsx")
MENSAJE_FORMATO = "Formato de archivo no soportado"

COLUMNAS = {
    "MONTOS": ["rut", "nemotecnico", "ejercicio", "monto"],
    "FACTORES": ["rut", "nemotecnico", "ejercicio", "factor"],
}
ALIAS = {"instrumento": "nemotecnico", "nemo": "nemotecnico", "anio": "ejercicio",
         "ano": "ejercicio", "año": "ejercicio"}


class ErrorArchivo(Exception):
    """Error que impide procesar el archivo completo (formato, estructura, tamaño)."""


def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto))
                   if unicodedata.category(c) != "Mn")


def _normalizar_encabezado(texto):
    clave = _sin_acentos(texto).strip().lower().replace(" ", "")
    return ALIAS.get(clave, clave)


def leer_filas(archivo):
    """Devuelve (encabezados_normalizados, lista_de_filas) validando extensión y tamaño."""
    nombre = (archivo.name or "").lower()
    if not nombre.endswith(EXTENSIONES):
        raise ErrorArchivo(MENSAJE_FORMATO)
    if archivo.size > settings.CARGA_MAX_BYTES:
        raise ErrorArchivo("El archivo excede el tamaño máximo permitido de 5 MB.")
    if archivo.size == 0:
        raise ErrorArchivo("El archivo está vacío.")

    contenido = archivo.read()
    if nombre.endswith(".csv"):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                texto = contenido.decode("latin-1")
            except UnicodeDecodeError:
                raise ErrorArchivo(MENSAJE_FORMATO)
        if "\x00" in texto:
            raise ErrorArchivo(MENSAJE_FORMATO)
        muestra = texto[:2048]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        filas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    else:
        from openpyxl import load_workbook
        try:
            libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except Exception:
            raise ErrorArchivo(MENSAJE_FORMATO)
        hoja = libro.active
        filas = [["" if c is None else c for c in fila] for fila in hoja.iter_rows(values_only=True)]
        libro.close()

    filas = [f for f in filas if any(str(c).strip() for c in f)]
    if not filas:
        raise ErrorArchivo("El archivo está vacío.")
    encabezados = [_normalizar_encabezado(c) for c in filas[0]]
    datos = filas[1:]
    if len(datos) > settings.CARGA_MAX_FILAS:
        raise ErrorArchivo(f"El archivo excede el máximo de {settings.CARGA_MAX_FILAS} filas.")
    return encabezados, datos


def _a_decimal(valor, nombre, max_decimales, minimo, maximo=None):
    texto = str(valor).strip().replace(" ", "")
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(f"{nombre} no es un valor numérico: '{valor}'")
    if not numero.is_finite():
        raise ValueError(f"{nombre} no es un valor numérico: '{valor}'")
    if numero < minimo:
        raise ValueError(f"{nombre} no puede ser negativo: '{valor}'")
    if maximo is not None and numero > maximo:
        raise ValueError(f"{nombre} no puede ser mayor a {maximo}: '{valor}'")
    if -numero.as_tuple().exponent > max_decimales:
        raise ValueError(f"{nombre} admite como máximo {max_decimales} decimales: '{valor}'")
    if len(numero.as_tuple().digits) - max(0, -numero.as_tuple().exponent) > 14:
        raise ValueError(f"{nombre} excede la cantidad de dígitos permitida: '{valor}'")
    return numero


def procesar_carga(archivo, tipo, request):
    """
    Procesa el archivo. Los registros correctos se cargan aunque existan filas con error
    (HU16); las filas inválidas quedan en `errores` con el motivo específico.
    """
    if tipo not in COLUMNAS:
        raise ErrorArchivo("Tipo de carga no válido.")
    encabezados, filas = leer_filas(archivo)
    requeridas = COLUMNAS[tipo]
    faltantes = [c for c in requeridas if c not in encabezados]
    if faltantes:
        raise ErrorArchivo("Estructura de archivo inválida. Faltan las columnas: "
                           + ", ".join(faltantes) + ". Columnas esperadas: " + ", ".join(requeridas) + ".")
    idx = {c: encabezados.index(c) for c in requeridas}
    campo_valor = "monto" if tipo == "MONTOS" else "factor"

    instrumentos = {i.nemotecnico.upper(): i for i in Instrumento.objects.all()}
    errores, validas, vistos = [], [], {}
    for numero, fila in enumerate(filas, start=2):          # fila 1 = encabezados
        def celda(col):
            pos = idx[col]
            return str(fila[pos]).strip() if pos < len(fila) and fila[pos] is not None else ""
        valores = {c: celda(c) for c in requeridas}
        rut_original = valores["rut"]
        try:
            for col, val in valores.items():
                if val == "":
                    raise ValueError(f"Celda vacía en la columna '{col}'")
            rut = normalizar_rut(valores["rut"])
            if not rut_es_valido(rut):
                raise ValueError(f"RUT inválido: '{rut_original}'")
            instrumento = instrumentos.get(valores["nemotecnico"].upper())
            if instrumento is None:
                raise ValueError(f"Instrumento no existe: '{valores['nemotecnico']}'")
            try:
                ejercicio = int(Decimal(valores["ejercicio"]))
                if Decimal(valores["ejercicio"]) != ejercicio:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError(f"Ejercicio no es un año válido: '{valores['ejercicio']}'")
            if not 2000 <= ejercicio <= 2100:
                raise ValueError(f"Ejercicio fuera de rango (2000-2100): '{ejercicio}'")
            if tipo == "MONTOS":
                valor = _a_decimal(valores["monto"], "Monto", 2, Decimal("0"))
            else:
                valor = _a_decimal(valores["factor"], "Factor", 4, Decimal("0"), Decimal("1"))
            clave = (rut, instrumento.pk, ejercicio)
            if clave in vistos:
                raise ValueError(f"Fila duplicada en el archivo (misma combinación que la fila {vistos[clave]})")
            vistos[clave] = numero
            validas.append((numero, rut, instrumento, ejercicio, valor))
        except ValueError as exc:
            errores.append({"fila": numero, "rut": rut_original, "motivo": str(exc)})

    usuario = request.user
    ahora = timezone.now()
    creados = actualizados = 0
    with transaction.atomic():
        existentes = {}
        ruts = {v[1] for v in validas}
        if ruts:
            for c in Calificacion.objects.filter(eliminado=False, rut__in=ruts):
                existentes[(c.rut, c.instrumento_id, c.ejercicio)] = c
        nuevos, a_actualizar, auditorias_upd = [], [], []
        for _, rut, instrumento, ejercicio, valor in validas:
            actual = existentes.get((rut, instrumento.pk, ejercicio))
            if actual:
                antes = getattr(actual, campo_valor)
                setattr(actual, campo_valor, valor)
                actual.actualizado_por = usuario
                actual.actualizado_en = ahora
                a_actualizar.append((actual, {campo_valor: [str(antes), str(valor)]}))
            else:
                nuevos.append(Calificacion(rut=rut, instrumento=instrumento, ejercicio=ejercicio,
                                           creado_por=usuario, actualizado_por=usuario,
                                           **{campo_valor: valor}))
        if nuevos:
            Calificacion.objects.bulk_create(nuevos)
            creados = len(nuevos)
        if a_actualizar:
            Calificacion.objects.bulk_update([c for c, _ in a_actualizar],
                                             [campo_valor, "actualizado_por", "actualizado_en"])
            actualizados = len(a_actualizar)

        carga = CargaMasiva.objects.create(
            tipo=tipo, nombre_archivo=archivo.name[:255], usuario=usuario,
            total_filas=len(filas), filas_ok=len(validas), filas_error=len(errores),
            creados=creados, actualizados=actualizados, errores=errores)

        # Trazabilidad por registro (HU18): usuario y fecha de cada creación/actualización
        ip = request.META.get("REMOTE_ADDR") or None
        registros = []
        for c in nuevos:
            registros.append(Auditoria(usuario=usuario, usuario_texto=usuario.get_username(),
                                       accion=Auditoria.Accion.CREAR, modulo="Carga masiva",
                                       calificacion=c, ip=ip,
                                       detalle={"origen": f"carga #{carga.pk}", campo_valor: str(getattr(c, campo_valor))}))
        for c, cambios in a_actualizar:
            registros.append(Auditoria(usuario=usuario, usuario_texto=usuario.get_username(),
                                       accion=Auditoria.Accion.EDITAR, modulo="Carga masiva",
                                       calificacion=c, ip=ip,
                                       detalle={"origen": f"carga #{carga.pk}", "cambios": cambios}))
        registros.append(Auditoria(usuario=usuario, usuario_texto=usuario.get_username(),
                                   accion=Auditoria.Accion.CARGA, modulo="Carga masiva", ip=ip,
                                   resultado="OK" if not errores else "PARC",
                                   detalle={"carga": carga.pk, "archivo": archivo.name,
                                            "tipo": tipo, "ok": len(validas), "errores": len(errores)}))
        Auditoria.objects.bulk_create(registros, batch_size=1000)
    return carga
