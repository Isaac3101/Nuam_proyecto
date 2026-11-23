import csv
import io
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .auditoria import registrar
from .forms import CalificacionForm, CargaMasivaForm, FiltroCalificacionForm
from .models import Auditoria, Calificacion, CargaMasiva, EmpresaEmisora, IntentoLogin
from .permisos import requiere_rol, solo_admin
from .services.cargas import ErrorArchivo, procesar_carga
from .services.rut import normalizar_rut

POR_PAGINA = 20
MSG_INVALIDAS = "Credenciales inválidas"


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    email = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()[:254]
        clave = request.POST.get("password", "")
        intento, _ = IntentoLogin.objects.get_or_create(email=email)
        ahora = timezone.now()
        if intento.bloqueado_hasta and intento.bloqueado_hasta > ahora:
            minutos = int((intento.bloqueado_hasta - ahora).total_seconds() // 60) + 1
            messages.error(request, f"Cuenta bloqueada temporalmente. Intente nuevamente en {minutos} minutos.")
            registrar(request, Auditoria.Accion.LOGIN_FALLIDO, modulo="Acceso", resultado="ERROR",
                      usuario_texto=email, detalle={"motivo": "cuenta bloqueada"})
        else:
            usuario = authenticate(request, username=email, password=clave) if email and clave else None
            if usuario is not None:
                intento.intentos, intento.bloqueado_hasta = 0, None
                intento.save()
                login(request, usuario)
                registrar(request, Auditoria.Accion.LOGIN, modulo="Acceso")
                destino = request.GET.get("next", "")
                if destino.startswith("/") and not destino.startswith("//"):
                    return redirect(destino)
                return redirect("dashboard")
            if intento.bloqueado_hasta:            # bloqueo vencido: se reinicia el conteo
                intento.intentos, intento.bloqueado_hasta = 0, None
            intento.intentos += 1
            registrar(request, Auditoria.Accion.LOGIN_FALLIDO, modulo="Acceso", resultado="ERROR",
                      usuario_texto=email, detalle={"intento": intento.intentos})
            if intento.intentos >= settings.LOGIN_MAX_INTENTOS:
                intento.bloqueado_hasta = ahora + timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS)
                intento.intentos = 0
                registrar(request, Auditoria.Accion.BLOQUEO, modulo="Acceso", resultado="ERROR",
                          usuario_texto=email)
                messages.error(request, f"Cuenta bloqueada por {settings.LOGIN_BLOQUEO_MINUTOS} minutos "
                                        "tras 5 intentos fallidos.")
            else:
                messages.error(request, MSG_INVALIDAS)
            intento.save()
    return render(request, "calificaciones/login.html", {"email": email})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        registrar(request, Auditoria.Accion.LOGOUT, modulo="Acceso")
    logout(request)
    return redirect("login")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@requiere_rol
def dashboard(request):
    activas = Calificacion.objects.filter(eliminado=False)
    por_estado = {e["estado"]: e["n"] for e in activas.values("estado").annotate(n=Count("id"))}
    kpis = {
        "total": activas.count(),
        "aprobadas": por_estado.get(Calificacion.Estado.APROBADA, 0),
        "pendientes": por_estado.get(Calificacion.Estado.PENDIENTE, 0),
        "observadas": por_estado.get(Calificacion.Estado.OBSERVADA, 0),
        "cargas": CargaMasiva.objects.count(),
        "errores_carga": CargaMasiva.objects.aggregate(t=Sum("filas_error"))["t"] or 0,
    }
    ultimos = Auditoria.objects.exclude(accion__in=["LOGIN", "LOGOUT", "LOGIN_FALLIDO", "BLOQUEO"]
                                        ).select_related("calificacion__instrumento")[:6]
    return render(request, "calificaciones/dashboard.html", {"kpis": kpis, "ultimos": ultimos})


# ---------------------------------------------------------------------------
# Mantenedor de calificaciones
# ---------------------------------------------------------------------------
def _filtrar(request):
    """Aplica los filtros del mantenedor (búsqueda). Reutilizado por listado y exportación."""
    qs = Calificacion.objects.filter(eliminado=False).select_related("instrumento", "instrumento__empresa")
    form = FiltroCalificacionForm(request.GET)
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            q = d["q"].strip()
            qs = qs.filter(Q(rut__icontains=normalizar_rut(q)) | Q(rut__icontains=q)
                           | Q(instrumento__nombre__icontains=q) | Q(instrumento__nemotecnico__icontains=q))
        if d["tipo"]:
            qs = qs.filter(instrumento__tipo=d["tipo"])
        if d["estado"]:
            qs = qs.filter(estado=d["estado"])
        if d["ejercicio"] and d["ejercicio"].strip().isdigit():
            qs = qs.filter(ejercicio=int(d["ejercicio"]))
    return qs.order_by("-actualizado_en", "-id"), form


