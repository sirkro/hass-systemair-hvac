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

"""Number platform for Systemair integration — fan levels & timed mode durations."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONN_CLOUD,
    DOMAIN,
    FAN_LEVEL_REGISTERS,
    MANUFACTURER,
    PARAMETER_MAP,
    TIMED_MODE_DURATION_REGISTERS,
)
from .coordinator import SystemairCoordinator, SystemairData

_LOGGER = logging.getLogger(__name__)

# Unit mapping for timed mode durations
_DURATION_UNIT_MAP: dict[str, str] = {
    "d": UnitOfTime.DAYS,
    "h": UnitOfTime.HOURS,
    "min": UnitOfTime.MINUTES,
}


@dataclass(frozen=True, kw_only=True)
class SystemairFanLevelDescription(NumberEntityDescription):
    """Describes a Systemair per-mode fan level number entity."""

    register_short: str  # e.g. "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF"
    mode_name: str  # e.g. "Crowded"
    air_type: str  # "Supply" or "Extract"


@dataclass(frozen=True, kw_only=True)
class SystemairTimedModeDurationDescription(NumberEntityDescription):
    """Describes a Systemair timed mode duration number entity."""

    register_short: str  # e.g. "REG_USERMODE_AWAY_TIME"
    mode_name: str  # e.g. "Away"


def _build_fan_level_descriptions() -> list[SystemairFanLevelDescription]:
    """Build number entity descriptions for per-mode fan levels."""
    descriptions: list[SystemairFanLevelDescription] = []
    for reg_short, mode_name, air_type in FAN_LEVEL_REGISTERS:
        param = PARAMETER_MAP[reg_short]
        key = reg_short.lower()
        descriptions.append(
            SystemairFanLevelDescription(
                key=key,
                translation_key=key,
                name=f"{mode_name} {air_type} fan level",
                icon="mdi:fan",
                native_min_value=float(param.min_val if param.min_val is not None else 0),
                native_max_value=float(param.max_val if param.max_val is not None else 5),
                native_step=1.0,
                mode=NumberMode.SLIDER,
                register_short=reg_short,
                mode_name=mode_name,
                air_type=air_type,
            )
        )
    return descriptions


def _build_timed_mode_duration_descriptions() -> list[SystemairTimedModeDurationDescription]:
    """Build number entity descriptions for timed mode durations."""
    descriptions: list[SystemairTimedModeDurationDescription] = []
    for reg_short, mode_name, unit_short in TIMED_MODE_DURATION_REGISTERS:
        param = PARAMETER_MAP[reg_short]
        key = reg_short.lower()
        ha_unit = _DURATION_UNIT_MAP.get(unit_short, unit_short)
        descriptions.append(
            SystemairTimedModeDurationDescription(
                key=key,
                translation_key=key,
                name=f"{mode_name} mode duration",
                icon="mdi:timer-cog-outline",
                native_min_value=float(param.min_val if param.min_val is not None else 1),
                native_max_value=float(param.max_val if param.max_val is not None else 365),
                native_step=1.0,
                native_unit_of_measurement=ha_unit,
                mode=NumberMode.BOX,
                register_short=reg_short,
                mode_name=mode_name,
            )
        )
    return descriptions


FAN_LEVEL_DESCRIPTIONS = _build_fan_level_descriptions()
TIMED_MODE_DURATION_DESCRIPTIONS = _build_timed_mode_duration_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Systemair number entities."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    is_cloud = coordinator.connection_type == CONN_CLOUD

    entities: list[NumberEntity] = []

    # Per-mode fan level entities
    for desc in FAN_LEVEL_DESCRIPTIONS:
        entities.append(
            SystemairFanLevelNumber(coordinator, entry, desc, read_only=is_cloud)
        )

    # Timed mode duration entities
    for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
        entities.append(
            SystemairTimedModeDurationNumber(coordinator, entry, desc)
        )

    async_add_entities(entities)


class SystemairFanLevelNumber(
    CoordinatorEntity[SystemairCoordinator], NumberEntity
):
    """Representation of a per-mode fan level setting."""

    _attr_has_entity_name = True
    entity_description: SystemairFanLevelDescription

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
        description: SystemairFanLevelDescription,
        *,
        read_only: bool = False,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._read_only = read_only
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }
        # Disable by default — most users won't need these
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        """Return the current fan level value."""
        data = self.coordinator.data
        if data is None:
            return None
        val = data.fan_levels.get(self.entity_description.register_short)
        if val is None:
            return None
        return float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set the fan level value."""
        if self._read_only:
            raise HomeAssistantError(
                f"Fan level {self.entity_description.register_short} "
                f"is read-only on cloud connections"
            )
        await self.coordinator.async_set_fan_level(
            self.entity_description.register_short,
            int(value),
        )


class SystemairTimedModeDurationNumber(
    CoordinatorEntity[SystemairCoordinator], NumberEntity
):
    """Representation of a timed mode duration setting."""

    _attr_has_entity_name = True
    entity_description: SystemairTimedModeDurationDescription

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
        description: SystemairTimedModeDurationDescription,
    ) -> None:
        """Initialize the timed mode duration entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }
        # Disable by default — users typically configure these once
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        """Return the current duration value."""
        data = self.coordinator.data
        if data is None:
            return None
        val = data.timed_mode_durations.get(self.entity_description.register_short)
        if val is None:
            return None
        return float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set the timed mode duration."""
        await self.coordinator.async_set_timed_mode_duration(
            self.entity_description.register_short,
            int(value),
        )
