---
title: Set data connection
urls: laboratory:equipment_connection_new
views: laboratory.views.equipment_connection_new
templates: ops/form.html
models: laboratory.Equipment, laboratory.DeviceConnection, core.AuditEvent
reviewed: 2026-11-18
summary: Say how readings are taken from a balance or meter connected to the analyst's computer: its output format, serial settings and serial number. Quality only.
---

## Common tasks
### Connect a balance or meter
1. Choose the [[Output format]] the instrument answers in, and set [[Baud rate]], [[Data bits]], [[Parity]], [[Stop bits]] and [[Flow control]] as set on the instrument.
2. Enter the [[Serial number]] the instrument reports, for a format that reports one.
3. Name the [[Verification record]] of the check that readings arrive unchanged, give a [[Reason]] and select [[Set data connection]].
### Change the settings of a connection
1. Open this page again: it starts from the current connection's settings.
2. Change what differs, name the [[Verification record]] and select [[Set data connection]]. The earlier connection ends and stays in the record.
## Good to know
- Set the instrument to answer requests only, without automatic or continuous output, or its answers are refused.
- A reading from a device whose serial number differs from [[Serial number]] is refused, so name the one the device reports.
- The A&D standard format reports no serial number: the instrument is then the one the analyst selects.
- Software flow control (XON/XOFF) is not available. Set the instrument's handshake to none or hardware.
- Readings are taken in Chrome or Edge on a computer, over HTTPS. In other browsers values are typed.

## Purpose

Record how readings are taken from an instrument connected to the analyst's computer by USB or RS-232, so that results can keep the reading as the device sent it instead of a typed value.

## Who can use it

- Sign-in required. **Quality** only; others receive 403 when opening or posting the page.
- An account holding only the Admin role is refused (403). Admin plus Quality has Quality's authority.

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, Set data connection), title "Set the data connection of ASSET".
- Introduction: when a connection is current, "This replaces the current connection (format, recorded date), which stays in the record with the readings taken through it."; then "Readings are taken in Chrome or Edge on the analyst's computer, through the serial port (USB or RS-232) the instrument is on. Check that readings arrive unchanged before results rely on them, and name where that check is recorded."
- The form in one panel and a **Cancel** / **Set data connection** row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Set data connection** | Always (the equipment record offers it under More to Quality) | Quality | Ends the current connection, records the new one and opens the equipment record with "Data connection set."; refusals appear on the form and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns to the equipment record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Output format | `DeviceConnection.device_format` | Choice: MT-SICS (METTLER TOLEDO balances); A&D standard format (A&D balances); Orion Star A-series meters (GETMEAS, PC (CSV) output) | Yes | "The format the instrument answers in. Set the instrument to answer requests only, without automatic or continuous output." |
| Baud rate | `DeviceConnection.baud_rate` | Choice: 1200 to 115200 | Yes | "As set on the instrument." The help lists each format's factory settings: MT-SICS 9600 baud 8N1, A&D 2400 baud 7E1, Orion Star 9600 baud 8N1 |
| Data bits | `DeviceConnection.data_bits` | Choice: 7 or 8 | Yes | As set on the instrument |
| Parity | `DeviceConnection.parity` | Choice: None, Even, Odd | Yes | As set on the instrument |
| Stop bits | `DeviceConnection.stop_bits` | Choice: 1 or 2 | Yes | As set on the instrument |
| Flow control | `DeviceConnection.flow_control` | Choice: None, Hardware (RTS/CTS); default None | Yes | "Software flow control (XON/XOFF) is not available: set the instrument's handshake to none or hardware." |
| Serial number | `DeviceConnection.serial_number` | Text, max 40 | For MT-SICS and Orion Star; empty for A&D | "As the device reports it. Required for a format that reports one: a reading from a device with another serial number is refused." |
| Verification record | `DeviceConnection.verification_ref` | Text, max 200 | Yes | "Where the check that readings arrive unchanged through this connection is recorded, with its revision." |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the connection is set |
| Current connection | — (hidden `replacing`) | Id | — | The connection that was current when the page opened; a change meanwhile refuses the form |

The first time, the settings start from the MT-SICS factory settings; afterwards from the current connection (except the verification record).

## Rules and hidden logic

- Messages: "State why the data connection is set."; "Enter the serial number the device reports; this format reports it with every reading."; "This format does not report a serial number; leave it empty."; "Enter the serial number without spaces around it."; "The data connection of this equipment changed while you were editing. Reload the page and check the current connection."
- In one transaction the equipment row is locked, the current connection ends (who and when), the new one is stored and `equipment.connection_set` is audited on the equipment with the ended connection before and the new one after.
- A connection is append-only: the database refuses any change to it except its end, once, and refuses deleting it. One connection per equipment is current.
- A reading keeps the connection it was taken through. A replicate cannot record a reading taken through a connection that has since ended or been replaced.
- The connection does not make the instrument fit for use: calibration, qualification and service state are still checked when a result is recorded.
- Not enforced by this page: whether the verification record exists or what it shows. The laboratory checks the interface under its own procedure.

## Related pages

- Equipment record (return target).
- End data connection.
- Record observation (where readings are taken).
