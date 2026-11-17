// Presentation site: the theme menu (Light, Dark or System, stored in localStorage "vr-theme", the
// application's key) and changes made in another tab or in the system setting. Without JavaScript
// the menu stays hidden and the page follows the system setting.
(function () {
  "use strict";
  var KEY = "vr-theme";
  var root = document.documentElement;
  var systemDark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function saved() {
    try {
      return localStorage.getItem(KEY) || "system";
    } catch (error) {
      return "system";
    }
  }

  function apply(choice) {
    if (choice !== "light" && choice !== "dark") choice = "system";
    var dark = choice === "dark" || (choice === "system" && !!systemDark && systemDark.matches);
    root.setAttribute("data-bs-theme", dark ? "dark" : "light");
    document.querySelectorAll("[data-theme-label]").forEach(function (text) {
      text.textContent = choice.charAt(0).toUpperCase() + choice.slice(1);
    });
    document.querySelectorAll("[data-theme-value]").forEach(function (option) {
      option.setAttribute("aria-pressed", option.getAttribute("data-theme-value") === choice ? "true" : "false");
    });
  }

  function setOpen(menu, open, focusButton) {
    var button = menu.querySelector("[data-theme-button]");
    var options = menu.querySelector("[data-theme-options]");
    button.setAttribute("aria-expanded", open ? "true" : "false");
    options.hidden = !open;
    if (open) {
      (options.querySelector('[aria-pressed="true"]') || options.querySelector("button")).focus();
    } else if (focusButton) {
      button.focus();
    }
  }

  document.querySelectorAll("[data-theme-menu]").forEach(function (menu) {
    var button = menu.querySelector("[data-theme-button]");
    var options = menu.querySelector("[data-theme-options]");
    var items = Array.prototype.slice.call(options.querySelectorAll("[data-theme-value]"));
    button.addEventListener("click", function () { setOpen(menu, options.hidden, false); });
    button.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setOpen(menu, true, false);
      }
    });
    items.forEach(function (item, index) {
      item.addEventListener("click", function () {
        var choice = item.getAttribute("data-theme-value");
        try {
          localStorage.setItem(KEY, choice);
        } catch (error) {
          // Storage blocked: the choice applies to this page only.
        }
        apply(choice);
        setOpen(menu, false, true);
      });
      item.addEventListener("keydown", function (event) {
        var next = null;
        if (event.key === "ArrowDown") next = items[(index + 1) % items.length];
        if (event.key === "ArrowUp") next = items[(index - 1 + items.length) % items.length];
        if (event.key === "Home") next = items[0];
        if (event.key === "End") next = items[items.length - 1];
        if (next) {
          event.preventDefault();
          next.focus();
        }
      });
    });
    menu.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !options.hidden) {
        event.preventDefault();
        setOpen(menu, false, true);
      }
    });
    document.addEventListener("click", function (event) {
      if (!menu.contains(event.target) && !options.hidden) setOpen(menu, false, false);
    });
  });

  if (systemDark) {
    systemDark.addEventListener("change", function () { apply(saved()); });
  }
  window.addEventListener("storage", function (event) {
    if (event.key === KEY) apply(saved());
  });
  apply(saved());
})();
