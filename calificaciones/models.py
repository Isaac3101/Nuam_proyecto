from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .services.rut import validar_rut


class Pais(models.TextChoices):
    CHILE = "CL", "Chile"
    PERU = "PE", "Perú"
    COLOMBIA = "CO", "Colombia"


class EmpresaEmisora(models.Model):
    """Catálogo maestro de empresas emisoras de instrumentos."""

    class TipoSociedad(models.TextChoices):
        SA = "SA", "Sociedad Anónima"
        SPA = "SPA", "Sociedad por Acciones"
        LTDA = "LTDA", "Limitada"
        OTRO = "OTRO", "Otro"

    razon_social = models.CharField(max_length=150)
    pais = models.CharField(max_length=2, choices=Pais.choices, default=Pais.CHILE)
    identificador_fiscal = models.CharField(max_length=20, unique=True)
    tipo_sociedad = models.CharField(max_length=5, choices=TipoSociedad.choices,
                                     default=TipoSociedad.SA)
    vigente = models.BooleanField(default=True)

    class Meta:
        ordering = ["razon_social"]
        verbose_name = "empresa emisora"
        verbose_name_plural = "empresas emisoras"

    def __str__(self):
        return self.razon_social


class Instrumento(models.Model):
    """Instrumento bursátil. Puede estar inscrito (catálogo) o ser no inscrito."""

    class Tipo(models.TextChoices):
        ACCION = "ACC", "Acción"
        BONO = "BON", "Bono"
        FONDO = "FON", "Fondo de inversión"
        OTRO = "OTR", "Otro"

    nemotecnico = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=3, choices=Tipo.choices, default=Tipo.ACCION)
    inscrito = models.BooleanField(default=True)
    empresa = models.ForeignKey(EmpresaEmisora, null=True, blank=True,
                                on_delete=models.PROTECT, related_name="instrumentos")
    # Campos adicionales para instrumentos no inscritos (HU6)
    emisor_externo = models.CharField(max_length=150, blank=True)
    pais_origen = models.CharField(max_length=2, choices=Pais.choices, blank=True)
    observacion = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["nemotecnico"]
        indexes = [models.Index(fields=["tipo"], name="idx_instr_tipo")]

    def __str__(self):
        return f"{self.nemotecnico} - {self.nombre}"


class Calificacion(models.Model):
    """Calificación tributaria de un contribuyente sobre un instrumento y ejercicio."""

    class Estado(models.TextChoices):
        PENDIENTE = "PEN", "Pendiente"
        APROBADA = "APR", "Aprobada"
        OBSERVADA = "OBS", "Observada"

    rut = models.CharField("RUT", max_length=12, validators=[validar_rut])
    instrumento = models.ForeignKey(Instrumento, on_delete=models.PROTECT,
                                    related_name="calificaciones")
    ejercicio = models.PositiveSmallIntegerField(
        "Ejercicio (año)",
        validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    monto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True,
                                validators=[MinValueValidator(Decimal("0"))])
    factor = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                 validators=[MinValueValidator(Decimal("0")),
                                             MaxValueValidator(Decimal("1"))])
    estado = models.CharField(max_length=3, choices=Estado.choices, default=Estado.PENDIENTE)

    # Borrado lógico (HU10)
    eliminado = models.BooleanField(default=False)
    eliminado_en = models.DateTimeField(null=True, blank=True)
    eliminado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="+")

    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-actualizado_en", "-id"]
        verbose_name = "calificación"
        verbose_name_plural = "calificaciones"
        indexes = [
            models.Index(fields=["rut"], name="idx_calif_rut"),
            models.Index(fields=["eliminado", "estado"], name="idx_calif_elim_estado"),
            models.Index(fields=["ejercicio"], name="idx_calif_ejercicio"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["rut", "instrumento", "ejercicio"],
                condition=Q(eliminado=False),
                name="uq_calif_rut_instr_ejercicio_activa",
                violation_error_message=(
                    "Ya existe una calificación para este RUT, instrumento y ejercicio."),
            ),
            models.CheckConstraint(condition=Q(monto__gte=0) | Q(monto__isnull=True),
                                   name="ck_calif_monto_no_negativo"),
            models.CheckConstraint(
                condition=(Q(factor__gte=0) & Q(factor__lte=1)) | Q(factor__isnull=True),
                name="ck_calif_factor_0_1"),
        ]

    def __str__(self):
        return f"{self.rut} / {self.instrumento.nemotecnico} / {self.ejercicio}"


class Auditoria(models.Model):
    """Registro de trazabilidad: quién hizo qué y cuándo (HU18)."""

    class Accion(models.TextChoices):
        LOGIN = "LOGIN", "Inicio de sesión"
        LOGIN_FALLIDO = "LOGIN_FALLIDO", "Inicio de sesión fallido"
        BLOQUEO = "BLOQUEO", "Cuenta bloqueada"
        LOGOUT = "LOGOUT", "Cierre de sesión"
        CREAR = "CREAR", "Creación"
        EDITAR = "EDITAR", "Edición"
        ELIMINAR = "ELIMINAR", "Eliminación"
        CARGA = "CARGA", "Carga masiva"
        EXPORTAR = "EXPORTAR", "Exportación"

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")
    usuario_texto = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=15, choices=Accion.choices)
    modulo = models.CharField(max_length=40, default="Calificaciones")
    resultado = models.CharField(max_length=5, default="OK")
    calificacion = models.ForeignKey(Calificacion, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="auditorias")
    detalle = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario_texto} {self.accion}"


class CargaMasiva(models.Model):
    class Tipo(models.TextChoices):
        MONTOS = "MONTOS", "Montos - DJ1948"
        FACTORES = "FACTORES", "Factores"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    nombre_archivo = models.CharField(max_length=255)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                on_delete=models.SET_NULL, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    total_filas = models.PositiveIntegerField(default=0)
    filas_ok = models.PositiveIntegerField(default=0)
    filas_error = models.PositiveIntegerField(default=0)
    creados = models.PositiveIntegerField(default=0)
    actualizados = models.PositiveIntegerField(default=0)
    errores = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name_plural = "cargas masivas"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nombre_archivo}"


class IntentoLogin(models.Model):
    """
    Control de intentos fallidos por correo ingresado (exista o no el usuario),
    para bloquear la cuenta sin revelar si el correo está registrado (CA-01.2/CA-01.3).
    """
    email = models.CharField(max_length=254, unique=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.email
