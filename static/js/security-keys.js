/* Security keys and passkeys (Web Authentication). A form marked data-security-key="get" or
   "create" reads its options from the JSON element named in data-security-key-options, asks
   the browser, puts the answer in its hidden security_key_response field and submits again
   with the same button. Without this script, or in a browser without Web Authentication, the
   forms still accept codes; the server checks every answer. */
(() => {
  const forms = document.querySelectorAll('form[data-security-key]');
  if (!forms.length) return;
  const supported = Boolean(
    window.isSecureContext && window.PublicKeyCredential && navigator.credentials,
  );

  const decode = (text) => {
    const base64 = text.replace(/-/g, '+').replace(/_/g, '/');
    const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4));
    return Uint8Array.from(binary, (c) => c.charCodeAt(0));
  };
  const encode = (buffer) => {
    let binary = '';
    new Uint8Array(buffer).forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  };
  const descriptors = (list) => (list || []).map((item) => ({ ...item, id: decode(item.id) }));
  const answer = (credential) => {
    const r = credential.response;
    const response = { clientDataJSON: encode(r.clientDataJSON) };
    if (r.attestationObject) {
      response.attestationObject = encode(r.attestationObject);
      if (typeof r.getTransports === 'function') response.transports = r.getTransports();
    } else {
      response.authenticatorData = encode(r.authenticatorData);
      response.signature = encode(r.signature);
      if (r.userHandle) response.userHandle = encode(r.userHandle);
    }
    return JSON.stringify({
      id: credential.id,
      rawId: encode(credential.rawId),
      type: credential.type,
      authenticatorAttachment: credential.authenticatorAttachment || undefined,
      response,
      clientExtensionResults: credential.getClientExtensionResults(),
    });
  };
  // A form without a code field names its own way out in data-security-key-fallback.
  const refusal = (fallback) => ({
    NotAllowedError: `The security key was not used, or the request timed out. Try again, or ${fallback}.`,
    InvalidStateError: 'This key is already registered for your account. Use another key.',
    SecurityError: 'This browser does not allow security keys at this address.',
    AbortError: 'The request was cancelled. Try again.',
  });

  document.querySelectorAll('[data-security-key-unsupported]').forEach((notice) => {
    notice.hidden = supported;
  });

  forms.forEach((form) => {
    const mode = form.dataset.securityKey;
    const source = document.getElementById(form.dataset.securityKeyOptions);
    const field = form.elements.namedItem('security_key_response');
    const status = form.querySelector('[data-security-key-status]');
    const fallback = form.dataset.securityKeyFallback || 'use a code';
    const refusals = refusal(fallback);
    const buttons = [...form.elements].filter((e) => e.matches('[data-security-key-button]'));
    const needKey = [...form.elements].filter((e) =>
      e.matches('[data-security-key-button], [data-security-key-required]'),
    );
    if (!source || !field) return;
    if (!supported) {
      needKey.forEach((button) => {
        button.disabled = true;
      });
      return;
    }
    // The guard is a disabled default button that keeps Enter from pressing any other one.
    const submits = [...form.elements].filter(
      (e) => e.type === 'submit' && !e.matches('[data-default-guard]'),
    );
    const controls = [...submits, ...buttons];
    const busy = (value) => {
      controls.forEach((button) => {
        button.disabled = value;
      });
    };
    let asking = false;
    let answered = false;
    let sent = false;
    // A page restored from the browser's back-forward cache starts over: its challenge was
    // spent, and the server refuses a resent answer without counting it.
    window.addEventListener('pageshow', (event) => {
      if (!event.persisted) return;
      asking = false;
      answered = false;
      sent = false;
      field.value = '';
      busy(false);
      if (status) status.textContent = '';
    });
    const ask = async (submitter) => {
      if (asking || answered || sent) return;
      asking = true;
      const code = form.elements.namedItem('otp_code');
      busy(true);
      if (status) {
        status.textContent =
          mode === 'create'
            ? 'Follow your browser’s prompts to register the key.'
            : 'Use your security key when your browser asks.';
      }
      try {
        const options = JSON.parse(source.textContent);
        options.challenge = decode(options.challenge);
        let credential;
        if (mode === 'create') {
          options.user = { ...options.user, id: decode(options.user.id) };
          options.excludeCredentials = descriptors(options.excludeCredentials);
          credential = await navigator.credentials.create({ publicKey: options });
        } else {
          options.allowCredentials = descriptors(options.allowCredentials);
          credential = await navigator.credentials.get({ publicKey: options });
        }
        field.value = answer(credential);
        if (code) code.value = '';
        if (status) status.textContent = 'Checking…';
        answered = true;
        // Every other control stays disabled: the answer is sent once, with this button.
        const chosen = submitter && submitter.form === form ? submitter : undefined;
        if (chosen) chosen.disabled = false;
        form.requestSubmit(chosen);
      } catch (error) {
        busy(false);
        if (status) {
          status.textContent =
            refusals[error.name] || `The security key could not be used. Try again, or ${fallback}.`;
        }
      } finally {
        asking = false;
      }
    };
    // A button that always uses the key (type="button", so Enter in the code field never
    // presses it).
    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        field.value = '';
        ask(null);
      });
    });
    form.addEventListener('submit', (event) => {
      if (answered) {
        // The answer goes once; a second press while the page loads sends nothing.
        if (sent) event.preventDefault();
        sent = true;
        return;
      }
      if (asking || sent) {
        // One submission per page: a second press while it loads sends nothing.
        event.preventDefault();
        return;
      }
      field.value = '';
      const code = form.elements.namedItem('otp_code');
      const password = form.elements.namedItem('current_password');
      const name = form.elements.namedItem('name');
      // A typed code is used as typed; a missing password or name is for the server to report.
      if (
        (mode === 'get' && code && code.value.trim()) ||
        (password && !password.value) ||
        (mode === 'create' && name && !name.value.trim())
      ) {
        sent = true;
        return;
      }
      event.preventDefault();
      ask(event.submitter || null);
    });
  });
})();
