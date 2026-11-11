// Page documentation panel: toggle, load the current page's documentation, resize, remember.
// pagedocs-init.js applies the saved state before paint; without JavaScript the top-bar link
// opens the documentation as a full page.
(function () {
  "use strict";

  var OPEN_KEY = "openbga-qualab-pagedocs-open";
  var WIDTH_KEY = "openbga-qualab-pagedocs-width";
  var MIN = 280;
  var LIMIT = 960;
  var DEFAULT = 400;
  var KEEP_MAIN = 360; // the page keeps at least this much room beside the panel
  var STEP = 16;
  var BIG_STEP = 64;
  var root = document.documentElement;
  var panel, body, splitter, fullLink, loadedPath, request;

  function store(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (error) {
      // Storage blocked: the choice applies to this page only.
    }
  }

  function read(key) {
    try {
      return localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function toggles() {
    return document.querySelectorAll("[data-pagedocs-toggle]");
  }

  function isOpen() {
    return root.classList.contains("pagedocs-open");
  }

  function maxWidth() {
    return Math.max(MIN, Math.min(LIMIT, window.innerWidth - KEEP_MAIN));
  }

  function currentWidth() {
    var saved = parseInt(read(WIDTH_KEY), 10);
    return clamp(isNaN(saved) ? DEFAULT : saved);
  }

  function clamp(width) {
    return Math.round(Math.min(maxWidth(), Math.max(MIN, width)));
  }

  function setWidth(width, persist) {
    width = clamp(width);
    root.style.setProperty("--pagedocs-width", width + "px");
    splitter.setAttribute("aria-valuemin", String(MIN));
    splitter.setAttribute("aria-valuemax", String(maxWidth()));
    splitter.setAttribute("aria-valuenow", String(width));
    splitter.setAttribute("aria-valuetext", width + " pixels wide");
    if (persist) {
      store(WIDTH_KEY, String(width));
    }
  }

  function currentPath() {
    return window.location.pathname;
  }

  function syncLinks() {
    var href = panel.getAttribute("data-pagedocs-endpoint") + "?path=" + encodeURIComponent(currentPath());
    fullLink.setAttribute("href", href);
    toggles().forEach(function (toggle) {
      toggle.setAttribute("href", href);
      toggle.setAttribute("aria-expanded", isOpen() ? "true" : "false");
    });
  }

  function load(focusAfter) {
    var path = currentPath();
    syncLinks();
    if (path === loadedPath) {
      if (focusAfter) {
        focusTitle();
      }
      return;
    }
    loadedPath = path;
    if (request) {
      request.abort();
    }
    request = new AbortController();
    body.setAttribute("aria-busy", "true");
    fetch(panel.getAttribute("data-pagedocs-endpoint") + "?path=" + encodeURIComponent(path), {
      headers: { "X-Pagedocs": "fragment" },
      credentials: "same-origin",
      signal: request.signal,
    })
      .then(function (response) {
        if (response.status !== 200 && response.status !== 404 && response.status !== 403) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        body.innerHTML = html; // server-rendered, sanitized fragment from the same origin
        body.scrollTop = 0;
        if (focusAfter) {
          focusTitle();
        }
      })
      .catch(function (error) {
        if (error.name === "AbortError") {
          return;
        }
        loadedPath = null;
        body.innerHTML = "";
        var message = document.createElement("p");
        message.className = "pagedocs-error";
        message.setAttribute("role", "alert");
        message.textContent = "Documentation could not be loaded. Use the full-page link or try again.";
        body.appendChild(message);
      })
      .finally(function () {
        body.removeAttribute("aria-busy");
      });
  }

  function focusTitle() {
    var title = body.querySelector("#pagedocs-title");
    (title || panel).focus({ preventScroll: true });
  }

  function open(focusAfter) {
    root.classList.add("pagedocs-open");
    store(OPEN_KEY, "1");
    setWidth(currentWidth(), false);
    load(focusAfter);
  }

  function close() {
    var hadFocus = panel.contains(document.activeElement);
    root.classList.remove("pagedocs-open");
    store(OPEN_KEY, "0");
    syncLinks();
    var toggle = toggles()[0];
    if (hadFocus && toggle) {
      toggle.focus();
    }
  }

  function onToggle(event) {
    var toggle = event.target.closest("[data-pagedocs-toggle]");
    if (!toggle) {
      return false;
    }
    event.preventDefault();
    if (isOpen()) {
      close();
    } else {
      open(true);
    }
    return true;
  }

  function startDrag(event) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    splitter.setPointerCapture(event.pointerId);
    root.classList.add("pagedocs-resizing");
    function move(moveEvent) {
      setWidth(window.innerWidth - moveEvent.clientX, false);
    }
    function end() {
      splitter.removeEventListener("pointermove", move);
      splitter.removeEventListener("pointerup", end);
      splitter.removeEventListener("pointercancel", end);
      root.classList.remove("pagedocs-resizing");
      store(WIDTH_KEY, splitter.getAttribute("aria-valuenow"));
    }
    splitter.addEventListener("pointermove", move);
    splitter.addEventListener("pointerup", end);
    splitter.addEventListener("pointercancel", end);
  }

  function keyResize(event) {
    var width = parseInt(splitter.getAttribute("aria-valuenow"), 10) || currentWidth();
    var step = event.shiftKey ? BIG_STEP : STEP;
    // The splitter is the panel's left edge: moving it left widens the panel.
    var next = {
      ArrowLeft: width + step,
      ArrowRight: width - step,
      Home: MIN,
      End: maxWidth(),
    }[event.key];
    if (next === undefined) {
      return;
    }
    event.preventDefault();
    setWidth(next, true);
  }

  function navigated() {
    if (isOpen()) {
      load(false);
    } else {
      syncLinks();
    }
  }

  function init() {
    panel = document.querySelector("[data-pagedocs-panel]");
    if (!panel) {
      return;
    }
    body = panel.querySelector("[data-pagedocs-body]");
    splitter = panel.querySelector("[data-pagedocs-splitter]");
    fullLink = panel.querySelector("[data-pagedocs-full]");
    setWidth(currentWidth(), false);
    syncLinks();
    if (isOpen()) {
      load(false); // restored open: show this page's documentation without moving focus
    }

    document.addEventListener("click", function (event) {
      if (onToggle(event)) {
        return;
      }
      if (event.target.closest("[data-pagedocs-close]")) {
        close();
      }
    });
    document.addEventListener("keydown", function (event) {
      if ((event.key === " " || event.key === "Spacebar") && event.target.closest("[data-pagedocs-toggle]")) {
        onToggle(event); // role="button" links activate on Space like buttons
      }
    });
    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        close();
      }
    });
    splitter.addEventListener("pointerdown", startDrag);
    splitter.addEventListener("keydown", keyResize);
    splitter.addEventListener("dblclick", function () {
      setWidth(DEFAULT, true);
    });
    window.addEventListener("resize", function () {
      setWidth(currentWidth(), false);
    });

    // History navigation without a full load (HTMX boosting or history restore).
    window.addEventListener("popstate", navigated);
    ["htmx:pushedIntoHistory", "htmx:replacedInHistory", "htmx:historyRestore"].forEach(function (name) {
      document.body.addEventListener(name, navigated);
    });

    // Another tab opened, closed or resized the panel.
    window.addEventListener("storage", function (event) {
      if (event.key === OPEN_KEY) {
        if (event.newValue === "1" && !isOpen()) {
          root.classList.add("pagedocs-open");
          navigated();
        } else if (event.newValue !== "1" && isOpen()) {
          root.classList.remove("pagedocs-open");
          syncLinks();
        }
      } else if (event.key === WIDTH_KEY) {
        setWidth(currentWidth(), false);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
