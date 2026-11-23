(function () {
  "use strict";

  // Notificaciones tipo toast: aparecen y desaparecen solas (HU20)
  document.querySelectorAll("#toasts .toast").forEach(function (t) {
    setTimeout(function () { t.classList.add("sale"); }, 4000);
    setTimeout(function () { t.remove(); }, 4500);
  });

  // Modal de confirmación de eliminación (HU11)
  var modal = document.getElementById("modal-eliminar");
  if (modal) {
    var form = document.getElementById("form-eliminar");
    var detalle = document.getElementById("modal-detalle");
    document.querySelectorAll(".js-eliminar").forEach(function (b) {
      b.addEventListener("click", function () {
        form.setAttribute("action", b.dataset.url);
        detalle.textContent = b.dataset.nombre || "";
        modal.hidden = false;
        document.getElementById("modal-cancelar").focus();
      });
    });
    var cerrar = function () { modal.hidden = true; };
    document.getElementById("modal-cancelar").addEventListener("click", cerrar);
    modal.addEventListener("click", function (e) { if (e.target === modal) cerrar(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") cerrar(); });
    // Evita doble envío al confirmar
    form.addEventListener("submit", function () {
      document.getElementById("modal-aceptar").disabled = true;
    });
  }

  // Instrumento no inscrito: muestra campos adicionales (HU6)
  var check = document.getElementById("id_no_inscrito");
  if (check) {
    var inscrito = document.getElementById("bloque-inscrito");
    var extra = document.getElementById("bloque-no-inscrito");
    var alternar = function () {
      extra.hidden = !check.checked;
      inscrito.hidden = check.checked;
    };
    check.addEventListener("change", alternar);
    alternar();
  }

  // Evita doble envío de formularios
  document.querySelectorAll("form#form-calificacion, form#form-carga").forEach(function (f) {
    f.addEventListener("submit", function () {
      var b = f.querySelector("button[type=submit]");
      if (b) { setTimeout(function () { b.disabled = true; }, 0); }
    });
  });
})();
