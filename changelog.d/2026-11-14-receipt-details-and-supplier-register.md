---
date: 2026-11-14
type: added
impact: high
title: Receipt details on each lot and a register of suppliers
area: Suppliers
link: suppliers:list
pr: 24
---
A lot is received together with where it came from, the supplier's and manufacturer's lot numbers, the delivery document, the quantity, the containers and what the examination on receipt found. Quality keeps a register of suppliers under **Suppliers**, and the lot list shows the supplier and searches both lot numbers.

## Technical notes

- Receipt details and a supplier register: a lot is received together with where it came from (a supplier from the register, or made on site), the supplier's and manufacturer's lot numbers, the delivery document, the date, the quantity, the containers and what the examination on receipt found. Details are never edited; a correction adds a linked record with its reason while the lot is in quarantine. Quality keeps the register, which records identity only and does not qualify a supplier. The lot list shows the supplier and searches supplier and manufacturer lot numbers. Lots received earlier have no receipt details until an analyst records them.
- Whoever recorded or corrected a lot's receipt details can no longer sign that lot's QC disposition. The **Number** field of the new-lot form is now **Lot number**.
