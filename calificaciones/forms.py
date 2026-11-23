from decimal import Decimal, InvalidOperation

from django import forms

from .models import Calificacion, Instrumento, Pais
from .services.rut import normalizar_rut


class DecimalComa(forms.DecimalField):
    """DecimalField que acepta coma o punto y entrega mensajes claros en español."""

    default_error_messages = {"invalid": "Ingrese un valor numérico válido."}

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip().replace(" ", "")
            if "," in value and "." not in value:
                value = value.replace(",", ".")
        return super().to_python(value)


class CalificacionForm(forms.ModelForm):
    required_css_class = "required"

    monto = DecimalComa(required=False, min_value=Decimal("0"), max_digits=18, decimal_places=2,
                        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0.00"}),
                        error_messages={
                            "min_value": "El monto no puede ser negativo.",
                            "max_decimal_places": "El monto admite como máximo 2 decimales.",
                            "max_digits": "El monto excede la cantidad de dígitos permitida.",
                            "invalid": "El monto debe ser un valor numérico."})
    factor = DecimalComa(required=False, min_value=Decimal("0"), max_value=Decimal("1"),
                         max_digits=8, decimal_places=4,
                         widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0.0000"}),
                         error_messages={
                             "min_value": "El factor no puede ser negativo.",
                             "max_value": "El factor no puede ser mayor a 1.",
                             "max_decimal_places": "El factor admite como máximo 4 decimales.",
                             "max_digits": "El factor excede la cantidad de dígitos permitida.",
                             "invalid": "El factor debe ser un valor numérico."})

    # --- Instrumento no inscrito (HU6) ---
    no_inscrito = forms.BooleanField(required=False, label="Instrumento no inscrito")
    ni_nombre = forms.CharField(required=False, max_length=150, label="Nombre del instrumento")
    ni_tipo = forms.ChoiceField(required=False, choices=Instrumento.Tipo.choices,
                                label="Tipo de instrumento")
    ni_emisor = forms.CharField(required=False, max_length=150, label="Emisor externo")
    ni_pais = forms.ChoiceField(required=False, choices=[("", "---------")] + list(Pais.choices),
                                label="País de origen")
    ni_observacion = forms.CharField(required=False, max_length=300, label="Observación",
                                     widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Calificacion
        fields = ["rut", "instrumento", "ejercicio", "monto", "factor", "estado"]
        widgets = {"rut": forms.TextInput(attrs={"placeholder": "12345678-5", "autocomplete": "off"}),
                   "ejercicio": forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "2026"})}
        error_messages = {"ejercicio": {"invalid": "El ejercicio debe ser un año numérico.",
                                        "required": "Este campo es obligatorio."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instrumento"].queryset = Instrumento.objects.filter(inscrito=True)
        self.fields["instrumento"].required = False
        self.fields["instrumento"].empty_label = "Seleccione un instrumento"
        self.fields["rut"].label = "RUT del contribuyente"
        self.fields["ejercicio"].label = "Ejercicio (año)"
        # Se muestra "Instrumento" como obligatorio salvo que sea no inscrito
        self.fields["instrumento"].label = "Instrumento"
        for campo in ("rut", "ejercicio"):
            self.fields[campo].error_messages["required"] = "Este campo es obligatorio."
        inst = self.instance.instrumento if self.instance.pk else None
        self._instrumento_original = inst
        if inst is not None and not inst.inscrito:
            self.initial.update({
                "no_inscrito": True, "ni_nombre": inst.nombre, "ni_tipo": inst.tipo,
                "ni_emisor": inst.emisor_externo, "ni_pais": inst.pais_origen,
                "ni_observacion": inst.observacion})

    def clean_rut(self):
        return normalizar_rut(self.cleaned_data.get("rut"))

    def clean(self):
        datos = super().clean()
        if datos.get("no_inscrito"):
            for campo in ("ni_nombre", "ni_emisor", "ni_pais"):
                if not datos.get(campo):
                    self.add_error(campo, "Este campo es obligatorio para instrumentos no inscritos.")
            self.errors.pop("instrumento", None)
            datos["instrumento"] = None
        else:
            if not datos.get("instrumento") and "instrumento" not in self.errors:
                self.add_error("instrumento", "Este campo es obligatorio.")
        # Duplicado: misma combinación RUT + instrumento + ejercicio entre registros activos
        if (datos.get("rut") and datos.get("instrumento") and datos.get("ejercicio")
                and not self.errors):
            existe = Calificacion.objects.filter(
                eliminado=False, rut=datos["rut"], instrumento=datos["instrumento"],
                ejercicio=datos["ejercicio"]).exclude(pk=self.instance.pk)
            if existe.exists():
                self.add_error(None, "Ya existe una calificación para este RUT, instrumento y ejercicio.")
        if (datos.get("monto") is None and datos.get("factor") is None
                and "monto" not in self.errors and "factor" not in self.errors):
            self.add_error("monto", "Debe informar al menos un monto o un factor.")
        return datos

    def save(self, commit=True):
        datos = self.cleaned_data
        if datos.get("no_inscrito"):
            inst = None
            original = self._instrumento_original
            if original is not None and not original.inscrito:
                inst = original
            if inst is None:
                inst = Instrumento(inscrito=False)
                inst.nemotecnico = f"NI-{Instrumento.objects.filter(inscrito=False).count() + 1:05d}"
                while Instrumento.objects.filter(nemotecnico=inst.nemotecnico).exists():
                    inst.nemotecnico += "X"
            inst.nombre = datos["ni_nombre"]
            inst.tipo = datos.get("ni_tipo") or Instrumento.Tipo.OTRO
            inst.emisor_externo = datos["ni_emisor"]
            inst.pais_origen = datos["ni_pais"]
            inst.observacion = datos.get("ni_observacion", "")
            inst.save()
            self.instance.instrumento = inst
        return super().save(commit=commit)


class FiltroCalificacionForm(forms.Form):
    q = forms.CharField(required=False, label="Buscar",
                        widget=forms.TextInput(attrs={"placeholder": "RUT, instrumento o nemotécnico"}))
    tipo = forms.ChoiceField(required=False, label="Tipo de instrumento",
                             choices=[("", "Todos los tipos")] + list(Instrumento.Tipo.choices))
    estado = forms.ChoiceField(required=False, label="Estado",
                               choices=[("", "Todos los estados")] + list(Calificacion.Estado.choices))
    ejercicio = forms.CharField(required=False, label="Ejercicio",
                                widget=forms.TextInput(attrs={"placeholder": "Año", "inputmode": "numeric"}))


class CargaMasivaForm(forms.Form):
    tipo = forms.ChoiceField(label="Tipo de carga", choices=[
        ("MONTOS", "Montos - DJ1948"), ("FACTORES", "Factores")])
    archivo = forms.FileField(label="Archivo (.xlsx o .csv)")
