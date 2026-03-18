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

"""Climate platform for Systemair integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    PRESET_TO_TIMED_MODE,
    TIMED_MODE_DEFAULTS,
    USER_MODE_TO_PRESET,
)
from .coordinator import SystemairCoordinator, SystemairData

_LOGGER = logging.getLogger(__name__)

# Map internal fan mode values to HA fan mode strings
HA_FAN_MODE_MAP: dict[int, str] = {
    2: "low",
    3: "medium",
    4: "high",
}
HA_FAN_MODE_REVERSE: dict[str, int] = {v: k for k, v in HA_FAN_MODE_MAP.items()}

# Map user modes to HVAC modes
# Auto -> HVACMode.AUTO, Manual -> HVACMode.FAN_ONLY
# Timed modes are shown as the underlying HVAC mode
HVAC_MODES = [HVACMode.AUTO, HVACMode.FAN_ONLY]

# The "none" preset means no timed mode is active (auto or manual)
PRESET_NONE = "none"

# Preset mode names exposed to HA — include "none" so users can deactivate timed modes
PRESET_MODES = [PRESET_NONE] + sorted(PRESET_TO_TIMED_MODE.keys())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Systemair climate entity."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SystemairClimate(coordinator, entry)])


class SystemairClimate(CoordinatorEntity[SystemairCoordinator], ClimateEntity):
    """Representation of a Systemair HVAC unit as a climate entity."""

    _attr_has_entity_name = True
    _attr_name = None  # Use device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 12.0
    _attr_max_temp = 30.0
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = list(HA_FAN_MODE_MAP.values())
    _attr_preset_modes = PRESET_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(
        self, coordinator: SystemairCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }

    @property
    def _data(self) -> SystemairData | None:
        """Return the current data."""
        return self.coordinator.data

    @property
    def current_temperature(self) -> float | None:
        """Return the current supply air temperature."""
        if self._data is None:
            return None
        return self._data.supply_air_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._data is None:
            return None
        return self._data.target_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode.

        user_mode 0 = Auto -> HVACMode.AUTO
        user_mode 1 = Manual -> HVACMode.FAN_ONLY
        user_mode 2-12 = Timed modes -> HVACMode.AUTO (device controls airflow)
        user_mode None = Unknown -> None
        """
        if self._data is None:
            return None
        mode = self._data.user_mode
        if mode is None:
            return None
        if mode == 1:
            return HVACMode.FAN_ONLY
        # Auto (0) and all timed modes (2-12): device manages airflow automatically
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action based on heater/cooler state."""
        if self._data is None:
            return None

        # Check heater state first
        if self._data.heater_active:
            return HVACAction.HEATING
        # For Modbus/SaveConnect, also check analog output > 0
        if self._data.heater_output is not None and self._data.heater_output > 0:
            return HVACAction.HEATING

        # Check cooler state
        if self._data.cooler_active:
            return HVACAction.COOLING
        if self._data.cooler_output is not None and self._data.cooler_output > 0:
            return HVACAction.COOLING

        # Determine if fan is running
        if self._data.saf_speed is not None and self._data.saf_speed == 0:
            return HVACAction.IDLE
        return HVACAction.FAN

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        if self._data is None:
            return None
        return HA_FAN_MODE_MAP.get(self._data.fan_mode)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode.

        Returns the HA preset name if a timed mode is active,
        or "none" if in auto/manual mode.
        """
        if self._data is None:
            return None
        user_mode = self._data.user_mode
        if user_mode is None:
            return None
        preset = USER_MODE_TO_PRESET.get(user_mode)
        return preset if preset is not None else PRESET_NONE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {}
        if self._data is None:
            return attrs

        if self._data.user_mode is not None:
            attrs["user_mode"] = self._data.user_mode_name
            attrs["user_mode_id"] = self._data.user_mode

        if self._data.outdoor_air_temperature is not None:
            attrs["outdoor_temperature"] = self._data.outdoor_air_temperature

        if self._data.extract_air_temperature is not None:
            attrs["extract_temperature"] = self._data.extract_air_temperature

        if self._data.eco_mode is not None:
            attrs["eco_mode"] = self._data.eco_mode

        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.async_set_target_temperature(temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode.

        Setting an HVAC mode also cancels any active timed mode
        by switching to auto or manual.
        """
        if hvac_mode == HVACMode.AUTO:
            await self.coordinator.async_set_mode("auto")
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self.coordinator.async_set_mode("manual")
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        value = HA_FAN_MODE_REVERSE.get(fan_mode)
        if value is None:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return
        await self.coordinator.async_set_fan_mode(value)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode.

        Activates the corresponding timed mode with a default duration,
        or cancels the current timed mode if preset is "none".
        """
        if preset_mode == PRESET_NONE:
            # Cancel timed mode -> return to auto
            await self.coordinator.async_set_mode("auto")
            return

        timed_mode = PRESET_TO_TIMED_MODE.get(preset_mode)
        if timed_mode is None:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return

        duration = TIMED_MODE_DEFAULTS.get(timed_mode)
        if duration is None:
            _LOGGER.error(
                "No default duration for timed mode %s", timed_mode
            )
            return

        await self.coordinator.async_set_timed_mode(timed_mode, duration)
