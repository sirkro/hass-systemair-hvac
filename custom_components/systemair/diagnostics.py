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

"""Diagnostics support for the Systemair integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_API_URL, CONF_EMAIL, CONF_PASSWORD, CONF_WS_URL, CONN_CLOUD, DOMAIN
from .coordinator import SystemairCoordinator

_LOGGER = logging.getLogger(__name__)

# Keys to redact from config data
TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_API_URL, CONF_WS_URL}

# Keys to redact from raw cloud data (applied recursively)
_CLOUD_REDACT_KEYS = {"serialNumber", "serial_number"}


def _redact_cloud_data(obj: Any) -> Any:
    """Recursively redact sensitive keys from raw cloud API responses."""
    if isinstance(obj, dict):
        return {
            k: ("**REDACTED**" if k in _CLOUD_REDACT_KEYS else _redact_cloud_data(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_cloud_data(item) for item in obj]
    return obj


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: SystemairCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    diag: dict[str, Any] = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "connection_type": coordinator.connection_type,
            "poll_count": coordinator._poll_count,
            "last_update_success": coordinator.last_update_success,
        },
    }

    if data is not None:
        diag["data"] = {
            "target_temperature": data.target_temperature,
            "supply_air_temperature": data.supply_air_temperature,
            "outdoor_air_temperature": data.outdoor_air_temperature,
            "extract_air_temperature": data.extract_air_temperature,
            "overheat_temperature": data.overheat_temperature,
            "humidity": data.humidity,
            "co2": data.co2,
            "air_quality": data.air_quality,
            "fan_mode": data.fan_mode,
            "fan_mode_name": data.fan_mode_name,
            "saf_rpm": data.saf_rpm,
            "eaf_rpm": data.eaf_rpm,
            "saf_speed": data.saf_speed,
            "eaf_speed": data.eaf_speed,
            "user_mode": data.user_mode,
            "user_mode_name": data.user_mode_name,
            "eco_mode": data.eco_mode,
            "filter_days_left": data.filter_days_left,
            "remaining_time_seconds": data.remaining_time_seconds,
            "heater_output": data.heater_output,
            "heater_active": data.heater_active,
            "cooler_output": data.cooler_output,
            "cooler_active": data.cooler_active,
            "heat_exchanger_type": data.heat_exchanger_type,
            "heat_exchanger_speed": data.heat_exchanger_speed,
            "moisture_transfer_enabled": data.moisture_transfer_enabled,
            "heater_type": data.heater_type,
            "heater_position": data.heater_position,
            "fan_levels": data.fan_levels,
            "timed_mode_durations": data.timed_mode_durations,
            "alarms": data.alarms,
            "functions": data.functions,
        }
    else:
        diag["data"] = None

    # Collect comprehensive raw cloud data for developer diagnostics
    if coordinator.connection_type == CONN_CLOUD:
        try:
            from .cloud_api import SystemairCloudAPI

            api: SystemairCloudAPI = coordinator.api
            raw_cloud = await api.collect_diagnostics_data()
            diag["cloud_raw_data"] = _redact_cloud_data(raw_cloud)
        except Exception as err:
            _LOGGER.warning("Failed to collect cloud diagnostics data: %s", err)
            diag["cloud_raw_data"] = f"Error: {type(err).__name__}"

    return diag
