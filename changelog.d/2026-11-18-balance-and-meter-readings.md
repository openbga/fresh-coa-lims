---
date: 2026-11-18
type: added
impact: high
title: Read values from balances and meters connected to the analyst's computer
area: Testing
link: laboratory:equipment_list
pr: 59
---
Quality can give a balance or meter a **data connection** on its equipment record (**More**, **Set data connection**): the format it answers in, its serial settings and the serial number it reports. METTLER TOLEDO balances (MT-SICS), A&D balances (A&D standard format) and Orion Star A-series meters are supported. On **Record observation** and **Correct observation**, in Chrome or Edge, **Read from** fills a value with the instrument's reading. A weight the balance did not report as stable, another unit or another device is refused. Every reading is kept on the test as the device sent it, whether or not a replicate records it, and the test record and the review show which values were read and which were typed.

## Technical notes

- Migrations `laboratory.0005_device_connections` (`DeviceConnection`, append-only by trigger: only its end is set, once; one current connection per equipment) and `analytical.0012_instrument_readings` (`InstrumentReading`; a trigger refuses deletes and any change except linking a reading once to an observation of the same test recorded by the reader).
- The browser uses the Web Serial API, which needs a secure context (HTTPS, or `localhost`). The application sends no `Permissions-Policy` header; a proxy that adds `serial=()` turns readings off. Without the API values are typed.
- The device's answer is read on the server (`core/device_formats.py`); the browser passes it on base64-encoded to the POST-only JSON endpoint `analytical:instrument_read` and never sends a value.
- New pages `laboratory:equipment_connection_new` and `laboratory:equipment_connection_end`; audit actions `equipment.connection_set`, `equipment.connection_ended` and `instrument.read`; `observation.recorded` and `observation.corrected` list the readings they record. The lot record export adds the section `instrument_readings`.
- The formats were built from the manufacturers' published interface descriptions and tested with simulated devices. Verify each connection with the laboratory's own instrument before relying on it.
