// Page documentation: apply the saved width before the first paint so the layout does not jump.
// The open state and width are the signed-in person's preferences (core/preferences.py); the
// shell renders them on <html> (class "pagedocs-open", data-pagedocs-width). pagedocs.js owns the
// behaviour; this only turns the width into the CSS variable (CSSOM, allowed by the CSP).
(function () {
  "use strict";
  var root = document.documentElement;
  var width = parseInt(root.getAttribute("data-pagedocs-width"), 10);
  if (width >= 280 && width <= 960) {
    root.style.setProperty("--pagedocs-width", width + "px");
  }
})();
