# CEK Power Outage Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/igorblyzn/cek-ha.svg)](https://github.com/igorblyzn/cek-ha/releases)

Home Assistant integration for monitoring planned power outages from [CEK (Центральна Енергетична Компанія)](https://cek.dp.ua/).

## Features

- 📅 **Outage Date** - Shows the date of scheduled power outages
- 🗓️ **All Days** - Schedules for every published day (today, tomorrow) with updates applied
- ⏰ **Next Outage** - Timestamp of the next scheduled outage
- 📋 **Schedule** - List of all outage time windows for your queue
- ⚡ **Outage Active** - Binary sensor indicating if an outage is currently happening
- 📊 **Timeline Visualization** - SVG and ASCII timeline charts
- 🔄 **Configurable Polling** - Set update interval from 5 to 120 minutes
- 💾 **Data Caching** - Maintains last known data during network issues

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/igorblyzn/cek-ha`
5. Select category: "Integration"
6. Click "Add"
7. Search for "CEK Power Outage" and install
8. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/cek_power_outage` to your Home Assistant's `custom_components` folder
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "CEK Power Outage"
4. Enter your queue number (e.g., `6.2`)
5. Set the polling interval (5-120 minutes)

### Change Polling Interval

1. Go to **Settings** → **Devices & Services**
2. Find "CEK Power Outage"
3. Click **Configure**
4. Adjust the update interval

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.cek_power_outage_X_outage_date` | Sensor | Date of scheduled outages |
| `sensor.cek_power_outage_X_schedule` | Sensor | Comma-separated time ranges |
| `sensor.cek_power_outage_X_next_outage` | Sensor | Next outage start timestamp |
| `binary_sensor.cek_power_outage_X_outage_active` | Binary Sensor | True if outage is currently active |

> **Note:** Replace `X` with your queue number (e.g., `6_2` for queue 6.2)

## Template Queries

### Basic Queries

```yaml
# Queue number
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'queue') }}
# Result: "6.2"

# Outage date
{{ states('sensor.cek_power_outage_6_2_outage_date') }}
# Result: "19 грудня"

# Schedule as text
{{ states('sensor.cek_power_outage_6_2_schedule') }}
# Result: "06:00 до 09:30, 16:30 до 20:00, 23:30 до 24:00"

# Next outage timestamp
{{ states('sensor.cek_power_outage_6_2_next_outage') }}
# Result: "2024-12-19T06:00:00"

# Outage active status
{{ states('binary_sensor.cek_power_outage_6_2_outage_active') }}
# Result: "on" or "off"
```

### Schedule Attributes

```yaml
# Time ranges as list
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'time_ranges') }}
# Result: ["06:00 до 09:30", "16:30 до 20:00", "23:30 до 24:00"]

# Number of outage periods
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'time_ranges') | length }}
# Result: 3

# First outage period
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'time_ranges')[0] }}
# Result: "06:00 до 09:30"

# Outage percentage of the day
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'outage_percentage') }}
# Result: 25.3
```

### Timeline Visualization

```yaml
# SVG Timeline (for Markdown card)
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_svg') }}

# ASCII Timeline
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_ascii') }}
# Result:
# 00    06    12    18    24
# ░░░░░░░░░░░░███████░░░░░░░░░░░░░░░████████░░░░░░░░░░██
```

### All Days

The page usually publishes today and tomorrow. Every day from today on is in the `days` attribute (updates for each day are already applied):

```yaml
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'days') }}
# Result:
# - date: "2024-12-19"
#   date_label: "19 грудня"
#   is_today: true
#   time_ranges: ["06:00 до 09:30", "16:30 до 20:00"]
#   outage_hours: 7.0
#   has_update: false
#   timeline_svg: "<svg ...>"
# - date: "2024-12-20"
#   ...
```

### Status Attributes

```yaml
# Last successful update timestamp
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'last_updated') }}
# Result: "2024-12-19T14:35:22.123456"

# Last error (empty if no error)
{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'last_error') }}
```

## Lovelace Card Examples

### Basic Markdown Card with SVG Timeline

```yaml
type: markdown
content: |
  ## ⚡ Power Outage Schedule
  
  **Queue:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'queue') }}
  
  ![timeline](data:image/svg+xml,{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_svg') | urlencode }})
```

### Full Dashboard Card

```yaml
type: markdown
content: |
  ## ⚡ Power Outage - Queue {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'queue') }}
  
  **Date:** {{ states('sensor.cek_power_outage_6_2_outage_date') }}
  
  ![timeline](data:image/svg+xml,{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_svg') | urlencode }})
  
  **Status:** {% if is_state('binary_sensor.cek_power_outage_6_2_outage_active', 'on') %}🔴 Outage Active{% else %}🟢 Power On{% endif %}
  
  **Schedule:**
  {% for range in state_attr('sensor.cek_power_outage_6_2_schedule', 'time_ranges') or [] -%}
  - {{ range }}
  {% endfor %}
  
  **Total outage:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'outage_percentage') }}% of the day
```

### All Days Card

Shows every published day stacked in one card:

```yaml
type: markdown
content: |
  {% set days = state_attr('sensor.cek_power_outage_6_2_schedule', 'days') or [] %}
  {% for day in days %}
  ### {{ '📅 Today' if day.is_today else '🗓️ ' ~ day.date_label }}{{ ' ⚠️ updated' if day.has_update else '' }}

  ![timeline](data:image/svg+xml,{{ day.timeline_svg | urlencode }})

  {% for range in day.time_ranges -%}
  - {{ range }}
  {% else -%}
  ✅ No outages
  {% endfor %}
  **Total outage:** {{ day.outage_hours }} hours
  {% else %}
  ✅ No schedule published
  {% endfor %}

  **Last updated:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'last_check') | as_datetime | relative_time }} ago
