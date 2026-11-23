import json

from django.core.serializers.json import DjangoJSONEncoder

from .models import Auditoria


def ip_cliente(request):
    return request.META.get("REMOTE_ADDR") or None


def registrar(request, accion, calificacion=None, detalle=None, modulo="Calificaciones",
              resultado="OK", usuario_texto=""):
    usuario = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    return Auditoria.objects.create(
        usuario=usuario,
        usuario_texto=usuario.get_username() if usuario else usuario_texto,
        accion=accion, modulo=modulo, resultado=resultado,
        calificacion=calificacion,
        # Se normaliza a JSON seguro (Decimal, fechas) antes de guardar en el campo JSON
        detalle=json.loads(json.dumps(detalle or {}, cls=DjangoJSONEncoder)),
        ip=ip_cliente(request))
