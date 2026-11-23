from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("calificaciones.urls")),
]

handler403 = "calificaciones.views.error_403"
handler404 = "calificaciones.views.error_404"
