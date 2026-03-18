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

"""DataUpdateCoordinator for Systemair integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .cloud_api import AuthenticationError
from .const import (
    ALARM_PARAMS,
    CLOUD_ALARMS,
    CONFIG_PARAMS,
    CONN_CLOUD,
    DEFAULT_POLL_INTERVAL,
    DIAGNOSTIC_PARAMS,
    DOMAIN,
    FAN_LEVEL_REGISTERS,
    FAN_MODES,
    FUNCTION_PARAMS,
    HEAT_EXCHANGER_TYPES,
    HEATER_POSITIONS,
    HEATER_TYPES,
    MODES,
    OPERATION_PARAMS,
    PARAMETER_MAP,
    SENSOR_PARAMS,
    TIMED_MODE_DURATION_REGISTERS,
)

_LOGGER = logging.getLogger(__name__)

# Event types fired on state changes
EVENT_ALARM_CHANGED = f"{DOMAIN}_alarm_changed"
EVENT_FUNCTION_CHANGED = f"{DOMAIN}_function_changed"

# Set of alarm state property names from CLOUD_ALARMS (e.g. "alarm_co2_state")
_CLOUD_ALARM_IDS: set[str] = {alarm["id"] for alarm in CLOUD_ALARMS}


def _apply_filter_expiration(
    value: Any, op_data: dict[str, Any]
) -> None:
    """Convert a filter expiration value to register-compatible format.

    The cloud API's filterExpiration may be:
      - An ISO date string (e.g. "2026-06-15")
      - A number of days remaining
      - A number of seconds remaining

    We convert to REG_FILTER_REMAINING_TIME_L / _H (seconds split
    into low/high 16-bit words) so _parse_modbus_data can handle it.
    """
    if value is None:
        return

    if isinstance(value, str):
        # Try to parse as ISO date/datetime
        try:
            exp_date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # fromisoformat may return a date (not datetime) on Python 3.11+
            # for bare date strings like "2026-06-15". Promote to datetime.
            if not isinstance(exp_date, datetime):
                from datetime import date as _date_type
                if isinstance(exp_date, _date_type):
                    exp_date = datetime(exp_date.year, exp_date.month, exp_date.day)
            now = datetime.now(exp_date.tzinfo) if exp_date.tzinfo else datetime.now()
            remaining = exp_date - now
            total_seconds = max(0, int(remaining.total_seconds()))
        except (ValueError, TypeError):
            # Not a date — try as numeric string
            try:
                total_seconds = int(float(value)) * 86400  # assume days
            except (ValueError, TypeError):
                return
    elif isinstance(value, (int, float)):
        # If value > 1000, assume seconds; otherwise days
        if value > 1000:
            total_seconds = max(0, int(value))
        else:
            total_seconds = max(0, int(value) * 86400)
    else:
        return

    op_data["REG_FILTER_REMAINING_TIME_L"] = total_seconds & 0xFFFF
    op_data["REG_FILTER_REMAINING_TIME_H"] = (total_seconds >> 16) & 0xFFFF


class SystemairData:
    """Parsed data from a Systemair unit."""

    def __init__(self) -> None:
        """Initialize the data container."""
        # Climate
        self.target_temperature: float | None = None
        self.supply_air_temperature: float | None = None
        self.outdoor_air_temperature: float | None = None
        self.extract_air_temperature: float | None = None
        self.overheat_temperature: float | None = None

        # Humidity
        self.humidity: float | None = None

        # CO2
        self.co2: int | None = None

        # Air quality (cloud-only, from WS/GetDeviceStatus)
        self.air_quality: int | None = None

        # Fan
        self.fan_mode: int | None = None  # raw value (1-5)
        self.fan_mode_name: str | None = None
        self.saf_rpm: float | None = None
        self.eaf_rpm: float | None = None
        self.saf_speed: float | None = None  # percentage
        self.eaf_speed: float | None = None  # percentage

        # Mode
        self.user_mode: int | None = None  # raw value (0-12)
        self.user_mode_name: str | None = None

        # ECO mode
        self.eco_mode: bool | None = None

        # Filter
        self.filter_days_left: int | None = None

        # Heater/cooler output
        self.heater_output: float | None = None  # 0-100%
        self.heater_active: bool | None = None
        self.cooler_output: float | None = None  # 0-100%
        self.cooler_active: bool | None = None

        # Timed mode remaining time (seconds)
        self.remaining_time_seconds: int | None = None

        # Diagnostic / configuration
        self.heat_exchanger_type: str | None = None   # "Rotating" or "Plate"
        self.heat_exchanger_speed: int | None = None   # 0-100%
        self.moisture_transfer_enabled: bool | None = None
        self.heater_type: str | None = None            # "None", "Electrical", "Water", "Change Over"
        self.heater_position: str | None = None        # "Supply" or "Extract"

        # Per-mode fan levels (register_short -> level value)
        self.fan_levels: dict[str, int] = {}

        # Timed mode durations (register_short -> value in mode's native unit)
        self.timed_mode_durations: dict[str, int] = {}

        # Alarms (short_name -> active bool or alarm level)
        self.alarms: dict[str, Any] = {}

        # Active functions (short_name -> active bool)
        self.functions: dict[str, Any] = {}

        # Connection type used
        self.connection_type: str = ""


class SystemairCoordinator(DataUpdateCoordinator[SystemairData]):
    """Coordinator to manage polling Systemair devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection_type: str,
        api: Any,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.connection_type = connection_type
        self.api = api
        self._poll_count = 0

        # WebSocket push data (updated by _on_ws_message callback)
        self._ws_data: dict[str, Any] = {}

    async def _async_update_data(self) -> SystemairData:
        """Fetch data from the Systemair unit."""
        try:
            if self.connection_type == CONN_CLOUD:
                new_data = await self._update_cloud()
            else:
                raise UpdateFailed(f"Unknown connection type: {self.connection_type}")
        except UpdateFailed:
            raise
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            # Check if the root cause is an authentication error
            if isinstance(err, AuthenticationError) or isinstance(
                err.__cause__, AuthenticationError
            ):
                raise ConfigEntryAuthFailed(
                    f"Authentication failed: {err}"
                ) from err
            raise UpdateFailed(f"Error communicating with Systemair: {err}") from err

        # Fire events on alarm/function state changes (Feature 3)
        self._fire_state_change_events(new_data)

        return new_data

    @staticmethod
    def _safe_round(value: Any, ndigits: int = 1) -> float | None:
        """Round a value safely, returning None for non-numeric inputs."""
        if value is None:
            return None
        try:
            return round(float(value), ndigits)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        """Convert to int safely, returning None for non-numeric inputs."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_modbus_data(self, raw: dict[str, Any], data: SystemairData) -> None:
        """Parse Modbus/SaveConnect register data into SystemairData."""
        _sr = self._safe_round
        _si = self._safe_int

        # Temperature setpoint
        if "REG_TC_SP" in raw:
            val = _sr(raw["REG_TC_SP"], 1)
            if val is not None:
                data.target_temperature = val

        # Temperature sensors
        if "REG_SENSOR_SAT" in raw:
            val = _sr(raw["REG_SENSOR_SAT"], 1)
            if val is not None:
                data.supply_air_temperature = val
        if "REG_SENSOR_OAT" in raw:
            val = _sr(raw["REG_SENSOR_OAT"], 1)
            if val is not None:
                data.outdoor_air_temperature = val
        if "REG_SENSOR_PDM_EAT_VALUE" in raw:
            val = _sr(raw["REG_SENSOR_PDM_EAT_VALUE"], 1)
            if val is not None:
                data.extract_air_temperature = val
        if "REG_SENSOR_OHT" in raw:
            val = _sr(raw["REG_SENSOR_OHT"], 1)
            if val is not None:
                data.overheat_temperature = val

        # Humidity
        if "REG_SENSOR_RHS_PDM" in raw:
            val = _sr(raw["REG_SENSOR_RHS_PDM"], 1)
            if val is not None:
                data.humidity = val

        # Fan mode
        if "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF" in raw:
            fan_val = _si(raw["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"])
            if fan_val is not None:
                data.fan_mode = fan_val
                data.fan_mode_name = FAN_MODES.get(fan_val, str(fan_val))

        # Fan RPM and speed
        if "REG_SENSOR_RPM_SAF" in raw:
            data.saf_rpm = raw["REG_SENSOR_RPM_SAF"]
        if "REG_SENSOR_RPM_EAF" in raw:
            data.eaf_rpm = raw["REG_SENSOR_RPM_EAF"]
        if "REG_OUTPUT_SAF" in raw:
            data.saf_speed = raw["REG_OUTPUT_SAF"]
        if "REG_OUTPUT_EAF" in raw:
            data.eaf_speed = raw["REG_OUTPUT_EAF"]

        # User mode
        if "REG_USERMODE_MODE" in raw:
            mode_val = _si(raw["REG_USERMODE_MODE"])
            if mode_val is not None:
                data.user_mode = mode_val
                data.user_mode_name = MODES.get(mode_val, str(mode_val))

        # ECO mode
        if "REG_ECO_MODE_ON_OFF" in raw:
            data.eco_mode = bool(raw["REG_ECO_MODE_ON_OFF"])

        # CO2 (cloud-only synthetic key from GetDeviceStatus / WebSocket)
        if "_CO2" in raw:
            data.co2 = raw["_CO2"]

        # Air quality (cloud-only synthetic key from GetDeviceStatus / WebSocket)
        if "_AIR_QUALITY" in raw:
            data.air_quality = raw["_AIR_QUALITY"]

        # Filter time
        filter_l = raw.get("REG_FILTER_REMAINING_TIME_L")
        filter_h = raw.get("REG_FILTER_REMAINING_TIME_H")
        if filter_l is not None and filter_h is not None:
            fl = _si(filter_l)
            fh = _si(filter_h)
            if fl is not None and fh is not None:
                total_seconds = fl + fh * 65536
                data.filter_days_left = max(0, total_seconds // 86400)

        # Heater output
        if "REG_OUTPUT_Y1_ANALOG" in raw:
            val = _sr(raw["REG_OUTPUT_Y1_ANALOG"], 1)
            if val is not None:
                data.heater_output = val
        if "REG_OUTPUT_Y1_DIGITAL" in raw:
            data.heater_active = bool(raw["REG_OUTPUT_Y1_DIGITAL"])

        # Cooler output
        if "REG_OUTPUT_Y3_ANALOG" in raw:
            val = _sr(raw["REG_OUTPUT_Y3_ANALOG"], 1)
            if val is not None:
                data.cooler_output = val
        if "REG_OUTPUT_Y3_DIGITAL" in raw:
            data.cooler_active = bool(raw["REG_OUTPUT_Y3_DIGITAL"])

        # Remaining time for timed modes
        time_l = raw.get("REG_USERMODE_REMAINING_TIME_L")
        time_h = raw.get("REG_USERMODE_REMAINING_TIME_H")
        if time_l is not None and time_h is not None:
            tl = _si(time_l)
            th = _si(time_h)
            if tl is not None and th is not None:
                data.remaining_time_seconds = tl + th * 65536

        # Per-mode fan levels
        for reg_short, _, _ in FAN_LEVEL_REGISTERS:
            if reg_short in raw:
                val = _si(raw[reg_short])
                if val is not None:
                    data.fan_levels[reg_short] = val

        # Timed mode durations
        for reg_short, _, _ in TIMED_MODE_DURATION_REGISTERS:
            if reg_short in raw:
                val = _si(raw[reg_short])
                if val is not None:
                    data.timed_mode_durations[reg_short] = val

        # Alarms
        for param in ALARM_PARAMS:
            if param.short in raw:
                val = raw[param.short]
                if param.is_boolean:
                    data.alarms[param.short] = bool(val)
                else:
                    data.alarms[param.short] = val

        # Cloud alarm state properties (from WS/device status)
        for alarm_id in _CLOUD_ALARM_IDS:
            key = f"_ALARM_{alarm_id}"
            if key in raw:
                data.alarms[alarm_id] = raw[key]

        # Functions
        for param in FUNCTION_PARAMS:
            if param.short in raw:
                data.functions[param.short] = bool(raw[param.short])

        # Diagnostic / configuration
        if "REG_HEAT_EXCHANGER_TYPE" in raw:
            val = _si(raw["REG_HEAT_EXCHANGER_TYPE"])
            if val is not None:
                data.heat_exchanger_type = HEAT_EXCHANGER_TYPES.get(
                    val, str(raw["REG_HEAT_EXCHANGER_TYPE"])
                )
        if "REG_HEAT_EXCHANGER_SPEED" in raw:
            val = _si(raw["REG_HEAT_EXCHANGER_SPEED"])
            if val is not None:
                data.heat_exchanger_speed = val
        if "REG_MOISTURE_TRANSFER_ON_OFF" in raw:
            data.moisture_transfer_enabled = bool(raw["REG_MOISTURE_TRANSFER_ON_OFF"])
        if "REG_HEATER_TYPE" in raw:
            val = _si(raw["REG_HEATER_TYPE"])
            if val is not None:
                data.heater_type = HEATER_TYPES.get(
                    val, str(raw["REG_HEATER_TYPE"])
                )
        if "REG_HEATER_POSITION" in raw:
            val = _si(raw["REG_HEATER_POSITION"])
            if val is not None:
                data.heater_position = HEATER_POSITIONS.get(
                    val, str(raw["REG_HEATER_POSITION"])
                )

    async def _update_cloud(self) -> SystemairData:
        """Update data via Cloud GraphQL API.

        The cloud API uses the same register-based interface as Modbus
        and SaveConnect.  HOLDING registers are mapped via ExportDataItems,
        and key INPUT registers (sensors, fan RPM/speed) are mapped via
        CLOUD_SENSOR_DATA_ITEMS (discovered by exhaustive ID scan).

        We also:
          1. Call GetDeviceStatus EVERY poll for quick sensor overview
          2. Process WebSocket DEVICE_STATUS_UPDATE events for real-time
             updates between polls
          3. Read SENSOR_PARAMS every 3rd poll for precise sensor values
        """
        from .cloud_api import SystemairCloudAPI

        api: SystemairCloudAPI = self.api
        data = SystemairData()
        data.connection_type = CONN_CLOUD
        self._poll_count += 1

        # Carry forward previous data for fields not fetched this cycle
        prev = self.data
        if prev is not None:
            data.alarms = dict(prev.alarms)
            data.functions = dict(prev.functions)
            data.fan_levels = dict(prev.fan_levels)
            data.timed_mode_durations = dict(prev.timed_mode_durations)

        # Read operation parameters via the register-based interface
        # (now includes sensor INPUT registers via CLOUD_SENSOR_DATA_ITEMS:
        #  RPM, fan speed %, heater/cooler output)
        op_data = await api.read_params(OPERATION_PARAMS)

        # Read sensor parameters every 3rd poll (temperature, humidity)
        # Also read on first poll (prev is None) to avoid blank values
        if prev is None or self._poll_count % 3 == 0:
            sensor_data = await api.read_params(SENSOR_PARAMS)
            op_data.update(sensor_data)
        elif prev is not None:
            # Carry forward sensor values from previous poll
            data.supply_air_temperature = prev.supply_air_temperature
            data.outdoor_air_temperature = prev.outdoor_air_temperature
            data.extract_air_temperature = prev.extract_air_temperature
            data.overheat_temperature = prev.overheat_temperature
            data.humidity = prev.humidity

        # Call GetDeviceStatus EVERY poll — provides quick sensor overview
        # and fields not available via registers (CO2, filter expiration).
        # Register-based values from read_params take precedence since they
        # are more precise (raw register values vs pre-scaled).
        try:
            status = await api.get_device_status()
            self._apply_device_status(status, op_data)
        except (ConfigEntryAuthFailed, AuthenticationError):
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug("GetDeviceStatus failed, using cached sensor data")
            if prev is not None:
                self._carry_forward_sensors(prev, data)

        # Apply any WebSocket data that was received between polls
        if self._ws_data:
            self._apply_ws_status(self._ws_data, op_data)
            self._ws_data = {}  # Clear after consumption

        # Read alarms periodically — cloud uses GetActiveAlarms
        # Also read on first poll (prev is None) for immediate visibility
        if prev is None or self._poll_count % 15 == 0:
            try:
                alarms = await api.get_active_alarms()
                for alarm in alarms:
                    title = alarm.get("title", "unknown")
                    data.alarms[title] = True
            except (ConfigEntryAuthFailed, AuthenticationError):
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.debug("GetActiveAlarms failed")

        # Read function active registers every 2nd poll
        # (via CLOUD_SENSOR_DATA_ITEMS data item IDs 102-118)
        # Also read on first poll (prev is None)
        if prev is None or self._poll_count % 2 == 0:
            try:
                func_data = await api.read_params(FUNCTION_PARAMS)
                op_data.update(func_data)
            except (ConfigEntryAuthFailed, AuthenticationError):
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Cloud function params read failed")

        # Read config params (fan levels, etc.) and diagnostics
        # Also read on first poll (prev is None)
        if prev is None or self._poll_count % 30 == 0:
            config_data = await api.read_params(CONFIG_PARAMS)
            op_data.update(config_data)
            try:
                diag_data = await api.read_params(DIAGNOSTIC_PARAMS)
                op_data.update(diag_data)
            except (ConfigEntryAuthFailed, AuthenticationError):
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Cloud diagnostic params read failed")
        elif prev is not None:
            data.filter_days_left = prev.filter_days_left
            data.heat_exchanger_type = prev.heat_exchanger_type
            data.heat_exchanger_speed = prev.heat_exchanger_speed
            data.moisture_transfer_enabled = prev.moisture_transfer_enabled
            data.heater_type = prev.heater_type
            data.heater_position = prev.heater_position

        self._parse_modbus_data(op_data, data)
        return data

    @staticmethod
    def _apply_device_status(
        status: dict[str, Any], op_data: dict[str, Any]
    ) -> None:
        """Map GetDeviceStatus fields to register-compatible keys.

        GetDeviceStatus returns already-scaled human-readable values.
        We inject them as synthetic register keys that _parse_modbus_data
        understands, but ONLY if the key isn't already populated from
        register-based reads (which are more precise).

        Known fields from GetDeviceStatus:
          - temperature: supply air temperature (already scaled, e.g. 16.3)
          - airflow: fan speed level (1-5)
          - filterExpiration: ISO date string or days remaining
          - humidity: relative humidity (if enhanced query supported)
          - userMode: active user mode (0-12, if enhanced query supported)
          - co2: CO2 level (if enhanced query supported)
        """
        # Supply air temperature — only if not already from register read
        if "temperature" in status and status["temperature"] is not None:
            if "REG_SENSOR_SAT" not in op_data:
                op_data["REG_SENSOR_SAT"] = status["temperature"]

        # User mode (0=Auto, 1=Manual, etc.) — only if not already set
        if "userMode" in status and status["userMode"] is not None:
            if "REG_USERMODE_MODE" not in op_data:
                op_data["REG_USERMODE_MODE"] = int(status["userMode"])

        # Humidity — only if not already from register read
        if "humidity" in status and status["humidity"] is not None:
            if "REG_SENSOR_RHS_PDM" not in op_data:
                op_data["REG_SENSOR_RHS_PDM"] = status["humidity"]

        # CO2 — always set (no register-based source)
        if "co2" in status and status["co2"] is not None:
            op_data["_CO2"] = int(status["co2"])

        # Air quality — always set (no register-based source)
        if "airQuality" in status and status["airQuality"] is not None:
            op_data["_AIR_QUALITY"] = int(status["airQuality"])

        # Filter expiration — always set (no register-based source for cloud)
        if "filterExpiration" in status and status["filterExpiration"] is not None:
            _apply_filter_expiration(status["filterExpiration"], op_data)

    @staticmethod
    def _apply_ws_status(
        ws_data: dict[str, Any], op_data: dict[str, Any]
    ) -> None:
        """Map WebSocket DEVICE_STATUS_UPDATE properties to register keys.

        WebSocket push events provide richer data than GetDeviceStatus:
          - temperature, airflow, humidity, co2, userMode
          - temperatures.oat, temperatures.sat, temperatures.setpoint
          - alarm_*_state properties (e.g. "alarm_co2_state": "inactive")

        Values from WS are already-scaled (human-readable).
        """
        props = ws_data.get("properties", ws_data)

        # Supply air temperature
        if "temperature" in props and props["temperature"] is not None:
            op_data["REG_SENSOR_SAT"] = props["temperature"]

        # Nested temperatures object
        temps = props.get("temperatures", {})
        if temps:
            if "sat" in temps and temps["sat"] is not None:
                op_data["REG_SENSOR_SAT"] = temps["sat"]
            if "oat" in temps and temps["oat"] is not None:
                op_data["REG_SENSOR_OAT"] = temps["oat"]
            if "setpoint" in temps and temps["setpoint"] is not None:
                # setpoint from WS is already scaled (e.g. 18.0)
                op_data["REG_TC_SP"] = temps["setpoint"]

        # User mode
        if "userMode" in props and props["userMode"] is not None:
            op_data["REG_USERMODE_MODE"] = int(props["userMode"])

        # Humidity
        if "humidity" in props and props["humidity"] is not None:
            op_data["REG_SENSOR_RHS_PDM"] = props["humidity"]

        # CO2
        if "co2" in props and props["co2"] is not None:
            op_data["_CO2"] = int(props["co2"])

        # Air quality
        if "airQuality" in props and props["airQuality"] is not None:
            op_data["_AIR_QUALITY"] = int(props["airQuality"])

        # Airflow level
        if "airflow" in props and props["airflow"] is not None:
            op_data["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"] = int(
                props["airflow"]
            )

        # Alarm state properties (e.g. "alarm_co2_state": "inactive"/"active")
        for alarm_id in _CLOUD_ALARM_IDS:
            if alarm_id in props:
                val = props[alarm_id]
                if isinstance(val, bool):
                    op_data[f"_ALARM_{alarm_id}"] = val
                elif isinstance(val, str):
                    op_data[f"_ALARM_{alarm_id}"] = val.lower() not in (
                        "inactive", "0", "false", ""
                    )
                else:
                    op_data[f"_ALARM_{alarm_id}"] = bool(val)

    @staticmethod
    def _carry_forward_sensors(
        prev: SystemairData, data: SystemairData
    ) -> None:
        """Carry forward sensor values from the previous poll cycle."""
        data.supply_air_temperature = prev.supply_air_temperature
        data.outdoor_air_temperature = prev.outdoor_air_temperature
        data.extract_air_temperature = prev.extract_air_temperature
        data.overheat_temperature = prev.overheat_temperature
        data.humidity = prev.humidity
        data.co2 = prev.co2
        data.air_quality = prev.air_quality
        data.saf_rpm = prev.saf_rpm
        data.eaf_rpm = prev.eaf_rpm
        data.saf_speed = prev.saf_speed
        data.eaf_speed = prev.eaf_speed

    # ──────────────────────────────────────────────
    # Cloud WebSocket management
    # ──────────────────────────────────────────────

    async def async_start_cloud_websocket(self) -> None:
        """Start the cloud WebSocket listener for push events.

        Call this after the coordinator is set up for cloud connections.
        The WebSocket provides real-time DEVICE_STATUS_UPDATE events with
        richer data than polling (humidity, OAT, userMode, etc.).
        """
        from .cloud_api import SystemairCloudAPI

        api: SystemairCloudAPI = self.api

        try:
            ws = await api.connect_websocket(callback=self._on_ws_message)
            if ws:
                _LOGGER.info("Cloud WebSocket connected for real-time updates")
            else:
                _LOGGER.debug("Cloud WebSocket connection returned None")
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Cloud WebSocket connection failed", exc_info=True)

    async def _on_ws_message(self, message: dict[str, Any]) -> None:
        """Handle incoming WebSocket message.

        Stores the latest DEVICE_STATUS_UPDATE data for use in the
        next poll cycle. Also triggers a coordinator refresh for
        immediate UI updates.
        """
        action = message.get("action")
        if action == "DEVICE_STATUS_UPDATE":
            self._ws_data = message
            _LOGGER.debug(
                "WebSocket DEVICE_STATUS_UPDATE received: %s",
                {k: v for k, v in message.get("properties", {}).items()
                 if k != "versions"},
            )
            # Trigger an immediate coordinator refresh so entities update
            await self.async_request_refresh()
        else:
            _LOGGER.debug("WebSocket message: action=%s", action)

    # ──────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────

    async def async_set_target_temperature(self, temperature: float) -> None:
        """Set the target temperature."""
        param = PARAMETER_MAP["REG_TC_SP"]
        await self.api.write_param(param, temperature)
        await self.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: int) -> None:
        """Set the fan mode (2=Low, 3=Normal, 4=High)."""
        param = PARAMETER_MAP["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"]
        await self.api.write_param(param, fan_mode)
        await self.async_request_refresh()

    async def async_set_mode(self, mode: str) -> None:
        """Set the user mode (auto/manual)."""
        mode_lower = mode.lower()
        code = {
            "auto": 1,
            "manual": 2,
        }.get(mode_lower)
        if code is None:
            _LOGGER.error("Unknown mode: %s", mode)
            return

        param = PARAMETER_MAP["REG_USERMODE_HMI_CHANGE_REQUEST"]
        await self.api.write_param(param, code)
        await self.async_request_refresh()

    async def async_set_eco_mode(self, enabled: bool) -> None:
        """Set ECO mode on/off."""
        param = PARAMETER_MAP["REG_ECO_MODE_ON_OFF"]
        await self.api.write_param(param, enabled)
        await self.async_request_refresh()

    async def async_set_moisture_transfer(self, enabled: bool) -> None:
        """Set moisture transfer on/off (rotating heat exchangers only)."""
        param = PARAMETER_MAP["REG_MOISTURE_TRANSFER_ON_OFF"]
        await self.api.write_param(param, enabled)
        await self.async_request_refresh()

    async def async_set_timed_mode(
        self, mode: str, period: int
    ) -> None:
        """Set a timed user mode (away, crowded, fireplace, holiday, refresh).

        Args:
            mode: One of "away", "crowded", "fireplace", "holiday", "refresh".
            period: Duration in the mode's native unit (hours/minutes/days).
        """
        mode_config = {
            "away": {"code": 6, "time_reg": "REG_USERMODE_AWAY_TIME"},
            "crowded": {"code": 3, "time_reg": "REG_USERMODE_CROWDED_TIME"},
            "fireplace": {"code": 5, "time_reg": "REG_USERMODE_FIREPLACE_TIME"},
            "holiday": {"code": 7, "time_reg": "REG_USERMODE_HOLIDAY_TIME"},
            "refresh": {"code": 4, "time_reg": "REG_USERMODE_REFRESH_TIME"},
        }

        config = mode_config.get(mode.lower())
        if config is None:
            _LOGGER.error("Unknown timed mode: %s", mode)
            return

        time_param = PARAMETER_MAP[config["time_reg"]]
        mode_param = PARAMETER_MAP["REG_USERMODE_HMI_CHANGE_REQUEST"]

        # Batch write: set duration then activate mode
        await self.api.write_params(
            [time_param, mode_param],
            [period, config["code"]],
        )
        await self.async_request_refresh()

    async def async_set_timed_mode_duration(
        self, register_short: str, value: int
    ) -> None:
        """Set a timed mode duration register.

        Args:
            register_short: The register short name (e.g. REG_USERMODE_AWAY_TIME).
            value: Duration in the mode's native unit (hours/minutes/days).
        """
        if register_short not in PARAMETER_MAP:
            _LOGGER.error("Unknown duration register: %s", register_short)
            return

        param = PARAMETER_MAP[register_short]
        if param.min_val is not None and value < param.min_val:
            _LOGGER.warning(
                "Duration %d below minimum %d for %s",
                value, param.min_val, register_short,
            )
            value = param.min_val
        if param.max_val is not None and value > param.max_val:
            _LOGGER.warning(
                "Duration %d above maximum %d for %s",
                value, param.max_val, register_short,
            )
            value = param.max_val

        await self.api.write_param(param, value)
        await self.async_request_refresh()

    async def async_set_fan_level(
        self, register_short: str, level: int
    ) -> None:
        """Set a per-mode fan level register.

        Args:
            register_short: The register short name (e.g. REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF).
            level: Fan level value (typically 0-5).
        """
        if register_short not in PARAMETER_MAP:
            _LOGGER.error("Unknown fan level register: %s", register_short)
            return

        param = PARAMETER_MAP[register_short]
        if param.min_val is not None and level < param.min_val:
            _LOGGER.warning(
                "Fan level %d below minimum %d for %s",
                level, param.min_val, register_short,
            )
            return
        if param.max_val is not None and level > param.max_val:
            _LOGGER.warning(
                "Fan level %d above maximum %d for %s",
                level, param.max_val, register_short,
            )
            return

        await self.api.write_param(param, level)
        await self.async_request_refresh()

    # ──────────────────────────────────────────────
    # Event firing for alarm/function state changes
    # ──────────────────────────────────────────────

    def _fire_state_change_events(self, new_data: SystemairData) -> None:
        """Compare new data with previous and fire events on changes."""
        prev = self.data
        if prev is None:
            return

        # Check alarm changes
        for key, new_val in new_data.alarms.items():
            old_val = prev.alarms.get(key)
            if old_val is not None and old_val != new_val:
                # Normalize to bool for event
                if isinstance(new_val, bool):
                    is_active = new_val
                elif isinstance(new_val, (int, float)):
                    is_active = new_val > 0
                else:
                    # String or other type — treat non-empty/truthy as active
                    is_active = bool(new_val)

                self.hass.bus.async_fire(
                    EVENT_ALARM_CHANGED,
                    {
                        "alarm_id": key,
                        "old_state": old_val,
                        "new_state": new_val,
                        "is_active": is_active,
                        "connection_type": new_data.connection_type,
                    },
                )
                _LOGGER.info(
                    "Alarm state changed: %s %s -> %s",
                    key, old_val, new_val,
                )

        # Check function changes
        for key, new_val in new_data.functions.items():
            old_val = prev.functions.get(key)
            if old_val is not None and old_val != new_val:
                self.hass.bus.async_fire(
                    EVENT_FUNCTION_CHANGED,
                    {
                        "function_id": key,
                        "old_state": old_val,
                        "new_state": new_val,
                        "is_active": bool(new_val),
                        "connection_type": new_data.connection_type,
                    },
                )
                _LOGGER.info(
                    "Function state changed: %s %s -> %s",
                    key, old_val, new_val,
                )
