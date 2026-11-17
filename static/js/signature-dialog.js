/* Native focus containment and Escape; server-rendered section remains the no-JS fallback. */
(() => {
  if (!window.HTMLDialogElement) return;
  const content = document.querySelector('[data-signature-dialog]');
  // In the shared form dialog (form-dialog.js) the card is already in a dialog.
  if (!content || content.closest('#vr-form-dialog')) return;
  const cancel = content.querySelector('[data-signature-cancel]');
  // The page is shown before this deferred script runs, so someone may already be typing in
  // one of the fields. Moving the form blurs that field and opening the dialog focuses
  // another; give it back so that no keystroke lands in a different field.
  const typing = content.contains(document.activeElement)
    && document.activeElement.matches('input, textarea, select') ? document.activeElement : null;
  const dialog = document.createElement('dialog');
  dialog.className = 'border-0 rounded p-0 col-11 col-md-8 col-lg-6';
  dialog.setAttribute('aria-labelledby', 'sign-title');
  content.before(dialog);
  dialog.append(content);
  // Leaving without signing returns to the record, and focus returns to the control that opened
  // this signing page (app.js reads the mark on the record page). Nothing is signed or changed.
  const markReturn = () => {
    try {
      window.sessionStorage.setItem('vr-return-focus', window.location.pathname);
    } catch (error) {
      // Storage blocked: the record page opens with focus at its start.
    }
  };
  cancel.addEventListener('click', markReturn);
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    markReturn();
    window.location.assign(cancel.href);
  });
  dialog.showModal();
  const error = content.querySelector('[data-vr-form-errors]');
  if (error) {
    error.setAttribute('tabindex', '-1');
    error.setAttribute('role', 'alert');
  }
  if (typing) {
    // The focus stays where the person is typing; the field then describes the error.
    if (error) {
      error.id = error.id || 'signature-errors';
      const described = typing.getAttribute('aria-describedby');
      typing.setAttribute('aria-describedby', described ? `${error.id} ${described}` : error.id);
    }
    typing.focus();
  } else if (error) {
    error.focus();
  } else {
    content.querySelector('input[type="password"]').focus();
  }
})();
