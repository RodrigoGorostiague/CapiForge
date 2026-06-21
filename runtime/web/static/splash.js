(function () {
  var SESSION_KEY = "capiforge.splash.seen";
  var splash = document.getElementById("app-splash");
  if (!splash) {
    return;
  }

  function removeSplash() {
    splash.remove();
  }

  try {
    if (sessionStorage.getItem(SESSION_KEY)) {
      removeSplash();
      return;
    }
  } catch (error) {
    removeSplash();
    return;
  }

  var MIN_MS = 1500;
  var MAX_MS = 4000;
  var start = performance.now();
  var done = false;

  function hide() {
    if (done) {
      return;
    }
    done = true;
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch (error) {
      /* ignore */
    }
    var elapsed = performance.now() - start;
    var wait = Math.max(0, MIN_MS - elapsed);
    window.setTimeout(function () {
      splash.classList.add("is-hidden");
      window.setTimeout(removeSplash, 350);
    }, wait);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hide, { once: true });
  } else {
    hide();
  }
  window.setTimeout(hide, MAX_MS);
})();
