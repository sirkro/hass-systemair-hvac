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

"""Sensor platform for Systemair integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    EntityCategory,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CLOUD_UNAVAILABLE_SENSORS, CONN_CLOUD, DOMAIN, MANUFACTURER
from .coordinator import SystemairCoordinator, SystemairData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SystemairSensorDescription(SensorEntityDescription):
    """Describes a Systemair sensor."""

    value_fn: Callable[[SystemairData], float | int | str | None]


SENSOR_DESCRIPTIONS: list[SystemairSensorDescription] = [
    SystemairSensorDescription(
        key="supply_air_temperature",
        translation_key="supply_air_temperature",
        name="Supply air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.supply_air_temperature,
    ),
    SystemairSensorDescription(
        key="outdoor_air_temperature",
        translation_key="outdoor_air_temperature",
        name="Outdoor air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.outdoor_air_temperature,
    ),
    SystemairSensorDescription(
        key="extract_air_temperature",
        translation_key="extract_air_temperature",
        name="Extract air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.extract_air_temperature,
    ),
    SystemairSensorDescription(
        key="overheat_temperature",
        translation_key="overheat_temperature",
        name="Overheat temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overheat_temperature,
    ),
    SystemairSensorDescription(
        key="humidity",
        translation_key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.humidity,
    ),
    SystemairSensorDescription(
        key="co2",
        translation_key="co2",
        name="CO2",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.co2,
    ),
    SystemairSensorDescription(
        key="saf_rpm",
        translation_key="saf_rpm",
        name="Supply air fan RPM",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        value_fn=lambda data: data.saf_rpm,
    ),
    SystemairSensorDescription(
        key="eaf_rpm",
        translation_key="eaf_rpm",
        name="Extract air fan RPM",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        value_fn=lambda data: data.eaf_rpm,
    ),
    SystemairSensorDescription(
        key="saf_speed",
        translation_key="saf_speed",
        name="Supply air fan speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        value_fn=lambda data: data.saf_speed,
    ),
    SystemairSensorDescription(
        key="eaf_speed",
        translation_key="eaf_speed",
        name="Extract air fan speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        value_fn=lambda data: data.eaf_speed,
    ),
    SystemairSensorDescription(
        key="filter_days_left",
        translation_key="filter_days_left",
        name="Filter days remaining",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.filter_days_left,
    ),
    SystemairSensorDescription(
        key="user_mode",
        translation_key="user_mode",
        name="User mode",
        icon="mdi:cog",
        value_fn=lambda data: data.user_mode_name,
    ),
    SystemairSensorDescription(
        key="fan_mode",
        translation_key="fan_mode_sensor",
        name="Fan mode",
        icon="mdi:fan",
        value_fn=lambda data: data.fan_mode_name,
    ),
    SystemairSensorDescription(
        key="heater_output",
        translation_key="heater_output",
        name="Heater output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radiator",
        value_fn=lambda data: data.heater_output,
    ),
    SystemairSensorDescription(
        key="cooler_output",
        translation_key="cooler_output",
        name="Cooler output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake",
        value_fn=lambda data: data.cooler_output,
    ),
    SystemairSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        name="Timed mode remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda data: (
            round(data.remaining_time_seconds / 60)
            if data.remaining_time_seconds is not None
            and (data.remaining_time_seconds > 0 or data.user_mode not in (0, 1))
            else None
        ),
    ),
    SystemairSensorDescription(
        key="air_quality",
        translation_key="air_quality",
        name="Air quality",
        icon="mdi:air-filter",
        value_fn=lambda data: data.air_quality,
    ),
    SystemairSensorDescription(
        key="heat_exchanger_type",
        translation_key="heat_exchanger_type",
        name="Heat exchanger type",
        icon="mdi:hvac",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heat_exchanger_type,
    ),
    SystemairSensorDescription(
        key="heat_exchanger_speed",
        translation_key="heat_exchanger_speed",
        name="Heat exchanger speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:hvac",
        value_fn=lambda data: data.heat_exchanger_speed,
    ),
    SystemairSensorDescription(
        key="heater_type",
        translation_key="heater_type",
        name="Heater type",
        icon="mdi:radiator",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater_type,
    ),
    SystemairSensorDescription(
        key="heater_position",
        translation_key="heater_position",
        name="Heater position",
        icon="mdi:radiator",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.heater_position,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Systemair sensor entities."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SystemairSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class SystemairSensor(CoordinatorEntity[SystemairCoordinator], SensorEntity):
    """Representation of a Systemair sensor."""

    _attr_has_entity_name = True
    entity_description: SystemairSensorDescription

    def __init__(
        self,
        coordinator: SystemairCoordinator,
        entry: ConfigEntry,
        description: SystemairSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "HVAC",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        For cloud connections, sensors that depend on Modbus INPUT registers
        (RPM, fan speed %, heater/cooler output) are not available because
        the cloud API only exposes HOLDING registers via ExportDataItems.
        """
        if not super().available:
            return False
        if (
            self.coordinator.connection_type == CONN_CLOUD
            and self.entity_description.key in CLOUD_UNAVAILABLE_SENSORS
        ):
            return False
        return True

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
