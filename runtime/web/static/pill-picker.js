(function () {
  document.addEventListener(
    "toggle",
    function (event) {
      var target = event.target;
      if (!target.matches || !target.matches(".pill-picker") || !target.open) {
        return;
      }
      document.querySelectorAll(".pill-picker[open]").forEach(function (picker) {
        if (picker !== target) {
          picker.open = false;
        }
      });
    },
    true
  );

  document.addEventListener("click", function (event) {
    if (event.target.closest(".pill-picker")) {
      return;
    }
    document.querySelectorAll(".pill-picker[open]").forEach(function (picker) {
      picker.open = false;
    });
  });
})();
