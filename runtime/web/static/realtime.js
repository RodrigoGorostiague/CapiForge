(function () {
  var configEl = document.getElementById("realtime-config");
  if (!configEl || typeof EventSource === "undefined") {
    return;
  }

  var syncApi = window.CapiForgeSync;
  if (!syncApi) {
    return;
  }

  var config;
  try {
    config = JSON.parse(configEl.textContent || "{}");
  } catch (e) {
    return;
  }

  var route = config.route || "home";
  var projectId = config.project_id || "";
  var panelUrl = config.panel_url || "";
  var debounceTimer = null;
  var source = null;
  var reconnectTimer = null;

  function pageRefreshUrl() {
    return window.location.pathname + window.location.search;
  }

  function tasksPanelUrl() {
    if (route !== "tasks") {
      return "";
    }
    var search = window.location.search;
    if (search) {
      return "/api/partials/tasks-panel" + search;
    }
    return panelUrl;
  }

  function refreshActiveView() {
    if (!window.htmx) {
      return;
    }
    syncApi.markUpdating();
    var currentPanelUrl = tasksPanelUrl();
    if (route === "tasks" && currentPanelUrl) {
      window.htmx.ajax("GET", currentPanelUrl, {
        target: "#tasks-panel",
        swap: "innerHTML scroll:innerHTML",
      });
    } else {
      window.htmx.ajax("GET", pageRefreshUrl(), {
        target: "#page-content",
        select: "#page-content",
        swap: "innerHTML scroll:innerHTML",
      });
    }
  }

  function scheduleRefresh() {
    syncApi.markPending();
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(function () {
      debounceTimer = null;
      refreshActiveView();
    }, 200);
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) {
      return;
    }
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      connect();
    }, 3000);
  }

  function connect() {
    if (source) {
      source.close();
      source = null;
    }
    syncApi.markConnecting();
    var params = new URLSearchParams({ route: route });
    if (projectId) {
      params.set("project_id", projectId);
    }
    source = new EventSource("/api/events/stream?" + params.toString());
    source.addEventListener("open", function () {
      syncApi.markLive();
    });
    source.addEventListener("data_changed", scheduleRefresh);
    source.addEventListener("heartbeat", function () {
      if (debounceTimer === null) {
        syncApi.markLive();
      }
    });
    source.onerror = function () {
      if (source) {
        source.close();
        source = null;
      }
      syncApi.markStale();
      scheduleReconnect();
    };
  }

  connect();
})();
