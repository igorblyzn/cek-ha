"""Binary sensor platform for CEK Power Outage."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CEKDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CEK Power Outage binary sensor."""
    coordinator: CEKDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CEKOutageActiveSensor(coordinator, entry)])


class CEKOutageActiveSensor(
    CoordinatorEntity[CEKDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating if an outage is currently active."""

    _attr_has_entity_name = True
    _attr_name = "Outage Active"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:flash-off"

    def __init__(
        self,
        coordinator: CEKDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_outage_active"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"CEK Power Outage ({coordinator.queue})",
            "manufacturer": "CEK",
            "model": f"Queue {coordinator.queue}",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if an outage is currently active."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("is_active", False)

    @property
    def extra_state_attributes(self) -> dict[str, str | list[str] | None]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        return {
            "queue": self.coordinator.data.get("queue"),
            "schedule": self.coordinator.data.get("schedule", []),
            "date": self.coordinator.data.get("date"),
        }

