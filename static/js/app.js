// Small progressive enhancements. Pages must work without this file.
(function () {
  "use strict";

  // Shared markup for the other scripts (grid.js, form-dialog.js, controls.js, sidebar.js), so
  // they build the same icon as {% icon %} (templates/includes/icon.html) and the standard
  // button roles. Every script builds icons only through window.vrUi.icon.
  var BUTTON_ROLES = {
    primary: "btn btn-primary",
    secondary: "btn btn-outline-secondary",
    quiet: "btn btn-link",
    destructive: "btn btn-outline-danger",
  };

  window.vrUi = {
    // Decorative sprite icon as markup (for innerHTML and Tom Select render strings).
    icon: function (name) {
      var sprite = document.body.getAttribute("data-vr-icons") || "";
      return '<svg class="vr-icon" aria-hidden="true" focusable="false"><use href="' + sprite + "#i-" + name + '"></use></svg>';
    },
    // <button type="button"> in a standard role; small for table cells, panel headers and dialogs.
    button: function (label, role, small) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = (BUTTON_ROLES[role] || BUTTON_ROLES.secondary) + (small ? " btn-sm" : "");
      button.textContent = label;
      return button;
    },
  };

  // Colour theme: "light" | "dark" | "system" in localStorage "vr-theme" (see theme-init.js).
  var THEME_KEY = "vr-theme";
  var systemDark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function savedTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || "system";
    } catch (error) {
      return "system";
    }
  }

  function applyTheme(choice) {
    var dark = choice === "dark" || (choice === "system" && systemDark && systemDark.matches);
    document.documentElement.setAttribute("data-bs-theme", dark ? "dark" : "light");
    document.documentElement.setAttribute("data-vr-theme-choice", choice);
    var label = choice.charAt(0).toUpperCase() + choice.slice(1);
    document.querySelectorAll("[data-vr-theme-value]").forEach(function (option) {
      option.setAttribute("aria-pressed", option.getAttribute("data-vr-theme-value") === choice ? "true" : "false");
    });
    document.querySelectorAll("[data-vr-theme-button]").forEach(function (button) {
      button.setAttribute("title", "Theme: " + label);
    });
  }

  document.addEventListener("click", function (event) {
    var option = event.target.closest("[data-vr-theme-value]");
    if (!option) {
      return;
    }
    var choice = option.getAttribute("data-vr-theme-value");
    try {
      localStorage.setItem(THEME_KEY, choice);
    } catch (error) {
      // Storage blocked: the choice applies to this page only.
    }
    applyTheme(choice);
  });

  if (systemDark) {
    systemDark.addEventListener("change", function () {
      if (savedTheme() === "system") {
        applyTheme("system");
      }
    });
  }

  // Another tab changed the theme.
  window.addEventListener("storage", function (event) {
    if (event.key === THEME_KEY) {
      applyTheme(savedTheme());
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(savedTheme());

    // Reveal the current section on narrow layouts without moving the document or focus.
    // Observe its available width as the documentation panel opens or is resized, too.
    document.querySelectorAll(".vr-section-tabs .nav-tabs").forEach(function (row) {
      var current = row.querySelector('[aria-current="page"]');
      if (!current) {
        return;
      }
      function revealLink(link) {
        var bounds = row.getBoundingClientRect();
        var active = link.getBoundingClientRect();
        if (active.left < bounds.left || active.right > bounds.right) {
          row.scrollLeft += active.left - bounds.left - (row.clientWidth - active.width) / 2;
        }
      }
      function revealCurrent() {
        var focused = row.querySelector("a:focus");
        revealLink(focused || current);
      }
      row.addEventListener("focusin", function (event) {
        if (event.target.matches("a")) {
          revealLink(event.target);
        }
      });
      revealCurrent();
      if (window.ResizeObserver) {
        new ResizeObserver(revealCurrent).observe(row);
      }
    });
  });

  // Page-bounded select-all: <input data-vr-select-all="name"> checks the enabled row checkboxes
  // named "name" in the same table; <span data-vr-select-count="name"> reads "3 of 18 selected".
  function selectionScope(control) {
    return control.form || control.closest("form, .vr-table-card") || document;
  }

  function rowBoxes(name, scope) {
    if (scope && scope.tagName === "FORM") {
      return Array.from(scope.elements).filter(function (control) {
        return control.type === "checkbox" && control.name === name;
      });
    }
    return Array.prototype.slice.call((scope || document).querySelectorAll('input[type="checkbox"][name="' + name + '"]'));
  }

  function syncSelection(name) {
    document.querySelectorAll('[data-vr-select-all="' + name + '"]').forEach(function (master) {
      var eligible = rowBoxes(name, master.closest("table")).filter(function (box) { return !box.disabled; });
      var checked = eligible.filter(function (box) { return box.checked; }).length;
      master.checked = eligible.length > 0 && checked === eligible.length;
      master.indeterminate = checked > 0 && checked < eligible.length;
      master.disabled = eligible.length === 0;
      selectionScope(master).querySelectorAll('[data-vr-select-count="' + name + '"]').forEach(function (counter) {
        counter.textContent = checked + " of " + eligible.length + " selected";
      });
    });
    // Optional "select only ready" shortcut (includes/select_all.html with ready_label).
    document.querySelectorAll('[data-vr-select-ready="' + name + '"]').forEach(function (button) {
      var ready = rowBoxes(name, selectionScope(button)).filter(function (box) { return !box.disabled && box.hasAttribute("data-ready"); });
      button.disabled = ready.length === 0;
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-vr-select-ready]");
    if (!button) {
      return;
    }
    var name = button.getAttribute("data-vr-select-ready");
    var changedForms = new Set();
    rowBoxes(name, selectionScope(button)).forEach(function (box) {
      if (!box.disabled) {
        var checked = box.hasAttribute("data-ready");
        if (box.checked !== checked && box.form) {
          changedForms.add(box.form);
        }
        box.checked = checked;
      }
    });
    syncSelection(name);
    changedForms.forEach(function (form) {
      form.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  document.addEventListener("change", function (event) {
    var master = event.target.closest("[data-vr-select-all]");
    if (master) {
      var name = master.getAttribute("data-vr-select-all");
      rowBoxes(name, master.closest("table")).forEach(function (box) {
        if (!box.disabled) {
          box.checked = master.checked;
        }
      });
      syncSelection(name);
      return;
    }
    if (event.target.matches('input[type="checkbox"][name]')) {
      if (document.querySelector('[data-vr-select-all="' + event.target.name + '"]')) {
        syncSelection(event.target.name);
      }
    }
    // Rows-per-page and similar single selects submit their GET form on change.
    if (event.target.matches("select[data-vr-autosubmit]") && event.target.form) {
      event.target.form.requestSubmit();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-vr-select-all]").forEach(function (master) {
      syncSelection(master.getAttribute("data-vr-select-all"));
    });
    document.querySelectorAll("[data-vr-autosubmit-fallback]").forEach(function (button) {
      button.hidden = true;
    });
  });

  // Long checkbox/radio lists (more than ten options) get a filter box. Presentation only: hidden
  // options keep their checked state and are still submitted.
  function addChoiceFilter(list) {
    var options = Array.prototype.slice.call(list.querySelectorAll(".form-check"));
    if (options.length <= 10 || list.previousElementSibling && list.previousElementSibling.matches(".vr-choice-filter")) {
      return;
    }
    var legend = list.closest("fieldset") && list.closest("fieldset").querySelector("legend");
    var name = legend ? legend.textContent.replace(/\*/g, "").trim().toLowerCase() : "options";
    var wrap = document.createElement("div");
    wrap.className = "vr-choice-filter";
    var input = document.createElement("input");
    input.type = "search";
    input.className = "form-control form-control-sm";
    input.placeholder = "Filter " + name;
    input.setAttribute("aria-label", "Filter " + name);
    input.autocomplete = "off";
    var status = document.createElement("span");
    status.className = "form-text";
    status.setAttribute("role", "status");
    wrap.append(input, status);
    list.parentNode.insertBefore(wrap, list);
    input.addEventListener("input", function () {
      var terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      var shown = 0;
      options.forEach(function (option) {
        var text = option.textContent.toLowerCase();
        var match = terms.every(function (term) { return text.indexOf(term) !== -1; });
        option.hidden = !match;
        shown += match ? 1 : 0;
      });
      status.textContent = terms.length ? shown + " of " + options.length + " shown; selections are kept." : "";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".vr-choices").forEach(addChoiceFilter);
  });

  // Column priority on tables without a Columns control (record sub-tables): the cells of a column
  // whose header carries data-vr-col-priority="low" are marked, and app.css hides them below 1366px,
  // so the table fits; the full data stays on the record. Lists (data-vr-grid) use grid.js instead.
  function markLowPriorityColumns(scope) {
    (scope || document).querySelectorAll(".vr-table:not([data-vr-grid])").forEach(function (table) {
      var head = table.tHead && table.tHead.rows[table.tHead.rows.length - 1];
      if (!head || table.dataset.vrPriorityReady === "true") {
        return;
      }
      var low = [];
      var position = 0;
      Array.from(head.cells).forEach(function (cell) {
        if (cell.getAttribute("data-vr-col-priority") === "low") {
          low.push(position);
          cell.setAttribute("data-vr-low", "");
        }
        position += cell.colSpan || 1;
      });
      if (!low.length) {
        return;
      }
      table.dataset.vrPriorityReady = "true";
      Array.from(table.tBodies).concat(table.tFoot ? [table.tFoot] : []).forEach(function (section) {
        Array.from(section.rows).forEach(function (row) {
          var column = 0;
          Array.from(row.cells).forEach(function (cell) {
            if ((cell.colSpan || 1) === 1 && low.indexOf(column) !== -1) {
              cell.setAttribute("data-vr-low", "");
            }
            column += cell.colSpan || 1;
          });
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () { markLowPriorityColumns(document); });
  document.addEventListener("htmx:load", function (event) { markLowPriorityColumns(event.detail.elt); });

  // Dashboard band: each stage's segment grows with its open work (CSSOM, so the content security
  // policy's style-src 'self' holds; the markup carries the count as text).
  function sizeFlowBand(scope) {
    (scope || document).querySelectorAll(".vr-flow-segment").forEach(function (segment) {
      var count = parseInt((segment.querySelector(".vr-flow-count") || {}).textContent, 10);
      segment.style.flexGrow = String(Math.max(isNaN(count) ? 1 : count, 1));
    });
  }

  document.addEventListener("DOMContentLoaded", function () { sizeFlowBand(document); });

  // After a failed submission, put keyboard focus on the first field with an error.
  document.addEventListener("DOMContentLoaded", function () {
    var invalid = document.querySelector("form [aria-invalid=true]");
    if (invalid && invalid.tagName === "FIELDSET") {
      invalid = invalid.querySelector("input, select, textarea");
    }
    if (invalid) {
      invalid.focus();
    }
  });

  // File size limit: <input type="file" data-vr-max-bytes="1048576" data-vr-max-label="1.0 MiB">
  // refuses larger files when they are chosen and again on submit, so they are never sent.
  // The server enforces the same limit; this saves the upload. Registered before the
  // double-submission guard below, which skips a submission that was prevented.
  function withinFileLimit(input) {
    var limit = parseInt(input.getAttribute("data-vr-max-bytes"), 10);
    var total = Array.from(input.files || []).reduce(function (sum, file) { return sum + file.size; }, 0);
    var errorId = input.id + "_limit_error";
    var shown = document.getElementById(errorId);
    var described = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (id) {
      return id && id !== errorId;
    });
    var within = isNaN(limit) || total <= limit;
    if (within && shown) {
      shown.remove();
      if (input.hasAttribute("data-vr-limit-invalid")) {
        input.removeAttribute("data-vr-limit-invalid");
        input.removeAttribute("aria-invalid");
      }
    }
    if (!within && !shown) {
      var list = document.createElement("ul");
      list.className = "vr-field-errors";
      list.id = errorId;
      list.setAttribute("role", "alert");
      var item = document.createElement("li");
      item.textContent = "The file is larger than the limit of " + input.getAttribute("data-vr-max-label") +
        " and was not sent. Choose a smaller file.";
      list.append(item);
      (input.closest(".vr-field") || input.parentNode).append(list);
      if (input.getAttribute("aria-invalid") !== "true") {
        input.setAttribute("data-vr-limit-invalid", "");
        input.setAttribute("aria-invalid", "true");
      }
    }
    if (!within) {
      described.push(errorId);
    }
    if (described.length) {
      input.setAttribute("aria-describedby", described.join(" "));
    } else {
      input.removeAttribute("aria-describedby");
    }
    return within;
  }
  document.addEventListener("change", function (event) {
    if (event.target.matches("input[type=file][data-vr-max-bytes]")) {
      withinFileLimit(event.target);
    }
  });
  document.addEventListener("submit", function (event) {
    var blocked = Array.from(event.target.querySelectorAll("input[type=file][data-vr-max-bytes]")).filter(function (input) {
      return !withinFileLimit(input);
    });
    if (blocked.length) {
      event.preventDefault();
      blocked[0].focus();
    }
  });

  // Native POST forms: block double submission while the request is in flight.
  // Buttons are disabled after the submit event so their name/value is still sent.
  function releaseForm(form) {
    delete form.dataset.vrSubmitting;
    form.removeAttribute("aria-busy");
    form.querySelectorAll(".vr-busy-mark").forEach(function (mark) { mark.remove(); });
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (button) {
      button.disabled = false;
    });
  }

  // A form answered by a file download (data-vr-download) stays on its page: it is released
  // once the download has had time to start, and the browser shows the download's progress.
  var DOWNLOAD_RELEASE_MS = 4000;

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var method = (form.getAttribute("method") || "get").toLowerCase();
    if (event.defaultPrevented || method !== "post" || form.hasAttribute("hx-post")) {
      return;
    }
    if (form.dataset.vrSubmitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.vrSubmitting = "true";
    form.setAttribute("aria-busy", "true");
    var submitter = event.submitter;
    window.setTimeout(function () {
      form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (button) {
        button.disabled = true;
      });
      // Release, import and export actions render or parse on the server and can take seconds:
      // show that the request is running, and announce it, instead of only greying the button.
      if (submitter && submitter.tagName === "BUTTON") {
        var spinner = document.createElement("span");
        spinner.className = "spinner-border spinner-border-sm me-2 vr-busy-mark";
        spinner.setAttribute("aria-hidden", "true");
        submitter.prepend(spinner);
        var status = document.createElement("span");
        status.className = "visually-hidden vr-busy-mark";
        status.setAttribute("role", "status");
        status.textContent = "Working. Please wait.";
        form.append(status);
      }
    }, 0);
    if (form.hasAttribute("data-vr-download")) {
      window.setTimeout(function () { releaseForm(form); }, DOWNLOAD_RELEASE_MS);
    }
  });

  // Back/forward cache restores the disabled state; re-enable on return.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) {
      return;
    }
    document.querySelectorAll("form[data-vr-submitting]").forEach(releaseForm);
  });

  // Django formsets: a button[data-formset-add="<prefix>"] appends a copy of
  // <template id="<prefix>-empty"> (the formset's empty_form) to #<prefix>-rows and keeps
  // TOTAL_FORMS accurate. "__num__" in the template becomes the 1-based row number.
  function initFormsetButton(button) {
    if (button.dataset.vrFormsetReady === "true") {
      return;
    }
    var prefix = button.dataset.formsetAdd;
    var total = document.querySelector("input[name='" + prefix + "-TOTAL_FORMS']");
    var max = document.querySelector("input[name='" + prefix + "-MAX_NUM_FORMS']");
    var template = document.getElementById(prefix + "-empty");
    var rows = document.getElementById(prefix + "-rows");
    if (!total || !template || !rows) {
      return;
    }
    button.dataset.vrFormsetReady = "true";
    function atLimit() {
      return max && parseInt(total.value, 10) >= parseInt(max.value, 10);
    }
    button.hidden = false;
    button.disabled = atLimit();
    button.addEventListener("click", function () {
      if (atLimit()) {
        return;
      }
      var index = parseInt(total.value, 10);
      var html = template.innerHTML.replace(/__prefix__/g, String(index)).replace(/__num__/g, String(index + 1));
      rows.insertAdjacentHTML("beforeend", html);
      if (window.htmx) {
        window.htmx.process(rows.lastElementChild);
        window.htmx.trigger(rows.lastElementChild, "htmx:load");
      }
      var form = button.form || button.closest("form");
      if (form) {
        form.dispatchEvent(new Event("change", { bubbles: true }));
      }
      total.value = String(index + 1);
      button.disabled = atLimit();
      var added = rows.lastElementChild;
      var first = added && added.querySelector("input:not([type=hidden]), select, textarea");
      if (first) {
        first.focus();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-formset-add]").forEach(initFormsetButton);
  });

  document.addEventListener("htmx:load", function () {
    document.querySelectorAll("[data-vr-select-all]").forEach(function (master) {
      syncSelection(master.getAttribute("data-vr-select-all"));
    });
    document.querySelectorAll("[data-vr-autosubmit-fallback]").forEach(function (button) {
      button.hidden = true;
    });
    document.querySelectorAll(".vr-choices").forEach(addChoiceFilter);
    document.querySelectorAll("[data-formset-add]").forEach(initFormsetButton);
  });

  // HTMX transport and server errors: keep the page as it is and say what happened, in a notice
  // where Django messages appear (no toasts). The notice markup is server-rendered once in
  // <template id="vr-request-error"> (layouts/document.html).
  function showRequestError(message) {
    var template = document.getElementById("vr-request-error");
    var main = document.querySelector(".vr-main");
    if (!template || !main) {
      return;
    }
    main.querySelectorAll("[data-vr-request-error]").forEach(function (old) { old.remove(); });
    var notice = template.content.firstElementChild.cloneNode(true);
    notice.querySelector("[data-vr-notice-text]").textContent = message;
    notice.setAttribute("tabindex", "-1");
    var region = main.querySelector(":scope > .vr-messages");
    if (!region) {
      region = document.createElement("div");
      region.className = "vr-messages";
      var header = main.querySelector(":scope > .vr-page-header");
      main.insertBefore(region, header ? header.nextSibling : main.firstChild);
    }
    region.prepend(notice);
    notice.focus();
  }

  function inFormDialog(event) {
    // The form dialog keeps its error beside the preserved inputs (form-dialog.js).
    return Boolean(event.detail.target && event.detail.target.closest("#vr-form-dialog"));
  }

  document.addEventListener("htmx:responseError", function (event) {
    if (inFormDialog(event)) {
      return;
    }
    var status = event.detail.xhr ? event.detail.xhr.status : "";
    var message = status === 403
      ? "You do not have permission for that action. Nothing was changed."
      : "The server could not complete the request (" + status + "). Your input was kept; try again.";
    showRequestError(message);
  });

  document.addEventListener("htmx:sendError", function (event) {
    if (inFormDialog(event)) {
      return;
    }
    showRequestError("The server could not be reached. Check the connection and try again.");
  });
})();
