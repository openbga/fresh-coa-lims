// Page documentation: restore the saved open state and width before the first paint so the
// layout does not jump. pagedocs.js owns the behaviour; this only sets two root hooks.
(function () {
  "use strict";
  try {
    var root = document.documentElement;
    var width = parseInt(localStorage.getItem("openbga-qlab-pagedocs-width"), 10);
    if (width >= 280 && width <= 960) {
      root.style.setProperty("--pagedocs-width", width + "px");
    }
    if (localStorage.getItem("openbga-qlab-pagedocs-open") === "1") {
      root.classList.add("pagedocs-open");
    }
  } catch (error) {
    // Storage blocked: the panel starts closed at its default width.
  }
})();
