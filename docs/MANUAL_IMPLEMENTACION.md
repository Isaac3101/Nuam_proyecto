# Manual de implementación y mantenimiento

Complementa al `README.md`. Explica cómo está construido el sistema para poder repetirlo, mantenerlo y extenderlo.

## 1. Decisiones de diseño
| Decisión | Motivo |
|---|---|
| Django (arquitectura MVT) | Incluye autenticación, ORM, protección CSRF/XSS y migraciones; acelera un desarrollo seguro |
| PostgreSQL 16 | Decisión del informe: ACID, `numeric` exacto para montos/factores, `JSONB`, índices parciales |
| Plantillas HTML + CSS/JS propios | Sin dependencias externas; permite una política CSP estricta (`script-src 'self'`) |
| Capa `services/` | Aísla reglas de negocio reutilizables (RUT, carga masiva) de las vistas |
| Borrado lógico | Conserva trazabilidad tributaria (HU10/HU18) |
| `IntentoLogin` por correo escrito | Bloquea sin revelar si el correo existe (anti-enumeración) |

## 2. Flujo de una petición
`Navegador → urls.py → vista (views.py) → formulario/servicio → modelo (ORM) → PostgreSQL → plantilla HTML`.
Cada acción relevante pasa por `auditoria.registrar()`, que guarda usuario, fecha, IP y detalle (JSON).

## 3. Mapa HU → implementación
| HU | Funcionalidad | Ruta | Vista / archivo |
|---|---|---|---|
| 1–3 | Listado, búsqueda, paginación (20) | `/calificaciones/` | `calificacion_lista`, `_filtrar` |
| 4–8 | Crear con validaciones, no inscritos, montos y factores | `/calificaciones/nueva/` | `calificacion_crear`, `forms.CalificacionForm` |
| 9 | Editar | `/calificaciones/<id>/editar/` | `calificacion_editar` |
| 10–11 | Eliminar (lógico) con modal de confirmación | `POST /calificaciones/<id>/eliminar/` | `calificacion_eliminar`, `lista.html` + `app.js` |
| 12–16 | Carga masiva, validación de formato, reporte de errores | `/carga-masiva/` | `carga_masiva`, `services/cargas.py` |
| 17–18 | Detalle solo lectura + historial | `/calificaciones/<id>/` | `calificacion_detalle` |
| 18 | Auditoría global (Administrador) | `/auditoria/` | `auditoria_lista` |
| 19 | Exportar Excel/CSV filtrado | `/calificaciones/exportar/` | `calificacion_exportar` |
| 20 | Toasts de confirmación | todas | `django.contrib.messages` + `app.js` |
| Seguridad | Login, bloqueo, roles | `/acceso/` | `login_view`, `permisos.py` |

## 4. Reglas de negocio implementadas
- **RUT**: formato `12345678-5`, dígito verificador módulo 11 (`services/rut.py`).
- **Monto**: numérico, ≥ 0, máximo 2 decimales (`numeric(18,2)`).
- **Factor**: numérico entre 0 y 1, máximo 4 decimales (`numeric(8,4)`).
- **Ejercicio**: año entre 2000 y 2100.
- **Unicidad**: no pueden existir dos calificaciones activas con el mismo RUT + instrumento + ejercicio
  (restricción parcial en BD + validación en formulario).
- **Carga masiva**: .csv/.xlsx, máx. 5 MB y 10.000 filas; columnas `rut, nemotecnico, ejercicio, monto|factor`;
  las filas correctas se cargan y las erróneas se informan con fila y motivo; si la combinación existe se actualiza.

## 5. Tareas frecuentes de mantenimiento
| Tarea | Cómo |
|---|---|
| Agregar un campo a `Calificacion` | Editar `models.py` → `python manage.py makemigrations` → `python manage.py migrate` → agregarlo en `forms.py` y plantillas |
| Crear un usuario | `/admin/` (como administrador) o `python manage.py createsuperuser`; asignarle el grupo *Analista Tributario* o *Administrador* |
| Cambiar política de bloqueo | `LOGIN_MAX_INTENTOS` y `LOGIN_BLOQUEO_MINUTOS` en `nuam/settings.py` |
| Cambiar tamaño máximo de carga | `CARGA_MAX_BYTES` y `CARGA_MAX_FILAS` en `settings.py` |
| Respaldar la BD | `pg_dump -U postgres nuam > respaldo.sql` |
| Restaurar | `psql -U postgres nuam < respaldo.sql` |
| Regenerar datos demo limpios | `bash pruebas/preparar_ambiente.sh` |

## 6. Pruebas
Tres niveles: (1) `python manage.py test` (16 pruebas unitarias/integración); (2) plan de pruebas funcionales de caja negra
(`pruebas/casos.py`, 51 casos) ejecutado con `pruebas/run_e2e.py`, que genera evidencias `EV-CP-XX.png` por ciclo en
`pruebas/resultados/cicloN/`; (3) estrés (carga de 5.000 filas y listado con 5.000+ registros).

## 7. Convenciones de equipo
- Rama `main` estable; trabajo en ramas `feature/<hu>-<tema>` con *pull request* revisado por el otro integrante.
- Mensajes de *commit* en infinitivo: `Agregar validación de factor (HU8)`.
- Ninguna contraseña o clave en el repositorio: todo en `.env` (ignorado por Git).
- Antes de integrar: `python manage.py test` en verde.