```

### Swipeable Days Card

Requires [swipe-card](https://github.com/bramkragten/swipe-card) from HACS. One slide per day (index 0 = first published day, 1 = next):

```yaml
type: custom:swipe-card
parameters:
  pagination:
    type: bullets
cards:
  - type: markdown
    content: >
      {% set day = (state_attr('sensor.cek_power_outage_6_2_schedule', 'days') or [])[0] %}
      {% if day %}
      ### {{ '📅 Today' if day.is_today else '🗓️ ' ~ day.date_label }}{{ ' ⚠️ updated' if day.has_update else '' }}

      ![timeline](data:image/svg+xml,{{ day.timeline_svg | urlencode }})

      {{ day.time_ranges | join(', ') or '✅ No outages' }}

      **Total outage:** {{ day.outage_hours }} hours
      {% else %}✅ No schedule published{% endif %}
  - type: markdown
    content: >
      {% set day = (state_attr('sensor.cek_power_outage_6_2_schedule', 'days') or [])[1] %}
      {% if day %}
      ### 🗓️ {{ day.date_label }}{{ ' ⚠️ updated' if day.has_update else '' }}

      ![timeline](data:image/svg+xml,{{ day.timeline_svg | urlencode }})

      {{ day.time_ranges | join(', ') or '✅ No outages' }}

      **Total outage:** {{ day.outage_hours }} hours
      {% else %}⏳ Tomorrow's schedule not published yet{% endif %}
```

### Card with Error Handling

```yaml
type: markdown
content: |
  ## ⚡ Power Outage Schedule
  
  **Queue:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'queue') | default('N/A') }}
  
  {% if states('sensor.cek_power_outage_6_2_schedule') == 'unavailable' %}
  ⚠️ **Error:** Unable to fetch schedule. Check internet connection.
  {% elif states('sensor.cek_power_outage_6_2_schedule') == 'No outages' %}
  ✅ **No scheduled outages today**
  {% else %}
  {% if state_attr('sensor.cek_power_outage_6_2_schedule', 'last_error') %}
  ⚠️ **Warning:** Using cached data. Network error occurred.
  {% endif %}
  
  **Date:** {{ states('sensor.cek_power_outage_6_2_outage_date') | default('Unknown') }}
  
  ![timeline](data:image/svg+xml,{{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_svg') | urlencode }})
  
  **Status:** {% if is_state('binary_sensor.cek_power_outage_6_2_outage_active', 'on') %}🔴 Outage Active{% else %}🟢 Power On{% endif %}
  
  **Schedule:**
  {% for range in state_attr('sensor.cek_power_outage_6_2_schedule', 'time_ranges') or [] -%}
  - {{ range }}
  {% endfor %}
  
  **Total outage:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'outage_percentage') | default(0) }}% of the day
  
  **Last updated:** {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'last_updated') | as_datetime | relative_time }} ago
  {% endif %}
```

### ASCII Timeline Card

```yaml
type: markdown
content: |
  ## Power Outage Timeline
  
  <pre style="font-family: monospace; line-height: 1.2;">
  {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'timeline_ascii') }}
  </pre>
  
  Legend: ░ = Power On | █ = Outage
```

## Example Automations

### Notification Before Outage

```yaml
automation:
  - alias: "Notify 30 min before power outage"
    trigger:
      - platform: template
        value_template: >
          {{ now() >= (states('sensor.cek_power_outage_6_2_next_outage') | as_datetime - timedelta(minutes=30)) }}
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Power Outage Warning"
          message: "Power outage starts in 30 minutes!"
```

### Turn Off Devices During Outage

```yaml
automation:
  - alias: "Turn off devices during outage"
    trigger:
      - platform: state
        entity_id: binary_sensor.cek_power_outage_6_2_outage_active
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.your_device
```

### Daily Schedule Notification

```yaml
automation:
  - alias: "Daily outage schedule notification"
    trigger:
      - platform: time
        at: "07:00:00"
    condition:
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.cek_power_outage_6_2_schedule
            state: "No outages"
    action:
      - service: notify.mobile_app
        data:
          title: "📋 Today's Power Outage Schedule"
          message: >
            Queue {{ state_attr('sensor.cek_power_outage_6_2_schedule', 'queue') }}:
            {{ states('sensor.cek_power_outage_6_2_schedule') }}
```

## Support

If you find this integration useful, please consider giving it a ⭐ on GitHub!

## License

MIT License
