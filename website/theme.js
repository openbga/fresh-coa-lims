// Applies the saved theme before the stylesheets paint, so the page never flashes the other theme.
// Loaded synchronously in <head>. Key "vr-theme" is shared with the application: "light" | "dark" |
// "system" (default). The menu itself is in site.js.
(function () {
  "use strict";
  var choice = "system";
  try {
    choice = localStorage.getItem("vr-theme") || "system";
  } catch (error) {
    // Storage blocked: follow the system setting.
  }
  var dark = choice === "dark" ||
    (choice !== "light" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-bs-theme", dark ? "dark" : "light");
  document.documentElement.classList.add("has-js");
})();