@requiere_rol
def calificacion_lista(request):
    qs, form = _filtrar(request)
    paginador = Paginator(qs, POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "calificaciones/lista.html", {
        "form": form, "pagina": pagina, "total": paginador.count,
        "querystring": params.urlencode(), "hay_filtros": any(request.GET.get(k) for k in ("q", "tipo", "estado", "ejercicio")),
    })


def _cambios(antes, despues):
    return {k: [str(antes[k]), str(despues[k])] for k in despues if str(antes.get(k)) != str(despues[k])}


def _foto(c):
    return {"rut": c.rut, "instrumento": c.instrumento.nemotecnico, "ejercicio": c.ejercicio,
            "monto": c.monto, "factor": c.factor, "estado": c.estado}


@requiere_rol
def calificacion_crear(request):
    form = CalificacionForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            obj = form.save(commit=False)
            obj.creado_por = obj.actualizado_por = request.user
            try:
                with transaction.atomic():
                    obj.save()
            except IntegrityError:      # protección ante envíos simultáneos (condición de carrera)
                form.add_error(None, "Ya existe una calificación para este RUT, instrumento y ejercicio.")
            else:
                registrar(request, Auditoria.Accion.CREAR, calificacion=obj, detalle=_foto(obj))
                messages.success(request, "Registro guardado con éxito")
                return redirect("calificacion_lista")
        messages.error(request, "Revise los campos marcados en rojo.")
    return render(request, "calificaciones/formulario.html", {"form": form, "modo": "Nueva calificación"})


@requiere_rol
def calificacion_editar(request, pk):
    obj = get_object_or_404(Calificacion.objects.select_related("instrumento"), pk=pk, eliminado=False)
    antes = _foto(obj)
    form = CalificacionForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            obj = form.save(commit=False)
            obj.actualizado_por = request.user
            try:
                with transaction.atomic():
                    obj.save()
            except IntegrityError:
                form.add_error(None, "Ya existe una calificación para este RUT, instrumento y ejercicio.")
            else:
                registrar(request, Auditoria.Accion.EDITAR, calificacion=obj,
                          detalle={"cambios": _cambios(antes, _foto(obj))})
                messages.success(request, "Registro actualizado con éxito")
                return redirect("calificacion_lista")
        messages.error(request, "Revise los campos marcados en rojo.")
    return render(request, "calificaciones/formulario.html", {"form": form, "modo": "Editar calificación", "obj": obj})


@requiere_rol
def calificacion_detalle(request, pk):
    obj = get_object_or_404(Calificacion.objects.select_related(
        "instrumento", "instrumento__empresa", "creado_por", "actualizado_por"), pk=pk, eliminado=False)
    historial = obj.auditorias.select_related("usuario")
    return render(request, "calificaciones/detalle.html", {"obj": obj, "historial": historial})


@requiere_rol
@require_POST
def calificacion_eliminar(request, pk):
    obj = get_object_or_404(Calificacion, pk=pk, eliminado=False)
    obj.eliminado, obj.eliminado_en, obj.eliminado_por = True, timezone.now(), request.user
    obj.save()
    registrar(request, Auditoria.Accion.ELIMINAR, calificacion=obj, detalle=_foto_segura(obj))
    messages.success(request, "Registro eliminado con éxito")
    return redirect(request.POST.get("next") if (request.POST.get("next", "").startswith("/")
                                                 and not request.POST.get("next", "").startswith("//"))
                    else "calificacion_lista")


def _foto_segura(obj):
    return {"rut": obj.rut, "instrumento": obj.instrumento.nemotecnico, "ejercicio": obj.ejercicio,
            "borrado_logico": True}


