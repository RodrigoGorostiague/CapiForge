(function () {
  var KEY = "capiforge.sidebar.collapsed";
  var MOBILE_QUERY = "(max-width: 960px)";
  var shell = document.getElementById("app-shell");
  var toggle = document.getElementById("sidebar-toggle");
  var backdrop = document.getElementById("sidebar-backdrop");
  var nav = document.getElementById("sidebar-nav");
  if (!shell || !toggle) {
    return;
  }

  var mobile = window.matchMedia(MOBILE_QUERY);

  function setCollapsed(collapsed) {
    document.documentElement.classList.remove("sidebar-collapsed-init");
    shell.classList.toggle("sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.setAttribute("aria-label", collapsed ? "Mostrar menú" : "Ocultar menú");
    toggle.textContent = collapsed ? "☰" : "×";
    if (backdrop) {
      backdrop.setAttribute("aria-hidden", collapsed ? "true" : "false");
    }
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch (error) {
      /* ignore */
    }
  }

  function applyInitialState() {
    var stored = null;
    try {
      stored = localStorage.getItem(KEY);
    } catch (error) {
      stored = null;
    }
    if (mobile.matches) {
      setCollapsed(stored !== "0");
      return;
    }
    setCollapsed(stored === "1");
  }

  applyInitialState();

  toggle.addEventListener("click", function () {
    setCollapsed(!shell.classList.contains("sidebar-collapsed"));
  });

  if (backdrop) {
    backdrop.addEventListener("click", function () {
      if (mobile.matches) {
        setCollapsed(true);
      }
    });
  }

  if (nav) {
    nav.addEventListener("click", function (event) {
      if (!mobile.matches) {
        return;
      }
      if (event.target.closest("a.sidebar-link, a.sidebar-node, button.sidebar-add-project")) {
        setCollapsed(true);
      }
    });
  }

  mobile.addEventListener("change", function () {
    applyInitialState();
  });
})();
