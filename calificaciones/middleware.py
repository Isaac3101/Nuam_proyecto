class CabecerasSeguridadMiddleware:
    """Agrega cabeceras de seguridad (CSP, Permissions-Policy) a todas las respuestas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if not request.path.startswith("/admin/"):
            respuesta.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                "script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        respuesta.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return respuesta
