"""Pruebas automáticas (unitarias y de integración) del mantenedor. Ejecutar: python manage.py test"""
import io
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Auditoria, Calificacion, EmpresaEmisora, Instrumento
from .permisos import GRUPO_ADMIN, GRUPO_ANALISTA
from .services.rut import calcular_dv, normalizar_rut, rut_es_valido

CLAVE = "Nuam2026!"


def rut(n):
    return f"{n}-{calcular_dv(n)}"


class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        g_an = Group.objects.create(name=GRUPO_ANALISTA)
        g_ad = Group.objects.create(name=GRUPO_ADMIN)
        cls.analista = User.objects.create_user("analista@nuam.cl", "analista@nuam.cl", CLAVE)
        cls.analista.groups.add(g_an)
        cls.admin = User.objects.create_user("admin@nuam.cl", "admin@nuam.cl", CLAVE)
        cls.admin.groups.add(g_ad)
        emp = EmpresaEmisora.objects.create(razon_social="Banco X", identificador_fiscal="97000000-0")
        cls.inst = Instrumento.objects.create(nemotecnico="BX", nombre="Acción X", empresa=emp)

    def entrar(self, user="analista@nuam.cl"):
        self.client.login(username=user, password=CLAVE)


class RutTests(TestCase):
    def test_rut_valido_e_invalido(self):
        self.assertTrue(rut_es_valido(rut(12345678)))
        self.assertFalse(rut_es_valido("12345678-0"))
        self.assertFalse(rut_es_valido("abc"))

    def test_normaliza_puntos_y_guion(self):
        self.assertEqual(normalizar_rut("12.345.678-5"), "12345678-5")
        self.assertEqual(normalizar_rut("123456785"), "12345678-5")


class MantenedorTests(BaseTest):
    def datos(self, **extra):
        d = {"rut": rut(11111111), "instrumento": self.inst.pk, "ejercicio": 2026,
             "monto": "1000.50", "factor": "0.1234", "estado": "PEN"}
        d.update(extra)
        return d

    def test_requiere_sesion(self):
        r = self.client.get(reverse("calificacion_lista"))
        self.assertEqual(r.status_code, 302)

    def test_crear_registra_auditoria_con_decimales(self):
        self.entrar()
        r = self.client.post(reverse("calificacion_crear"), self.datos())
        self.assertEqual(r.status_code, 302)
        c = Calificacion.objects.get()
        self.assertEqual(c.factor, Decimal("0.1234"))
        self.assertTrue(Auditoria.objects.filter(calificacion=c, accion="CREAR", usuario=self.analista).exists())

    def test_monto_negativo_y_factor_invalido(self):
        self.entrar()
        r = self.client.post(reverse("calificacion_crear"), self.datos(monto="-1", factor="0.12345"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Calificacion.objects.exists())
        self.assertContains(r, "no puede ser negativo")
        self.assertContains(r, "4 decimales")

    def test_duplicado_rechazado(self):
        self.entrar()
        self.client.post(reverse("calificacion_crear"), self.datos())
        r = self.client.post(reverse("calificacion_crear"), self.datos())
        self.assertEqual(Calificacion.objects.count(), 1)
        self.assertContains(r, "Ya existe una calificación")

    def test_borrado_logico_y_solo_post(self):
        self.entrar()
        self.client.post(reverse("calificacion_crear"), self.datos())
        c = Calificacion.objects.get()
        self.assertEqual(self.client.get(reverse("calificacion_eliminar", args=[c.pk])).status_code, 405)
        self.client.post(reverse("calificacion_eliminar", args=[c.pk]))
        c.refresh_from_db()
        self.assertTrue(c.eliminado)
        self.assertNotContains(self.client.get(reverse("calificacion_lista")), c.rut)

    def test_paginacion_20(self):
        self.entrar()
        for i in range(25):
            Calificacion.objects.create(rut=rut(13000000 + i), instrumento=self.inst, ejercicio=2026, monto=1)
        r = self.client.get(reverse("calificacion_lista"))
        self.assertEqual(len(r.context["pagina"]), 20)
        self.assertEqual(len(self.client.get(reverse("calificacion_lista") + "?page=2").context["pagina"]), 5)

    def test_auditoria_solo_admin(self):
        self.entrar()
        self.assertEqual(self.client.get(reverse("auditoria")).status_code, 403)
        self.client.logout()
        self.entrar("admin@nuam.cl")
        self.assertEqual(self.client.get(reverse("auditoria")).status_code, 200)


class LoginTests(BaseTest):
    def intentar(self, email, clave):
        return self.client.post(reverse("login"), {"email": email, "password": clave})

    def test_mensaje_igual_exista_o_no_el_correo(self):
        a = self.intentar("analista@nuam.cl", "mala")
        b = self.intentar("fantasma@nuam.cl", "mala")
        self.assertContains(a, "Credenciales inválidas")
        self.assertContains(b, "Credenciales inválidas")

    def test_bloqueo_tras_cinco_intentos(self):
        for _ in range(5):
            self.intentar("analista@nuam.cl", "mala")
        r = self.intentar("analista@nuam.cl", CLAVE)
        self.assertContains(r, "bloqueada")
        self.assertNotIn("_auth_user_id", self.client.session)


class CargaMasivaTests(BaseTest):
    def subir(self, nombre, contenido, tipo="MONTOS"):
        self.entrar()
        archivo = SimpleUploadedFile(nombre, contenido.encode() if isinstance(contenido, str) else contenido)
        return self.client.post(reverse("carga_masiva"), {"tipo": tipo, "archivo": archivo})

    def test_carga_parcial_con_errores(self):
        csv = f"rut,nemotecnico,ejercicio,monto\n{rut(14000000)},BX,2025,100\n12345678-0,BX,2025,5\n{rut(14000001)},BX,2025,-3\n"
        r = self.subir("m.csv", csv)
        carga = r.context["resultado"]
        self.assertEqual((carga.filas_ok, carga.filas_error), (1, 2))
        self.assertEqual(Calificacion.objects.count(), 1)

    def test_formato_no_soportado(self):
        r = self.subir("x.pdf", b"%PDF-1.4")
        self.assertContains(r, "Formato de archivo no soportado")

    def test_archivo_vacio(self):
        r = self.subir("v.csv", b"")
        self.assertContains(r, "El archivo está vacío")

    def test_factores_actualiza_existente(self):
        Calificacion.objects.create(rut=rut(14000000), instrumento=self.inst, ejercicio=2025, monto=1)
        csv = f"rut,nemotecnico,ejercicio,factor\n{rut(14000000)},BX,2025,0.5\n"
        r = self.subir("f.csv", csv, tipo="FACTORES")
        self.assertEqual((r.context["resultado"].creados, r.context["resultado"].actualizados), (0, 1))
        self.assertEqual(Calificacion.objects.get().factor, Decimal("0.5"))

    def test_exportacion_csv_neutraliza_formulas(self):
        self.entrar()
        inst = Instrumento.objects.create(nemotecnico="X1", nombre="=CMD()")
        Calificacion.objects.create(rut=rut(15000000), instrumento=inst, ejercicio=2025, monto=1)
        r = self.client.get(reverse("calificacion_exportar") + "?formato=csv")
        self.assertIn("'=CMD()", r.content.decode())
