from django.contrib import admin

from .models import Auditoria, Calificacion, CargaMasiva, EmpresaEmisora, Instrumento


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("rut", "instrumento", "ejercicio", "monto", "factor", "estado", "eliminado")
    list_filter = ("estado", "eliminado", "ejercicio")
    search_fields = ("rut", "instrumento__nemotecnico")


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario_texto", "accion", "modulo", "resultado")
    list_filter = ("accion", "resultado")
    readonly_fields = [f.name for f in Auditoria._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(EmpresaEmisora)
admin.site.register(Instrumento)
admin.site.register(CargaMasiva)
