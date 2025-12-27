"""Sensor platform for CEK Power Outage."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CEKDataUpdateCoordinator


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="date",
        name="Outage Date",
        icon="mdi:calendar",
    ),
    SensorEntityDescription(
        key="next_outage",
        name="Next Outage",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert",
    ),
    SensorEntityDescription(
        key="schedule",
        name="Schedule",
        icon="mdi:format-list-bulleted",
    ),
    SensorEntityDescription(
        key="outage_hours",
        name="Outage Hours",
        native_unit_of_measurement="h",
        icon="mdi:clock-outline",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CEK Power Outage sensors."""
    coordinator: CEKDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CEKSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class CEKSensor(CoordinatorEntity[CEKDataUpdateCoordinator], SensorEntity):
    """Representation of a CEK Power Outage sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CEKDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"CEK Power Outage ({coordinator.queue})",
            "manufacturer": "CEK",
            "model": f"Queue {coordinator.queue}",
        }

    @property
    def native_value(self) -> str | datetime | float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        key = self.entity_description.key

        if key == "schedule":
            schedule = self.coordinator.data.get("schedule", [])
            return ", ".join(schedule) if schedule else "No outages"

        if key == "outage_hours":
            schedule = self.coordinator.data.get("schedule", [])
            return self._calculate_outage_hours(schedule)

        return self.coordinator.data.get(key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        attrs: dict[str, Any] = {
            "queue": self.coordinator.data.get("queue"),
        }

        # Add last_check (every attempt) and last_updated (successful only)
        if self.coordinator.last_check:
            attrs["last_check"] = self.coordinator.last_check.isoformat()

        if self.coordinator.last_updated:
            attrs["last_updated"] = self.coordinator.last_updated.isoformat()

        # Add error info if there was a fetch error
        if self.coordinator.last_error:
            attrs["last_error"] = self.coordinator.last_error

        if self.entity_description.key == "schedule":
            schedule = self.coordinator.data.get("schedule", [])
            attrs["time_ranges"] = schedule
            attrs["timeline_svg"] = self._generate_timeline_svg(schedule)
            attrs["timeline_ascii"] = self._generate_ascii_timeline(schedule)
            attrs["outage_percentage"] = self._calculate_outage_percentage(schedule)
            attrs["has_update"] = self.coordinator.data.get("has_update", False)
            if self.coordinator.data.get("update_announcement"):
                attrs["update_announcement"] = self.coordinator.data.get("update_announcement")

        return attrs

    def _generate_timeline_svg(self, schedule: list[str]) -> str:
        """Generate SVG timeline visualization with current time marker."""
        width = 480
        height = 44
        bar_y = 20
        bar_height = 20

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
            # Background bar
            f'<rect x="0" y="{bar_y}" width="{width}" height="{bar_height}" rx="4" fill="#2d3436"/>',
        ]

        # Outage blocks
        for time_range in schedule:
            match = re.match(r"(\d{2}):(\d{2})\s*до\s*(\d{2}):(\d{2})", time_range)
            if match:
                start_h, start_m = int(match.group(1)), int(match.group(2))
                end_h, end_m = int(match.group(3)), int(match.group(4))

                start_pct = (start_h * 60 + start_m) / 1440
                end_pct = (end_h * 60 + end_m) / 1440

                x = start_pct * width
                w = (end_pct - start_pct) * width

                svg_parts.append(
                    f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="{bar_height}" rx="2" fill="#e74c3c"/>'
                )

        # Hour markers
        for h in range(0, 25, 6):
            x = (h / 24) * width
            svg_parts.append(
                f'<text x="{x}" y="12" font-size="10" fill="#b2bec3" '
                f'text-anchor="middle" font-family="sans-serif">{h:02d}:00</text>'
            )

        # Current time marker
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        current_x = (current_minutes / 1440) * width

        # Triangle marker on top
        svg_parts.append(
            f'<polygon points="{current_x-4},16 {current_x+4},16 {current_x},{bar_y}" fill="#00cec9"/>'
        )
        # Vertical line through the bar
        svg_parts.append(
            f'<line x1="{current_x}" y1="{bar_y}" x2="{current_x}" y2="{bar_y + bar_height}" '
            f'stroke="#00cec9" stroke-width="2"/>'
        )
            # Tick marks
            svg_parts.append(
                f'<line x1="{x}" y1="16" x2="{x}" y2="{bar_y}" stroke="#636e72" stroke-width="1"/>'
            )

        svg_parts.append('</svg>')
        return ''.join(svg_parts)

    def _generate_ascii_timeline(self, schedule: list[str]) -> str:
        """Generate ASCII timeline visualization."""
        blocks = ['░'] * 48  # 30-min blocks for 24 hours

        for time_range in schedule:
            match = re.match(r"(\d{2}):(\d{2})\s*до\s*(\d{2}):(\d{2})", time_range)
            if match:
                start_h, start_m = int(match.group(1)), int(match.group(2))
                end_h, end_m = int(match.group(3)), int(match.group(4))

                start_block = start_h * 2 + (1 if start_m >= 30 else 0)
                end_block = end_h * 2 + (1 if end_m > 30 else 0)

                for i in range(start_block, min(end_block, 48)):
                    blocks[i] = '█'

        # Add hour markers
        header = "00    06    12    18    24"
        timeline = ''.join(blocks)
        return f"{header}\n{timeline}"

    def _calculate_outage_minutes(self, schedule: list[str]) -> int:
        """Calculate total outage minutes."""
        total_minutes = 0

        for time_range in schedule:
            match = re.match(r"(\d{2}):(\d{2})\s*до\s*(\d{2}):(\d{2})", time_range)
            if match:
                start_h, start_m = int(match.group(1)), int(match.group(2))
                end_h, end_m = int(match.group(3)), int(match.group(4))
                total_minutes += (end_h * 60 + end_m) - (start_h * 60 + start_m)

        return total_minutes

    def _calculate_outage_percentage(self, schedule: list[str]) -> float:
        """Calculate total outage percentage of the day."""
        total_minutes = self._calculate_outage_minutes(schedule)
        return round((total_minutes / 1440) * 100, 1)

    def _calculate_outage_hours(self, schedule: list[str]) -> float:
        """Calculate total outage hours."""
        total_minutes = self._calculate_outage_minutes(schedule)
        return round(total_minutes / 60, 1)
