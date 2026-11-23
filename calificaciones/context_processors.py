from .permisos import es_admin, rol_de

_SECCIONES = {
    "dashboard": "dashboard", "calificacion_lista": "calificaciones", "calificacion_crear": "calificaciones",
    "calificacion_editar": "calificaciones", "calificacion_detalle": "calificaciones",
    "carga_masiva": "carga", "empresas": "empresas", "auditoria": "auditoria",
    "configuracion": "configuracion", "cambiar_clave": "configuracion",
}


def navegacion(request):
    contexto = {}
    if request.user.is_authenticated:
        contexto.update({"es_admin": es_admin(request.user), "rol_usuario": rol_de(request.user)})
        match = getattr(request, "resolver_match", None)
        contexto["seccion"] = _SECCIONES.get(match.url_name if match else "", "")
    return contexto
