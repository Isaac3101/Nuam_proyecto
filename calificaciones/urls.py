from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("acceso/", views.login_view, name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("calificaciones/", views.calificacion_lista, name="calificacion_lista"),
    path("calificaciones/nueva/", views.calificacion_crear, name="calificacion_crear"),
    path("calificaciones/exportar/", views.calificacion_exportar, name="calificacion_exportar"),
    path("calificaciones/<int:pk>/", views.calificacion_detalle, name="calificacion_detalle"),
    path("calificaciones/<int:pk>/editar/", views.calificacion_editar, name="calificacion_editar"),
    path("calificaciones/<int:pk>/eliminar/", views.calificacion_eliminar, name="calificacion_eliminar"),
    path("carga-masiva/", views.carga_masiva, name="carga_masiva"),
    path("carga-masiva/<int:pk>/errores.csv", views.carga_errores_csv, name="carga_errores_csv"),
    path("empresas/", views.empresas, name="empresas"),
    path("auditoria/", views.auditoria_lista, name="auditoria"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("configuracion/clave/", auth_views.PasswordChangeView.as_view(
        template_name="calificaciones/cambiar_clave.html",
        success_url=reverse_lazy("configuracion")), name="cambiar_clave"),
]
