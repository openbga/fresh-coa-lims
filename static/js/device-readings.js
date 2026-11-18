/* Readings from balances and meters connected to this computer (Web Serial API).

   A form page that carries the JSON element #vr-reading-options (analytical/readings.py
   form_options) offers, under each value a connected instrument can supply, a button that reads
   the instrument: the browser asks which serial port it is on (once per instrument and page),
   opens it with the data connection's settings, sends the requests of its format and passes the
   bytes the device answered, unchanged, to the server. The server reads them, keeps the reading
   on the test and answers the value, which fills the field (read-only) and its hidden reading
   field. "Type instead" clears the reading; the value is then typed. Without the Web Serial API
   or without this script values are typed, and the server checks every reading a form names. */
(() => {
  const supported = Boolean(window.isSecureContext && navigator.serial);
  const ports = new Map(); // equipment id -> SerialPort chosen on this page
  const busy = new Set(); // equipment ids being read now: one exchange per port at a time
  const encoder = new TextEncoder();

  const csrfToken = () => {
    try {
      return JSON.parse(document.body.getAttribute('hx-headers') || '{}')['X-CSRFToken'] || '';
    } catch (error) {
      return '';
    }
  };

  const encode = (bytes) => {
    let binary = '';
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary);
  };

  const icon = (name) => (window.vrUi && window.vrUi.icon ? window.vrUi.icon(name) : '');

  const element = (tag, attributes = {}, text = '') => {
    const node = document.createElement(tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    if (text) node.textContent = text;
    return node;
  };

  // Read until the answer to one request has ended (its `until` text arrived after the request)
  // or `wait` milliseconds passed. Returns false when the time ran out.
  const readStep = async (reader, received, step) => {
    const start = received.length;
    const until = encoder.encode(step.until);
    const ended = () => {
      for (let i = start; i + until.length <= received.length; i += 1) {
        if (until.every((byte, j) => received[i + j] === byte)) return true;
      }
      return false;
    };
    let timer;
    const timeout = new Promise((resolve) => {
      timer = setTimeout(() => resolve({ timedOut: true }), step.wait);
    });
    try {
      while (!ended()) {
        const result = await Promise.race([reader.read(), timeout]);
        if (result.timedOut) return false;
        if (result.done) return false;
        result.value.forEach((byte) => received.push(byte));
        if (received.length > 2048) return false;
      }
      return true;
    } finally {
      clearTimeout(timer);
    }
  };

  // A promise that settles true when `promise` resolves within `ms`, false when time runs out.
  const within = (promise, ms) => {
    let timer;
    return Promise.race([
      promise.then(() => true),
      new Promise((resolve) => {
        timer = setTimeout(() => resolve(false), ms);
      }),
    ]).finally(() => clearTimeout(timer));
  };

  // Send each request of the format and collect what the device answers. Always releases and
  // closes the port, also when a write never completes (a device that never raises CTS under
  // hardware flow control) or the device stops answering.
  const exchange = async (instrument) => {
    let port = ports.get(instrument.equipment);
    if (!port) {
      port = await navigator.serial.requestPort();
      ports.set(instrument.equipment, port);
    }
    const received = [];
    let writer;
    let reader;
    try {
      await port.open({ ...instrument.open, bufferSize: 4096 });
      writer = port.writable.getWriter();
      reader = port.readable.getReader();
      for (const step of instrument.steps) {
        if (!(await within(writer.write(encoder.encode(step.send)), step.wait))) {
          await writer.abort().catch(() => {});
          break;
        }
        if (!(await readStep(reader, received, step))) break;
      }
    } finally {
      if (reader) {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
      if (writer) {
        try {
          writer.releaseLock();
        } catch (error) {
          /* already released by the abort */
        }
      }
      await port.close().catch(() => {});
    }
    return Uint8Array.from(received);
  };

  const setup = (options) => {
    const form = document
      .querySelector(`[name="${CSS.escape(options.fields[0].name)}"]`)
      ?.closest('form');
    if (!form) return;
    const checkbox = (equipment) =>
      form.querySelector(`input[name="equipment_ids"][value="${CSS.escape(String(equipment))}"]`);

    options.fields.forEach((field) => {
      const input = form.querySelector(`[name="${CSS.escape(field.name)}"]`);
      const hidden = form.querySelector(`input[name="reading_${CSS.escape(field.name)}"]`);
      if (!input || !hidden) return;
      const anchor = input.closest('.vr-unit-group') || input;
      const box = element('div', { class: 'vr-reading', 'data-vr-reading': field.name });
      const status = element('div', { class: 'vr-reading-status', role: 'status' });
      const controls = element('div', { class: 'vr-reading-actions' });
      box.append(controls, status);
      anchor.insertAdjacentElement('afterend', box);

      if (!supported) {
        status.textContent =
          'Reading from an instrument needs Chrome or Edge on a computer, over HTTPS. ' +
          'Type the value as read.';
        return;
      }

      const showReading = (reading) => {
        status.replaceChildren();
        status.classList.remove('vr-reading-error');
        const text = element('span');
        text.textContent = `Read from ${reading.asset_id} at ${reading.read_at}: `;
        const raw = element('code', { class: 'vr-code vr-reading-raw' }, reading.response);
        const clear = element('button', { type: 'button', class: 'btn btn-link btn-sm' }, 'Type instead');
        clear.addEventListener('click', () => {
          hidden.value = '';
          input.readOnly = false;
          input.value = '';
          status.replaceChildren();
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.focus();
        });
        status.append(text, raw, clear);
      };

      const showError = (message) => {
        status.replaceChildren();
        status.classList.add('vr-reading-error');
        status.textContent = message;
      };

      const read = async (instrument, button) => {
        if (busy.has(instrument.equipment)) {
          showError(`${instrument.asset_id} is being read for another value. Wait for it to finish.`);
          return;
        }
        busy.add(instrument.equipment);
        button.disabled = true;
        status.classList.remove('vr-reading-error');
        status.textContent = `Reading ${instrument.asset_id}…`;
        try {
          let bytes;
          try {
            bytes = await exchange(instrument);
          } catch (error) {
            if (error && error.name === 'NotFoundError') {
              showError('No serial port was chosen. Choose the port the instrument is on.');
            } else {
              ports.delete(instrument.equipment);
              showError(
                `The serial port of ${instrument.asset_id} could not be used (${error && error.message ? error.message : error}). Check the cable and that no other program has the port open.`,
              );
            }
            return;
          }
          const body = new FormData();
          body.append('target', field.target);
          body.append('connection', String(instrument.connection));
          body.append('response', encode(bytes));
          const answer = await fetch(options.url, {
            method: 'POST',
            body,
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken() },
          });
          let data = {};
          try {
            data = await answer.json();
          } catch (error) {
            data = { error: 'The server did not answer. Read again.' };
          }
          if (!answer.ok) {
            showError(data.error || 'The reading was refused.');
            return;
          }
          input.value = data.value;
          input.readOnly = true;
          hidden.value = String(data.reading);
          const box = checkbox(instrument.equipment);
          if (box && !box.checked) {
            box.checked = true;
            box.dispatchEvent(new Event('change', { bubbles: true }));
          }
          input.dispatchEvent(new Event('input', { bubbles: true }));
          showReading(data);
        } finally {
          busy.delete(instrument.equipment);
          button.disabled = false;
        }
      };

      const label = (instrument) => `Read from ${instrument.asset_id}`;
      // The instruments that can supply this value: balances beside a mass, meters otherwise.
      const offered = options.instruments.filter((instrument) =>
        (field.instruments || []).includes(instrument.connection),
      );
      if (!offered.length) {
        box.remove();
        return;
      }
      if (offered.length === 1) {
        const instrument = offered[0];
        const button = element('button', { type: 'button', class: 'btn btn-outline-secondary btn-sm' });
        button.innerHTML = icon('download');
        button.append(document.createTextNode(label(instrument)));
        button.addEventListener('click', () => read(instrument, button));
        controls.append(button);
      } else {
        const menu = element('div', { class: 'dropdown' });
        const toggle = element('button', {
          type: 'button',
          class: 'btn btn-outline-secondary btn-sm dropdown-toggle',
          'data-bs-toggle': 'dropdown',
          'aria-expanded': 'false',
        });
        toggle.innerHTML = icon('download');
        toggle.append(document.createTextNode(`Read ${field.label.toLowerCase()} from`));
        const list = element('ul', { class: 'dropdown-menu' });
        offered.forEach((instrument) => {
          const item = element(
            'button',
            { type: 'button', class: 'dropdown-item' },
            `${instrument.asset_id} · ${instrument.description}`,
          );
          item.addEventListener('click', () => read(instrument, toggle));
          const entry = element('li');
          entry.append(item);
          list.append(entry);
        });
        menu.append(toggle, list);
        controls.append(menu);
      }

      // A page shown again after a refused submission keeps the readings already taken.
      const taken = options.taken && options.taken[field.name];
      if (taken && hidden.value === String(taken.reading)) {
        input.readOnly = true;
        showReading(taken);
      }
    });
  };

  const init = (root) => {
    const source = (root || document).querySelector
      ? (root || document).querySelector('#vr-reading-options')
      : null;
    if (!source || source.dataset.vrReady) return;
    source.dataset.vrReady = '1';
    let options;
    try {
      options = JSON.parse(source.textContent);
    } catch (error) {
      return;
    }
    if (options && options.fields && options.fields.length && options.instruments.length) {
      setup(options);
    }
  };

  if (!window.vrReadings) {
    window.vrReadings = { init };
    // The form dialog swaps a form page in; its script runs again and finds the new options.
    document.addEventListener('htmx:afterSettle', (event) => window.vrReadings.init(event.target));
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.vrReadings.init(document));
  } else {
    window.vrReadings.init(document);
  }
})();
