"""Carga datos de demostración: roles, usuarios, empresas, instrumentos y calificaciones."""
import random
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from calificaciones.models import Calificacion, EmpresaEmisora, Instrumento
from calificaciones.permisos import GRUPO_ADMIN, GRUPO_ANALISTA
from calificaciones.services.rut import calcular_dv

CLAVE_DEMO = "Nuam2026!"

EMPRESAS = [
    ("Banco de Chile", "CL", "97004000-5", "SA"), ("Falabella S.A.", "CL", "90749000-9", "SA"),
    ("Empresas COPEC", "CL", "90690000-9", "SA"), ("SQM", "CL", "93007000-9", "SA"),
    ("Credicorp Ltd.", "PE", "20100047218", "SA"), ("Southern Copper Perú", "PE", "20100147514", "SA"),
    ("Bancolombia", "CO", "890903938-8", "SA"), ("Ecopetrol", "CO", "899999068-1", "SA"),
    ("Inversiones del Sur SpA", "CL", "76123456-0", "SPA"),
]
INSTRUMENTOS = [
    ("CHILE", "Acción Banco de Chile", "ACC", 0), ("FALABELLA", "Acción Falabella", "ACC", 1),
    ("COPEC", "Acción Empresas COPEC", "ACC", 2), ("SQM-B", "Acción SQM Serie B", "ACC", 3),
    ("BAP", "Acción Credicorp", "ACC", 4), ("SCCO", "Acción Southern Copper", "ACC", 5),
    ("BCOLOMBIA", "Acción Bancolombia", "ACC", 6), ("ECOPETROL", "Acción Ecopetrol", "ACC", 7),
    ("BFAL-A", "Bono Falabella Serie A", "BON", 1), ("BCHI-F", "Bono Banco de Chile F", "BON", 0),
    ("FISUR-I", "Fondo Inversiones del Sur", "FON", 8), ("BCOL-B", "Bono Bancolombia B", "BON", 6),
]


def rut_valido(n):
    return f"{n}-{calcular_dv(n)}"


class Command(BaseCommand):
    help = "Crea datos de demostración para el sistema NUAM"

    def handle(self, *args, **opts):
        admin_g, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
        analista_g, _ = Group.objects.get_or_create(name=GRUPO_ANALISTA)
        usuarios = [("admin@nuam.cl", "Administrador", "NUAM", admin_g, True),
                    ("analista@nuam.cl", "Analista", "Tributario", analista_g, False),
                    ("analista2@nuam.cl", "Segundo", "Analista", analista_g, False)]
        for email, nombre, apellido, grupo, staff in usuarios:
            u, creado = User.objects.get_or_create(username=email, defaults={
                "email": email, "first_name": nombre, "last_name": apellido, "is_staff": staff,
                "is_superuser": staff})
            if creado:
                u.set_password(CLAVE_DEMO)
                u.save()
            u.groups.add(grupo)

        empresas = []
        for razon, pais, ident, tipo in EMPRESAS:
            e, _ = EmpresaEmisora.objects.get_or_create(identificador_fiscal=ident, defaults={
                "razon_social": razon, "pais": pais, "tipo_sociedad": tipo})
            empresas.append(e)
        instrumentos = []
        for nemo, nombre, tipo, idx in INSTRUMENTOS:
            i, _ = Instrumento.objects.get_or_create(nemotecnico=nemo, defaults={
                "nombre": nombre, "tipo": tipo, "empresa": empresas[idx]})
            instrumentos.append(i)

        if not Calificacion.objects.exists():
            azar = random.Random(2026)
            analista = User.objects.get(username="analista@nuam.cl")
            ruts = [rut_valido(n) for n in range(12000000, 12000000 + 60 * 137, 137)]
            estados = ["PEN", "APR", "APR", "OBS"]
            for i, rut in enumerate(ruts):
                inst = instrumentos[i % len(instrumentos)]
                Calificacion.objects.create(
                    rut=rut, instrumento=inst, ejercicio=2024 + (i % 3),
                    monto=Decimal(azar.randint(500000, 90000000)),
                    factor=Decimal(str(round(azar.uniform(0.05, 0.95), 4))),
                    estado=estados[i % 4], creado_por=analista, actualizado_por=analista)
        self.stdout.write(self.style.SUCCESS(
            f"Datos de demostración listos. Usuarios: admin@nuam.cl / analista@nuam.cl (clave {CLAVE_DEMO})"))
