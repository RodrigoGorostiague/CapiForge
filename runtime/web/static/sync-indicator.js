(function () {
  var FRESHNESS = {
    live: { label: "Al día", dotClass: "sync-dot--live" },
    connecting: { label: "Conectando", dotClass: "sync-dot--connecting" },
    pending: { label: "Cambios nuevos", dotClass: "sync-dot--pending" },
    updating: { label: "Actualizando", dotClass: "sync-dot--updating" },
    stale: { label: "Desactualizado", dotClass: "sync-dot--stale" },
    offline: { label: "Sin tiempo real", dotClass: "sync-dot--offline" },
  };

  var PRIORITY = {
    stale: 5,
    updating: 4,
    pending: 3,
    connecting: 2,
    live: 1,
    offline: 0,
  };

  var sync = document.getElementById("app-sync-status");
  if (!sync) {
    return;
  }

  var dot = sync.querySelector(".sync-dot");
  var label = sync.querySelector(".sync-label");
  var realtimeEnabled = sync.dataset.realtime === "1";
  var fallbackSeconds = parseInt(sync.dataset.fallbackSeconds || "0", 10) || 0;
  var coordLabel = sync.dataset.coordLabel || "";
  var currentState = realtimeEnabled ? "connecting" : fallbackSeconds > 0 ? "live" : "offline";
  var htmxPending = 0;
  var pendingChanges = false;

  function isContentRefreshRequest(path) {
    if (!path) {
      return false;
    }
    if (path.indexOf("/api/partials/sync-status") !== -1) {
      return false;
    }
    return (
      path.indexOf("/api/partials/") !== -1 ||
      path.indexOf("/api/tasks/") !== -1 ||
      path === "/tasks" ||
      path.indexOf("/tasks?") === 0 ||
      path === "/" ||
      path.indexOf("/?") === 0 ||
      path === "/docs" ||
      path.indexOf("/docs?") === 0
    );
  }

  function buildTitle(stateKey) {
    var parts = [];
    var freshness = FRESHNESS[stateKey];
    if (freshness) {
      parts.push("Vista: " + freshness.label);
    }
    if (coordLabel) {
      parts.push(coordLabel);
    }
    if (fallbackSeconds > 0) {
      parts.push("Fallback polling " + fallbackSeconds + "s");
    } else if (realtimeEnabled) {
      parts.push("Realtime SSE");
    }
    return parts.join(" · ");
  }

  function applyState(stateKey, options) {
    var opts = options || {};
    if (!FRESHNESS[stateKey]) {
      return;
    }
    if (!opts.force && PRIORITY[stateKey] < PRIORITY[currentState]) {
      return;
    }
    currentState = stateKey;
    if (!dot || !label) {
      return;
    }
    dot.className = "sync-dot " + FRESHNESS[stateKey].dotClass;
    label.textContent = FRESHNESS[stateKey].label;
    sync.classList.toggle("is-refreshing", stateKey === "updating" || stateKey === "pending");
    sync.classList.toggle("is-stale", stateKey === "stale");
    sync.title = buildTitle(stateKey);
  }

  function recomputeState() {
    if (htmxPending > 0) {
      applyState("updating", { force: true });
      return;
    }
    if (pendingChanges) {
      applyState("pending", { force: true });
      return;
    }
    if (currentState === "stale") {
      return;
    }
    if (realtimeEnabled && currentState === "connecting") {
      return;
    }
    if (realtimeEnabled || fallbackSeconds > 0) {
      applyState("live", { force: true });
      return;
    }
    applyState("offline", { force: true });
  }

  window.CapiForgeSync = {
    markConnecting: function () {
      applyState("connecting", { force: true });
    },
    markLive: function () {
      pendingChanges = false;
      if (htmxPending > 0) {
        return;
      }
      applyState("live", { force: true });
    },
    markPending: function () {
      pendingChanges = true;
      recomputeState();
    },
    markUpdating: function () {
      applyState("updating", { force: true });
    },
    markStale: function () {
      applyState("stale", { force: true });
    },
    markOffline: function () {
      applyState("offline", { force: true });
    },
    setCoordMeta: function (coordState, coordLabelText) {
      if (coordLabelText) {
        coordLabel = coordLabelText;
        sync.dataset.coordLabel = coordLabelText;
      }
      if (coordState) {
        sync.dataset.coordState = coordState;
      }
      sync.title = buildTitle(currentState);
    },
  };

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isContentRefreshRequest(path)) {
      return;
    }
    htmxPending += 1;
    applyState("updating", { force: true });
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isContentRefreshRequest(path)) {
      return;
    }
    htmxPending = Math.max(0, htmxPending - 1);
    if (event.detail.successful) {
      pendingChanges = false;
    } else if (pendingChanges || realtimeEnabled) {
      applyState("stale", { force: true });
      return;
    }
    recomputeState();
  });

  document.body.addEventListener("htmx:responseError", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isContentRefreshRequest(path)) {
      return;
    }
    htmxPending = Math.max(0, htmxPending - 1);
    applyState("stale", { force: true });
  });

  if (!realtimeEnabled && fallbackSeconds > 0) {
    applyState("live", { force: true });
  } else if (!realtimeEnabled) {
    applyState("offline", { force: true });
  }

  document.body.addEventListener("htmx:oobAfterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || target.id !== "sync-coord-meta") {
      return;
    }
    window.CapiForgeSync.setCoordMeta(target.dataset.coordState, target.dataset.coordLabel);
  });
})();
