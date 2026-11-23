from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

GRUPO_ADMIN = "Administrador"
GRUPO_ANALISTA = "Analista Tributario"


def es_admin(usuario):
    return usuario.is_authenticated and (
        usuario.is_superuser or usuario.groups.filter(name=GRUPO_ADMIN).exists())


def rol_de(usuario):
    if es_admin(usuario):
        return GRUPO_ADMIN
    if usuario.groups.filter(name=GRUPO_ANALISTA).exists():
        return GRUPO_ANALISTA
    return "Sin rol"


def solo_admin(vista):
    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if not es_admin(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envoltura


def requiere_rol(vista):
    """Exige sesión iniciada y un rol asignado (Analista o Administrador)."""
    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if rol_de(request.user) == "Sin rol":
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envoltura
