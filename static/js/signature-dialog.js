/* Native focus containment and Escape; server-rendered section remains the no-JS fallback. */
(() => {
  if (!window.HTMLDialogElement) return;
  const content = document.querySelector('[data-signature-dialog]');
  if (!content) return;
  const cancel = content.querySelector('[data-signature-cancel]');
  const dialog = document.createElement('dialog');
  dialog.className = 'border-0 rounded p-0 col-11 col-md-8 col-lg-6';
  dialog.setAttribute('aria-labelledby', 'sign-title');
  content.before(dialog);
  dialog.append(content);
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    window.location.assign(cancel.href);
  });
  dialog.showModal();
  const error = content.querySelector('.errorlist');
  if (error) {
    error.setAttribute('tabindex', '-1');
    error.setAttribute('role', 'alert');
    error.focus();
  } else {
    content.querySelector('input[type="password"]').focus();
  }
})();
