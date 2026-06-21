(function () {
  var sync = document.getElementById("app-sync-status");
  if (!sync) {
    return;
  }

  var dot = sync.querySelector(".sync-dot");
  var label = sync.querySelector(".sync-label");
  var baseState = sync.dataset.baseState || "ok";
  var baseLabel = sync.dataset.baseLabel || "Sync OK";
  var pending = 0;

  function isRefreshRequest(path) {
    if (!path) {
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

  function setRefreshing(active) {
    if (!dot || !label) {
      return;
    }
    if (active) {
      dot.className = "sync-dot sync-dot--refreshing";
      label.textContent = "Refresh";
      sync.classList.add("is-refreshing");
      return;
    }
    sync.classList.remove("is-refreshing");
    dot.className = "sync-dot sync-dot--" + baseState;
    label.textContent = baseLabel;
  }

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isRefreshRequest(path)) {
      return;
    }
    pending += 1;
    setRefreshing(true);
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isRefreshRequest(path)) {
      return;
    }
    pending = Math.max(0, pending - 1);
    if (pending === 0) {
      setRefreshing(false);
    }
  });

  document.body.addEventListener("htmx:responseError", function (event) {
    var path = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (!isRefreshRequest(path)) {
      return;
    }
    pending = Math.max(0, pending - 1);
    if (pending === 0) {
      setRefreshing(false);
    }
  });
})();
