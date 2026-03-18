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

"""Binary sensor platform for Systemair integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLOUD_ALARMS,
    CLOUD_FUNCTIONS,
    CONN_CLOUD,
    DOMAIN,
    FUNCTION_PARAMS,
    MANUFACTURER,
)
from .coordinator import SystemairCoordinator, SystemairData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SystemairBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Systemair binary sensor."""

    alarm_key: str  # Key in SystemairData.alarms or .functions
    is_function: bool = False  # True for active functions, False for alarms


def _build_heater_cooler_descriptions() -> list[SystemairBinarySensorDescription]:
    """Build heater/cooler active binary sensor descriptions.

    These are separate from the alarm/function descriptions because they
    use dedicated SystemairData fields rather than the alarms/functions dicts.
    """
    return [
        SystemairBinarySensorDescription(
            key="heater_active",
            translation_key="heater_active",
            name="Heater active",
            device_class=BinarySensorDeviceClass.RUNNING,
            alarm_key="__heater_active__",
            is_function=False,
        ),
        SystemairBinarySensorDescription(
            key="cooler_active",
            translation_key="cooler_active",
            name="Cooler active",
            device_class=BinarySensorDeviceClass.RUNNING,
            alarm_key="__cooler_active__",
            is_function=False,
        ),
    ]


def _build_alarm_descriptions_cloud() -> list[SystemairBinarySensorDescription]:
    """Build alarm binary sensor descriptions for Cloud."""
    descriptions = []
    for alarm in CLOUD_ALARMS:
        key = f"alarm_{alarm['id']}"
        descriptions.append(
            SystemairBinarySensorDescription(
                key=key,
                translation_key=key,
                name=f"Alarm: {alarm['description']}",
                device_class=BinarySensorDeviceClass.PROBLEM,
                alarm_key=alarm["id"],
                is_function=False,
            )
        )
    return descriptions


def _build_function_descriptions_cloud() -> list[SystemairBinarySensorDescription]:
    """Build active function binary sensor descriptions for Cloud.

    Now that function active registers (3101-3117) are readable via cloud
    data item IDs, we use the same register-based approach.
    The CLOUD_FUNCTIONS list provides the "register" -> function name mapping.
    """
    # Build a register->description lookup from CLOUD_FUNCTIONS
    reg_to_desc: dict[str, str] = {}
    for func in CLOUD_FUNCTIONS:
        reg = func.get("register")
        if reg:
            reg_to_desc[reg] = func["description"]

    descriptions = []
    for param in FUNCTION_PARAMS:
        desc = reg_to_desc.get(param.short, param.description)
        key = f"function_{param.short.lower()}"
        descriptions.append(
            SystemairBinarySensorDescription(
                key=key,
                translation_key=key,
                name=f"Function: {desc}",
                device_class=BinarySensorDeviceClass.RUNNING,
                alarm_key=param.short,
                is_function=True,
            )
        )
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Systemair binary sensor entities."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]

    descriptions: list[SystemairBinarySensorDescription] = []
    descriptions.extend(_build_alarm_descriptions_cloud())
    descriptions.extend(_build_function_descriptions_cloud())

    # Always add heater/cooler active sensors
    descriptions.extend(_build_heater_cooler_descriptions())

    async_add_entities(
        SystemairBinarySensor(coordinator, entry, desc)
        for desc in descriptions
    )


class SystemairBinarySensor(
    CoordinatorEntity[SystemairCoordinator], BinarySensorEntity
):
    """Representation of a Systemair alarm or function binary sensor."""

    _attr_has_entity_name = True
    entity_description: SystemairBinarySensorDescription

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
        description: SystemairBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }
        # Alarms are disabled by default (noisy); functions and heater/cooler
        # are enabled so users see active state out of the box.
        if not description.is_function and description.alarm_key not in (
            "__heater_active__",
            "__cooler_active__",
        ):
            self._attr_entity_registry_enabled_default = False

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        For cloud connections, heater_active and cooler_active binary sensors
        are unavailable because the underlying Modbus INPUT registers
        (REG_OUTPUT_Y1_DIGITAL, REG_OUTPUT_Y3_DIGITAL) are not exposed
        by the cloud API's ExportDataItems.
        """
        if not super().available:
            return False
        if (
            self.coordinator.connection_type == CONN_CLOUD
            and self.entity_description.key in ("heater_active", "cooler_active")
        ):
            return False
        return True

    @property
    def is_on(self) -> bool | None:
        """Return true if the alarm/function is active."""
        data = self.coordinator.data
        if data is None:
            return None

        key = self.entity_description.alarm_key

        # Special heater/cooler active sensors
        if key == "__heater_active__":
            return data.heater_active
        if key == "__cooler_active__":
            return data.cooler_active

        if self.entity_description.is_function:
            val = data.functions.get(key)
            if val is None:
                return None
            return bool(val)
        else:
            val = data.alarms.get(key)
            if val is None:
                return None
            if isinstance(val, bool):
                return val
            # Alarm level: 0=inactive, 1-3=active with severity
            return val > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes for alarm sensors."""
        attrs: dict[str, Any] = {}
        if self.entity_description.is_function:
            return attrs

        # Skip synthetic heater/cooler keys — they don't live in data.alarms
        key = self.entity_description.alarm_key
        if key in ("__heater_active__", "__cooler_active__"):
            return attrs

        data = self.coordinator.data
        if data is None:
            return attrs

        val = data.alarms.get(key)
        if val is not None and not isinstance(val, bool):
            severity_map = {0: "inactive", 1: "warning", 2: "alarm", 3: "critical"}
            attrs["alarm_level"] = val
            attrs["alarm_severity"] = severity_map.get(val, "unknown")

        return attrs
