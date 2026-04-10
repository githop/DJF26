# GTC Daily Agenda — {{ date }}

> {{ total_vehicles }} vehicle(s) | {{ total_shifts }} shift(s) | {{ total_tasks }} GT task(s)

---

## Vehicle Summary

| Vehicle | Shifts | Drivers |
|---------|--------|---------|
{% for v in vehicle_summary %}
| {{ v.name }} ({{ v.color }} {{ v.make_model }}, {{ v.license_plate }}) | {{ v.shift_count }} | {{ v.drivers | join(', ') }} |
{% endfor %}

---

## Shift Overview

{% for block in vehicle_blocks %}
### {{ block.name }}

{% for shift in block.shifts %}
#### [{{ shift.shift_label }}: {{ shift.start }} – {{ shift.end }} — {{ shift.driver }}](/sheet/{{ shift.sheet_filename | replace(' ', '%20') }})

Pickup: {{ shift.pickup }} | Dropoff: {{ shift.dropoff }}

{% if shift.tasks %}
| Time | Details | From | To | Pax | Notes |
|------|---------|------|----|-----|-------|
{% for t in shift.tasks %}
| {{ t.start }} | {{ t.details }} | {{ t.origin }} | {{ t.destination }} | {{ t.pax }} | {{ t.notes }} |
{% endfor %}
{% else %}
_No GT tasks assigned to this shift._
{% endif %}

{% endfor %}
{% endfor %}

---

## Full Timeline

All GT tasks for the day in chronological order.

| Time | Vehicle | Driver | Details | From | To | Pax | Notes |
|------|---------|--------|---------|------|----|-----|-------|
{% for t in timeline %}
| {{ t.start }} | {{ t.vehicle }} | {{ t.driver }} | {{ t.details }} | {{ t.origin }} | {{ t.destination }} | {{ t.pax }} | {{ t.notes }} |
{% endfor %}

{% if uncovered %}
---

## Uncovered Tasks

These GT tasks fall outside all defined driver shift windows.

| Time | Vehicle | Details | Notes |
|------|---------|---------|-------|
{% for t in uncovered %}
| {{ t.start }} | {{ t.vehicle }} | {{ t.details }} | {{ t.notes }} |
{% endfor %}
{% endif %}
