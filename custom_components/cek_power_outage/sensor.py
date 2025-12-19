"""Sensor platform for CEK Power Outage."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
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
    def native_value(self) -> str | datetime | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        key = self.entity_description.key

        if key == "schedule":
            schedule = self.coordinator.data.get("schedule", [])
            return ", ".join(schedule) if schedule else "No outages"

        return self.coordinator.data.get(key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        attrs: dict[str, Any] = {
            "queue": self.coordinator.data.get("queue"),
        }

        if self.entity_description.key == "schedule":
            attrs["time_ranges"] = self.coordinator.data.get("schedule", [])

        return attrs

