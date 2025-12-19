# CEK Power Outage Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/igorbl/cek_power_outage.svg)](https://github.com/igorbl/cek_power_outage/releases)

Home Assistant integration for monitoring planned power outages from [CEK (Центральна Енергетична Компанія)](https://cek.dp.ua/).

## Features

- 📅 **Outage Date** - Shows the date of scheduled power outages
- ⏰ **Next Outage** - Timestamp of the next scheduled outage
- 📋 **Schedule** - List of all outage time windows for your queue
- ⚡ **Outage Active** - Binary sensor indicating if an outage is currently happening
- 🔄 **Configurable Polling** - Set update interval from 5 to 120 minutes

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/igorbl/cek_power_outage`
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

## Support

If you find this integration useful, please consider giving it a ⭐ on GitHub!

## License

MIT License

