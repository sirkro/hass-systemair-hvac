# Systemair HVAC integration for Home Assistant
# Based on com.systemair by balmli (https://github.com/balmli/com.systemair)
# Copyright (C) 2026
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Switch platform for Systemair integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SystemairCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Systemair switch entities."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SystemairEcoModeSwitch(coordinator, entry),
        SystemairMoistureTransferSwitch(coordinator, entry),
    ])


class SystemairEcoModeSwitch(CoordinatorEntity[SystemairCoordinator], SwitchEntity):
    """Switch entity for Systemair ECO mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "eco_mode"
    _attr_name = "ECO mode"
    _attr_icon = "mdi:leaf"

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the ECO mode switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_eco_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if ECO mode is on."""
        if self.coordinator.data is None:
            return None
        eco = self.coordinator.data.eco_mode
        return bool(eco) if eco is not None else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on ECO mode."""
        await self.coordinator.async_set_eco_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off ECO mode."""
        await self.coordinator.async_set_eco_mode(False)


class SystemairMoistureTransferSwitch(
    CoordinatorEntity[SystemairCoordinator], SwitchEntity
):
    """Switch entity for Systemair moisture transfer (rotating heat exchangers)."""

    _attr_has_entity_name = True
    _attr_translation_key = "moisture_transfer"
    _attr_name = "Moisture transfer"
    _attr_icon = "mdi:water-sync"

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the moisture transfer switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_moisture_transfer"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }
        # Disable by default — only relevant for units with rotating heat exchangers
        self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        """Return true if moisture transfer is enabled."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.moisture_transfer_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable moisture transfer."""
        await self.coordinator.async_set_moisture_transfer(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable moisture transfer."""
        await self.coordinator.async_set_moisture_transfer(False)