# ---------------------------------------------------------------------------
# Exportación (HU19): exactamente los registros filtrados en pantalla
# ---------------------------------------------------------------------------
def _seguro_csv(valor):
    """Evita inyección de fórmulas en Excel/CSV."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


@requiere_rol
def calificacion_exportar(request):
    qs, _ = _filtrar(request)
    formato = request.GET.get("formato", "xlsx")
    encabezado = ["ID", "RUT", "Instrumento", "Nemotécnico", "Tipo", "Ejercicio", "Monto", "Factor",
                  "Estado", "Última modificación"]
    filas = [[c.pk, c.rut, _seguro_csv(c.instrumento.nombre), _seguro_csv(c.instrumento.nemotecnico),
              c.instrumento.get_tipo_display(), c.ejercicio,
              "" if c.monto is None else float(c.monto), "" if c.factor is None else float(c.factor),
              c.get_estado_display(), timezone.localtime(c.actualizado_en).strftime("%Y-%m-%d %H:%M")]
             for c in qs.iterator()]
    registrar(request, Auditoria.Accion.EXPORTAR, detalle={"formato": formato, "registros": len(filas)})
    if formato == "csv":
        salida = io.StringIO()
        escritor = csv.writer(salida)
        escritor.writerow(encabezado)
        escritor.writerows(filas)
        resp = HttpResponse("﻿" + salida.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="calificaciones.csv"'
        return resp
    from openpyxl import Workbook
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Calificaciones"
    hoja.append(encabezado)
    for fila in filas:
        hoja.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    resp = HttpResponse(buffer.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = 'attachment; filename="calificaciones.xlsx"'
    return resp


# ---------------------------------------------------------------------------
# Carga masiva
# ---------------------------------------------------------------------------
@requiere_rol
def carga_masiva(request):
    form = CargaMasivaForm(request.POST or None, request.FILES or None)
    resultado = None
    if request.method == "POST":
        if form.is_valid():
            try:
                resultado = procesar_carga(form.cleaned_data["archivo"], form.cleaned_data["tipo"], request)
                if resultado.filas_error:
                    messages.warning(request, f"Carga procesada con observaciones: {resultado.filas_ok} "
                                              f"registros correctos y {resultado.filas_error} con error.")
                else:
                    messages.success(request, f"Carga finalizada: {resultado.filas_ok} registros procesados con éxito.")
            except ErrorArchivo as exc:
                registrar(request, Auditoria.Accion.CARGA, modulo="Carga masiva", resultado="ERROR",
                          detalle={"archivo": form.cleaned_data["archivo"].name, "motivo": str(exc)})
                messages.error(request, str(exc))
        else:
            codigos = [e.code for e in form.errors.as_data().get("archivo", [])]
            if "empty" in codigos:
                messages.error(request, "El archivo está vacío.")
            else:
                messages.error(request, "Seleccione el tipo de carga y adjunte un archivo.")
    historial = CargaMasiva.objects.select_related("usuario")[:8]
    return render(request, "calificaciones/carga_masiva.html",
                  {"form": form, "resultado": resultado, "historial": historial})


@requiere_rol
def carga_errores_csv(request, pk):
    carga = get_object_or_404(CargaMasiva, pk=pk)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["fila", "rut", "motivo"])
    for e in carga.errores:
        escritor.writerow([e["fila"], _seguro_csv(e["rut"]), e["motivo"]])
    resp = HttpResponse("﻿" + salida.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="errores_carga_{carga.pk}.csv"'
    return resp


# ---------------------------------------------------------------------------
# Otros módulos
# ---------------------------------------------------------------------------
@requiere_rol
def empresas(request):
    q = request.GET.get("q", "").strip()
    qs = EmpresaEmisora.objects.all()
    if q:
        qs = qs.filter(Q(razon_social__icontains=q) | Q(identificador_fiscal__icontains=q))
    return render(request, "calificaciones/empresas.html", {"empresas": qs, "q": q})


@solo_admin
def auditoria_lista(request):
    qs = Auditoria.objects.select_related("usuario", "calificacion__instrumento")
    accion = request.GET.get("accion", "")
    if accion:
        qs = qs.filter(accion=accion)
    pagina = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "calificaciones/auditoria.html",
                  {"pagina": pagina, "acciones": Auditoria.Accion.choices, "accion": accion})


@login_required
def configuracion(request):
    return render(request, "calificaciones/configuracion.html",
                  {"zona_horaria": settings.TIME_ZONE,
                   "expira_min": settings.SESSION_COOKIE_AGE // 60})


def error_403(request, exception=None):
    return render(request, "calificaciones/error.html",
                  {"codigo": 403, "mensaje": "No tiene permisos para acceder a esta sección."}, status=403)


def error_404(request, exception=None):
    return render(request, "calificaciones/error.html",
                  {"codigo": 404, "mensaje": "La página o el registro solicitado no existe."}, status=404)
