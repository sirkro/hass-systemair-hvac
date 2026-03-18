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

"""Select platform for Systemair integration."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODES_SETTABLE
from .coordinator import SystemairCoordinator

_LOGGER = logging.getLogger(__name__)

# Selectable options: persistent modes only (Auto, Manual)
USER_MODE_OPTIONS = list(MODES_SETTABLE.values())  # ["Auto", "Manual"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Systemair select entities."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SystemairUserModeSelect(coordinator, entry)])


class SystemairUserModeSelect(CoordinatorEntity[SystemairCoordinator], SelectEntity):
    """Select entity for Systemair user mode (Auto/Manual)."""

    _attr_has_entity_name = True
    _attr_translation_key = "user_mode_select"
    _attr_name = "User mode"
    _attr_icon = "mdi:cog"
    _attr_options = USER_MODE_OPTIONS

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the user mode select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_user_mode_select"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }

    @property
    def current_option(self) -> str | None:
        """Return the currently active user mode."""
        if self.coordinator.data is None:
            return None
        mode = self.coordinator.data.user_mode
        if mode is None:
            return None
        # For Auto/Manual, return the settable option directly
        if mode in MODES_SETTABLE:
            return MODES_SETTABLE[mode]
        # For timed modes (Away, Crowded, etc.), the base mode is Auto
        # since timed modes are temporary overrides that revert to Auto
        return MODES_SETTABLE[0]  # "Auto"

    async def async_select_option(self, option: str) -> None:
        """Set the user mode."""
        await self.coordinator.async_set_mode(option.lower())
