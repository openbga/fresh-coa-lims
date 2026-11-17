// Column presentation for server-rendered lists (DataTables 3 + ColReorder 3, presentation only).
//
// Django renders rows, sort links, filters, counts and pagination. This file only lets a user hide,
// show and reorder columns of <table data-vr-grid="app.list" data-vr-grid-version="1"> whose header
// cells carry data-vr-col="id" (plus data-vr-col-locked / data-vr-col-hidden). The layout is saved
// per user on the server as column IDs, preference "grid:<grid>:v<version>" (static/js/
// preferences.js, core/preferences.py); no row, filter or sort data. Page size and sort are kept
// by the server itself (core.preferences.GridPreferenceMiddleware).
// The shared Columns dialog (#vr-columns-dialog) lives in base.html.
//
// Column priority: a header with data-vr-col-priority="low" is hidden by default whenever the
// table would not fit its own panel with it: a laptop window, the help drawer open, the sidebar
// expanded. The table's width decides, not the window's. It is a default only: the user can show
// the column in Columns, and a saved layout always wins. Until a layout is saved, the defaults
// follow the panel's width as it changes.
(function () {
  "use strict";

  var grids = {};
  var dialogGrid = null;
  var dialogOpener = null;

  function storageKey(table) {
    return "grid:" + table.getAttribute("data-vr-grid") + ":v" + (table.getAttribute("data-vr-grid-version") || "1");
  }

  function readLayout(key) {
    var value = window.vrPreferences ? window.vrPreferences.get(key) : null;
    if (value && Array.isArray(value.order) && Array.isArray(value.hidden)) {
      return value;
    }
    return null; // Nothing saved, or no longer valid: the declared defaults apply.
  }

  function writeLayout(key, layout) {
    if (window.vrPreferences) {
      window.vrPreferences.set(key, layout || null);
    }
  }

  function enhance(table) {
    if (table.closest("[data-vr-form-page]") || table.dataset.vrGridReady === "true") {
      return; // Form grids keep fixed columns and never open another dialog.
    }
    var headerRow = table.tHead && table.tHead.rows[0];
    var body = table.tBodies[0];
    if (!headerRow || !body || !body.rows.length) {
      return; // Empty page: nothing to present.
    }
    for (var r = 0; r < body.rows.length; r++) {
      if (body.rows[r].cells.length !== headerRow.cells.length) {
        return; // Placeholder or colspan rows: leave the table as Django rendered it.
      }
    }
    var columns = [];
    for (var c = 0; c < headerRow.cells.length; c++) {
      var th = headerRow.cells[c];
      var id = th.getAttribute("data-vr-col");
      if (!id) {
        return; // Every header needs a stable ID; without them the layout cannot be saved.
      }
      if (th.hasAttribute("data-vr-col-locked")) {
        th.classList.add("vr-col-locked");
      }
      columns.push({
        id: id,
        index: c,
        label: (th.getAttribute("data-vr-col-label") || th.textContent).replace(/\s+/g, " ").trim() || id,
        locked: th.hasAttribute("data-vr-col-locked"),
        hiddenByDefault: th.hasAttribute("data-vr-col-hidden"),
        lowPriority: th.getAttribute("data-vr-col-priority") === "low",
        mediumPriority: th.getAttribute("data-vr-col-priority") === "medium",
      });
    }
    // Locked columns keep their place: leading ones before every movable column, the rest trailing.
    var firstMovable = columns.findIndex(function (col) { return !col.locked; });
    columns.forEach(function (col) {
      col.leading = col.locked && (firstMovable === -1 || col.index < firstMovable);
    });

    table.dataset.vrGridReady = "true";
    var dt = new window.DataTable(table, {
      ordering: false,
      searching: false,
      paging: false,
      info: false,
      stateSave: false,
      autoWidth: false,
      layout: { topStart: null, topEnd: null, bottomStart: null, bottomEnd: null },
      columns: columns.map(function (col) { return { name: col.id }; }),
      colReorder: { columns: ":not(.vr-col-locked)" },
    });

    var grid = { table: table, dt: dt, columns: columns, key: storageKey(table), cramped: 0 };
    grids[table.getAttribute("data-vr-grid")] = grid;
    applyLayout(grid, readLayout(grid.key));
    watchWidth(grid);

    dt.on("columns-reordered", function () { save(grid); });
    document.querySelectorAll('[data-vr-columns-for="' + table.getAttribute("data-vr-grid") + '"]').forEach(function (button) {
      button.hidden = Boolean(button.closest("[data-vr-form-page]"));
    });
  }

  function byId(grid, id) {
    return grid.columns.find(function (col) { return col.id === id; });
  }

  // Current display order as column IDs.
  function currentOrder(grid) {
    return grid.dt.colReorder.order().map(function (original) { return grid.columns[original].id; });
  }

  function isVisible(grid, id) {
    return grid.dt.column(id + ":name").visible();
  }

  // Build a full order of original indexes: leading locked, saved movable order (unknown IDs ignored,
  // new columns appended in declared order), trailing locked.
  function resolveOrder(grid, savedOrder) {
    var movable = grid.columns.filter(function (col) { return !col.locked; });
    var ordered = [];
    (savedOrder || []).forEach(function (id) {
      var col = byId(grid, id);
      if (col && !col.locked && ordered.indexOf(col) === -1) {
        ordered.push(col);
      }
    });
    movable.forEach(function (col) {
      if (ordered.indexOf(col) === -1) {
        ordered.push(col);
      }
    });
    var leading = grid.columns.filter(function (col) { return col.leading; });
    var trailing = grid.columns.filter(function (col) { return col.locked && !col.leading; });
    return leading.concat(ordered, trailing).map(function (col) { return col.index; });
  }

  function applyLayout(grid, layout) {
    grid.dt.colReorder.order(resolveOrder(grid, layout && layout.order), true);
    grid.columns.forEach(function (col) {
      var hidden = layout ? layout.hidden.indexOf(col.id) !== -1 : hiddenByDefault(col, grid.cramped);
      grid.dt.column(col.id + ":name").visible(col.locked ? true : !hidden, false);
    });
    grid.dt.columns.adjust();
  }

  // cramped: 0 the table fits, 1 low-priority columns give way, 2 medium-priority ones too.
  function hiddenByDefault(col, cramped) {
    return col.hiddenByDefault || (col.lowPriority && cramped >= 1) || (col.mediumPriority && cramped >= 2);
  }

  // The scrolling box the table sits in: its width is the room the table has.
  function frameOf(grid) {
    return grid.table.closest(".vr-table-wrap") || grid.table.parentElement;
  }

  // Without a saved layout, low-priority columns show only while the table fits its frame with
  // them, and medium-priority ones only while it fits without the low ones. Measured from all
  // shown, so the answer never depends on the previous one.
  function fit(grid) {
    if (readLayout(grid.key) || !grid.columns.some(function (col) {
      return (col.lowPriority || col.mediumPriority) && !col.hiddenByDefault;
    })) {
      return;
    }
    var frame = frameOf(grid);
    for (grid.cramped = 0; grid.cramped <= 2; grid.cramped += 1) {
      applyLayout(grid, null);
      if (grid.table.scrollWidth <= frame.clientWidth + 1) {
        return;
      }
    }
    grid.cramped = 2; // still too wide: the panel scrolls sideways rather than hide more
  }

  // Refit when the frame's width changes (window, help drawer, sidebar), not when its height does.
  function watchWidth(grid) {
    fit(grid);
    if (!window.ResizeObserver) {
      return;
    }
    var width = frameOf(grid).clientWidth;
    new ResizeObserver(function () {
      var now = frameOf(grid).clientWidth;
      if (now !== width) {
        width = now;
        fit(grid);
      }
    }).observe(frameOf(grid));
  }

  function save(grid) {
    var hidden = grid.columns.filter(function (col) { return !isVisible(grid, col.id); }).map(function (col) { return col.id; });
    writeLayout(grid.key, { order: currentOrder(grid), hidden: hidden });
  }

  // ---------------------------------------------------------------- Columns dialog

  function dialogParts() {
    var dialog = document.getElementById("vr-columns-dialog");
    return dialog && {
      dialog: dialog,
      list: dialog.querySelector("[data-vr-columns-list]"),
      status: dialog.querySelector("[data-vr-columns-status]"),
      title: dialog.querySelector(".modal-title"),
    };
  }

  function renderDialog(grid, focus) {
    var parts = dialogParts();
    var order = currentOrder(grid);
    var movable = order.filter(function (id) { return !byId(grid, id).locked; });
    parts.list.replaceChildren();
    order.forEach(function (id) {
      var col = byId(grid, id);
      var item = document.createElement("li");
      var check = document.createElement("div");
      check.className = "form-check";
      var input = document.createElement("input");
      input.className = "form-check-input";
      input.type = "checkbox";
      input.id = "vr-col-" + id;
      input.checked = isVisible(grid, id);
      input.disabled = col.locked;
      input.setAttribute("data-vr-col-toggle", id);
      var label = document.createElement("label");
      label.className = "form-check-label";
      label.htmlFor = input.id;
      label.textContent = col.label;
      check.append(input, label);
      item.append(check);
      if (col.locked) {
        var note = document.createElement("span");
        note.className = "vr-col-locked";
        note.textContent = "Always shown";
        item.append(note);
      } else {
        var position = movable.indexOf(id);
        [["up", "arrow-up", position === 0], ["down", "arrow-down", position === movable.length - 1]].forEach(function (spec) {
          var button = window.vrUi.button("", "secondary", true);
          button.setAttribute("data-vr-col-move", spec[0]);
          button.setAttribute("data-vr-col-id", id);
          button.setAttribute("aria-label", "Move " + col.label + " " + spec[0]);
          button.disabled = spec[2];
          button.innerHTML = window.vrUi.icon(spec[1]);
          item.append(button);
        });
      }
      parts.list.append(item);
    });
    // focus: a selector string, or {id, direction} to keep focus on the moved column's control.
    if (focus) {
      var target = typeof focus === "string" ? parts.list.querySelector(focus) :
        parts.list.querySelector('[data-vr-col-move="' + focus.direction + '"][data-vr-col-id="' + focus.id + '"]:not([disabled])') ||
        parts.list.querySelector('[data-vr-col-id="' + focus.id + '"]:not([disabled])');
      if (target) {
        target.focus();
      }
    }
  }

  function announce(text) {
    var parts = dialogParts();
    parts.status.textContent = "";
    window.setTimeout(function () { parts.status.textContent = text; }, 30);
  }

  function moveColumn(grid, id, direction) {
    var order = currentOrder(grid);
    var movable = order.filter(function (colId) { return !byId(grid, colId).locked; });
    var from = movable.indexOf(id);
    var to = direction === "up" ? from - 1 : from + 1;
    if (from === -1 || to < 0 || to >= movable.length) {
      return;
    }
    movable.splice(to, 0, movable.splice(from, 1)[0]);
    grid.dt.colReorder.order(resolveOrder(grid, movable), true);
    save(grid);
    renderDialog(grid, { id: id, direction: direction });
    announce(byId(grid, id).label + " moved to position " + (to + 1) + " of " + movable.length + ".");
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-vr-columns-for]");
    var parts = dialogParts();
    if (opener && opener.closest("#vr-form-dialog")) {
      event.preventDefault();
      return;
    }
    if (opener && parts && window.bootstrap) {
      dialogGrid = grids[opener.getAttribute("data-vr-columns-for")];
      if (!dialogGrid) {
        return;
      }
      dialogOpener = opener;
      parts.title.textContent = "Columns";
      renderDialog(dialogGrid);
      window.bootstrap.Modal.getOrCreateInstance(parts.dialog).show(opener);
      return;
    }
    var move = event.target.closest("[data-vr-col-move]");
    if (move && dialogGrid) {
      moveColumn(dialogGrid, move.getAttribute("data-vr-col-id"), move.getAttribute("data-vr-col-move"));
      return;
    }
    if (event.target.closest("[data-vr-columns-reset]") && dialogGrid) {
      dialogGrid.dt.colReorder.reset();
      writeLayout(dialogGrid.key, null);
      applyLayout(dialogGrid, null);
      fit(dialogGrid);
      renderDialog(dialogGrid); // Focus stays on the Reset button the user pressed.
      announce("Columns reset to the default layout.");
    }
  });

  document.addEventListener("change", function (event) {
    var toggle = event.target.closest("[data-vr-col-toggle]");
    if (toggle && dialogGrid) {
      var id = toggle.getAttribute("data-vr-col-toggle");
      dialogGrid.dt.column(id + ":name").visible(toggle.checked);
      save(dialogGrid);
      announce(byId(dialogGrid, id).label + (toggle.checked ? " shown." : " hidden."));
    }
  });

  // Bootstrap returns focus only for data-bs-toggle openers; this dialog is opened from script.
  document.addEventListener("hidden.bs.modal", function (event) {
    if (event.target.id === "vr-columns-dialog" && dialogOpener && dialogOpener.isConnected) {
      dialogOpener.focus();
    }
  });

  function initGrids() {
    document.querySelectorAll("[data-vr-form-page] [data-vr-columns-for]").forEach(function (button) {
      button.hidden = true;
    });
    if (!window.DataTable) {
      return; // Library unavailable: lists still work as plain server-rendered tables.
    }
    document.querySelectorAll("table[data-vr-grid]").forEach(enhance);
  }
  document.addEventListener("DOMContentLoaded", initGrids);
  document.addEventListener("htmx:load", initGrids);
})();
