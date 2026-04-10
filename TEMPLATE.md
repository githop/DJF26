# {{ driver }} - {{ date }}

## {{ shift_start }} - {{ shift_end }}

{{ vehicle }} - {{ vehicle_color }} {{ make_model }} - {{ license_plate }}

[Parking process](https://docs.google.com/document/d/1uiPNSprNHtB5df02xG6g0HuZuNMYXbDCk9x9cK8R08g/edit?usp=sharing)

Pickup Location: {{ pickup_location }}
Dropoff Location: {{ dropoff_location }}

# Use the EZPass toll lane

{% for task in tasks %}

### {{ task.start }}: {{ task.details }}

- {{ task.location }} -> {{ task.destination }}
  {% if task.is_airport_pickup %} - Flight: {{ task.flight if task.flight else "TBD" }}{% if task.door %} → {{ task.door }}{% endif %}{% endif %}
  {% if task.notes %} - Note: {{ task.notes }}{% endif %}
  {% endfor %}

# Locations

{% for loc in locations %}

- {{ loc.name }}{% if loc.address %} — [{{ loc.address }}]({{ loc.maps_link }}){% endif %}
  {% if loc.phone %} Phone: {{ loc.phone }}
  {% endif %}
  {% endfor %}

{% if contacts %}

# Contacts

{% for contact in contacts %}
{% if contact.tel_link %}

- {{ contact.name }}: [{{ contact.phone }}]({{ contact.tel_link }})
  {% else %}
- {{ contact.name }}: {{ contact.phone }}
  {% endif %}
  {% endfor %}
  {% endif %}
- GTC Contact: Tom [513-675-4467](tel:5136754467)
- Adi Diner: [917-494-2896](tel:9174942896)

{% if pickup_messages %}

# Artist Pickup Text

Use these prefilled text messages to coordinate pickup with the driver.
Send this to the driver after their flight has landed.

{% for msg in pickup_messages %}

## {{ msg.passenger }} - {{ msg.phone }}

```
{{ msg.message }}
```

{% endfor %}
{% endif %}
