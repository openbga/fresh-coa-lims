// Page documentation panel: toggle, load the current page's documentation, resize, remember.
// pagedocs-init.js applies the saved state before paint; without JavaScript the top-bar link
// opens the documentation as a full page.
(function () {
  "use strict";

  // Open state and width are the signed-in person's preferences, kept on the server
  // (core/preferences.py "pagedocs.open" and "pagedocs.width"): lab workstations are shared.
  // Earlier versions kept them in this browser under these keys; init() moves them once.
  var LEGACY_OPEN_KEY = "freshcoa-pagedocs-open";
  var LEGACY_WIDTH_KEY = "freshcoa-pagedocs-width";
  var MIN = 280;
  var LIMIT = 960;
  var DEFAULT = 400;
  var KEEP_MAIN = 360; // the page keeps at least this much room beside the panel
  var STEP = 16;
  var BIG_STEP = 64;
  var root = document.documentElement;
  var narrow = window.matchMedia("(max-width: 991.98px)"); // matches pagedocs.css
  var panel, body, splitter, fullLink, loadedPath, request;
  var formDialog, home; // the shared form dialog (static/js/form-dialog.js) and the panel's place

  function saved(key) {
    return window.vrPreferences ? window.vrPreferences.get(key) : null;
  }

  function save(key, value) {
    if (window.vrPreferences) {
      window.vrPreferences.set(key, value); // refused or offline: applies to this page only
    }
  }

  // The values an earlier version kept in this browser become the preferences of the person
  // signed in now, unless they have their own, and leave the browser.
  function migrateLegacy() {
    try {
      var open = localStorage.getItem(LEGACY_OPEN_KEY);
      var width = parseInt(localStorage.getItem(LEGACY_WIDTH_KEY), 10);
      if (open !== null && saved("pagedocs.open") === null) {
        save("pagedocs.open", open === "1");
      }
      if (!isNaN(width) && width >= MIN && width <= LIMIT && saved("pagedocs.width") === null) {
        save("pagedocs.width", width);
      }
      localStorage.removeItem(LEGACY_OPEN_KEY);
      localStorage.removeItem(LEGACY_WIDTH_KEY);
    } catch (error) {
      // Storage blocked: nothing to move.
    }
  }

  function toggles() {
    return document.querySelectorAll("[data-pagedocs-toggle]");
  }

  // While the form dialog is open the panel docks inside it: inside the dialog's focus boundary,
  // never in the inert page behind it, and it documents the form shown in the dialog.
  function docked() {
    return Boolean(formDialog && formDialog.contains(panel));
  }

  function isOpen() {
    return root.classList.contains("pagedocs-open");
  }

  function maxWidth() {
    return Math.max(MIN, Math.min(LIMIT, window.innerWidth - KEEP_MAIN));
  }

  function currentWidth() {
    var width = saved("pagedocs.width");
    return clamp(typeof width === "number" ? width : DEFAULT);
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
      save("pagedocs.width", width);
    }
  }

  function currentPath() {
    var form = docked() && formDialog.querySelector("#vr-form-content [data-vr-form-page]");
    var url = form && form.getAttribute("data-vr-form-url");
    return url ? new URL(url, window.location.href).pathname : window.location.pathname;
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
        enhance(body);
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

  // "Find a field or action": in a doc with the friendly layer the reference sections are
  // collapsed. Typing hides the blocks that don't match, opens the sections that do and marks the
  // matches. Marks are built from text nodes only; documentation text never becomes markup.
  var UNITS = ":scope > p, :scope > ul > li, :scope > ol > li, :scope > pre, :scope > .pagedocs-note, :scope > h4, :scope > h5, tbody > tr";

  function enhance(scope) {
    scope.querySelectorAll("[data-pagedocs-filter-box]").forEach(function (box) {
      box.hidden = false;
    });
  }

  function unmark(scope) {
    scope.querySelectorAll("mark.pagedocs-hit").forEach(function (hit) {
      var parent = hit.parentNode;
      parent.replaceChild(document.createTextNode(hit.textContent), hit);
      parent.normalize();
    });
  }

  function mark(element, query) {
    var walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    var nodes = [];
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }
    nodes.forEach(function (node) {
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      var index = lower.indexOf(query);
      if (index === -1) {
        return;
      }
      var parts = document.createDocumentFragment();
      var at = 0;
      while (index !== -1) {
        parts.appendChild(document.createTextNode(text.slice(at, index)));
        var hit = document.createElement("mark");
        hit.className = "pagedocs-hit";
        hit.textContent = text.slice(index, index + query.length);
        parts.appendChild(hit);
        at = index + query.length;
        index = lower.indexOf(query, at);
      }
      parts.appendChild(document.createTextNode(text.slice(at)));
      node.parentNode.replaceChild(parts, node);
    });
  }

  function filter(input) {
    var reference = input.closest("[data-pagedocs-reference]");
    if (!reference) {
      return;
    }
    var query = input.value.trim().toLowerCase();
    var any = false;
    unmark(reference);
    reference.querySelectorAll("[data-pagedocs-section]").forEach(function (section) {
      var title = section.querySelector("summary");
      var content = section.querySelector(".pagedocs-section-body");
      var whole = Boolean(query) && title.textContent.toLowerCase().indexOf(query) !== -1;
      var matches = whole ? 1 : 0;
      content.querySelectorAll(UNITS).forEach(function (unit) {
        var hit = Boolean(query) && unit.textContent.toLowerCase().indexOf(query) !== -1;
        unit.hidden = Boolean(query) && !hit && !whole;
        if (hit) {
          matches += 1;
        }
      });
      // A table whose rows are all hidden loses its header too.
      content.querySelectorAll(".table-responsive").forEach(function (table) {
        table.hidden = Boolean(query) && !table.querySelector("tbody > tr:not([hidden])");
      });
      if (query && matches) {
        mark(section, query);
      }
      section.hidden = Boolean(query) && !matches;
      section.open = Boolean(query) && matches > 0;
      any = any || matches > 0;
    });
    reference.querySelector("[data-pagedocs-none]").hidden = !query || any;
  }

  // Narrow screens: the open panel covers the page, so the covered content leaves the tab order
  // and the accessibility tree (with the skip link to it). The top bar and the phone navigation (its
  // own overlay) stay usable.
  function syncCovered() {
    if (docked()) {
      return; // the form dialog keeps the page behind it inert
    }
    var covered = isOpen() && narrow.matches;
    document.querySelectorAll(".vr-skip, .vr-shell > :not(#vr-nav)").forEach(function (element) {
      element.inert = covered;
    });
  }

  function focusTitle() {
    var title = body.querySelector("#pagedocs-title");
    (title || panel).focus({ preventScroll: true });
  }

  function open(focusAfter) {
    root.classList.add("pagedocs-open");
    save("pagedocs.open", true);
    setWidth(currentWidth(), false);
    syncCovered();
    load(focusAfter);
  }

  function close() {
    var hadFocus = panel.contains(document.activeElement);
    root.classList.remove("pagedocs-open");
    save("pagedocs.open", false);
    syncCovered();
    syncLinks();
    var toggle = (docked() ? formDialog : document).querySelector("[data-pagedocs-toggle]");
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
      save("pagedocs.width", parseInt(splitter.getAttribute("aria-valuenow"), 10));
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
    enhance(document); // the full-page fallback renders a doc outside the panel
    setWidth(currentWidth(), false);
    syncLinks();
    syncCovered();
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
    document.addEventListener("input", function (event) {
      if (event.target.matches("[data-pagedocs-filter]")) {
        filter(event.target);
      }
    });
    // Escape in a filled filter clears it first (capture: before the panel's Escape closes it).
    document.addEventListener(
      "keydown",
      function (event) {
        if (event.key === "Escape" && event.target.matches("[data-pagedocs-filter]") && event.target.value) {
          event.preventDefault();
          event.target.value = "";
          filter(event.target);
        }
      },
      true
    );
    document.addEventListener("keydown", function (event) {
      if ((event.key === " " || event.key === "Spacebar") && event.target.closest("[data-pagedocs-toggle]")) {
        onToggle(event); // role="button" links activate on Space like buttons
      }
    });
    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        event.stopPropagation(); // docked in the form dialog: Escape closes the panel, not the form
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
    narrow.addEventListener("change", syncCovered);

    formDialog = document.getElementById("vr-form-dialog");
    if (formDialog) {
      home = document.createComment("pagedocs panel");
      panel.before(home);
      // Dock before form-dialog.js marks the other branches of the page inert.
      formDialog.addEventListener("show.bs.modal", function () {
        formDialog.append(panel);
        navigated();
      });
      formDialog.addEventListener("hidden.bs.modal", function () {
        home.after(panel);
        syncCovered();
        navigated();
      });
      var content = formDialog.querySelector("#vr-form-content");
      if (content) {
        new MutationObserver(function () {
          if (docked()) {
            navigated(); // the dialog moved to another form
          }
        }).observe(content, { childList: true });
      }
    }

    // History navigation without a full load (HTMX boosting or history restore).
    window.addEventListener("popstate", navigated);
    ["htmx:pushedIntoHistory", "htmx:replacedInHistory", "htmx:historyRestore"].forEach(function (name) {
      document.body.addEventListener(name, navigated);
    });

    migrateLegacy();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
