document.body.addEventListener("click", function (event) {
  var button = event.target.closest("[data-action='pick-folder']");
  if (!button) {
    return;
  }

  var form = button.closest(".add-project-form");
  if (!form) {
    return;
  }

  var input = form.querySelector("#folder_path");
  if (!input) {
    return;
  }

  var toast = document.getElementById("nav-toast");
  button.disabled = true;
  var label = button.textContent;
  button.textContent = "Abriendo…";

  fetch("/api/projects/pick-folder")
    .then(function (response) {
      return response.json();
    })
    .then(function (data) {
      if (data.ok && data.path) {
        input.value = data.path;
        input.focus();
        return;
      }
      if (toast && data.message) {
        toast.innerHTML =
          '<div class="notice-banner notice-banner--error">' + data.message + "</div>";
      }
    })
    .catch(function () {
      if (toast) {
        toast.innerHTML =
          '<div class="notice-banner notice-banner--error">No se pudo abrir el selector de carpeta.</div>';
      }
    })
    .finally(function () {
      button.disabled = false;
      button.textContent = label;
    });
});
