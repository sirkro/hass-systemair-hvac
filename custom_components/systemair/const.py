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

"""Constants for the Systemair integration."""
from __future__ import annotations

from enum import IntEnum

DOMAIN = "systemair"
MANUFACTURER = "Systemair"

# Connection types
CONN_CLOUD = "cloud"

# Config keys
CONF_CONNECTION_TYPE = "connection_type"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"
CONF_API_URL = "api_url"
CONF_WS_URL = "ws_url"

# Defaults
DEFAULT_POLL_INTERVAL = 20  # seconds
DEFAULT_CLOUD_API_URL = "https://homesolutions.systemair.com/gateway/api"
DEFAULT_CLOUD_WS_URL = "wss://homesolutions.systemair.com/streaming/"
# ──────────────────────────────────────────────
# Modbus Register definitions
# ──────────────────────────────────────────────


class IntegerType(IntEnum):
    """Integer signedness for Modbus register values."""

    UINT = 0
    INT = 1


class RegisterType(IntEnum):
    """Modbus register type (holding vs input)."""

    HOLDING = 0
    INPUT = 1


class ModbusParam:
    """Represents a single Modbus register parameter."""

    def __init__(
        self,
        register: int,
        sig: IntegerType,
        reg_type: RegisterType,
        short: str,
        description: str,
        scale_factor: int = 1,
        is_boolean: bool = False,
        min_val: int | None = None,
        max_val: int | None = None,
    ) -> None:
        """Initialize a Modbus parameter definition."""
        self.register = register
        self.sig = sig
        self.reg_type = reg_type
        self.short = short
        self.description = description
        self.scale_factor = scale_factor
        self.is_boolean = is_boolean
        self.min_val = min_val
        self.max_val = max_val


# All Modbus parameters (register addresses are 1-indexed, wire uses register-1)
PARAMETERS: list[ModbusParam] = [
    # Demand control
    ModbusParam(1001, IntegerType.UINT, RegisterType.INPUT, "REG_DEMC_RH_HIGHEST",
                "Highest value of all RH sensors", min_val=0, max_val=100),

    # User modes
    ModbusParam(1101, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_HOLIDAY_TIME",
                "Time delay setting for user mode Holiday (days)", min_val=1, max_val=365),
    ModbusParam(1102, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_AWAY_TIME",
                "Time delay setting for user mode Away (hours)", min_val=1, max_val=72),
    ModbusParam(1103, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_FIREPLACE_TIME",
                "Time delay setting for user mode Fire Place (minutes)", min_val=1, max_val=60),
    ModbusParam(1104, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_REFRESH_TIME",
                "Time delay setting for user mode Refresh (minutes)", min_val=1, max_val=240),
    ModbusParam(1105, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_CROWDED_TIME",
                "Time delay setting for user mode Crowded (hours)", min_val=1, max_val=8),
    ModbusParam(1111, IntegerType.UINT, RegisterType.INPUT, "REG_USERMODE_REMAINING_TIME_L",
                "Remaining time lower 16 bits"),
    ModbusParam(1112, IntegerType.UINT, RegisterType.INPUT, "REG_USERMODE_REMAINING_TIME_H",
                "Remaining time higher 16 bits"),
    ModbusParam(1131, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Manual", min_val=0, max_val=4),
    ModbusParam(1135, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Crowded", min_val=3, max_val=5),
    ModbusParam(1136, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Crowded EAF", min_val=3, max_val=5),
    ModbusParam(1137, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Refresh", min_val=3, max_val=5),
    ModbusParam(1138, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Refresh EAF", min_val=3, max_val=5),
    ModbusParam(1139, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Fireplace", min_val=3, max_val=5),
    ModbusParam(1140, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Fireplace EAF", min_val=1, max_val=3),
    ModbusParam(1141, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Away", min_val=0, max_val=3),
    ModbusParam(1142, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_AWAY_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Away EAF", min_val=0, max_val=3),
    ModbusParam(1143, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Holiday", min_val=0, max_val=3),
    ModbusParam(1144, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Holiday EAF", min_val=0, max_val=3),
    ModbusParam(1145, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Cooker Hood", min_val=1, max_val=5),
    ModbusParam(1146, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Cooker Hood EAF", min_val=1, max_val=5),
    ModbusParam(1147, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_SAF",
                "Fan speed level for mode Vacuum Cleaner", min_val=1, max_val=5),
    ModbusParam(1148, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_EAF",
                "Fan speed level for mode Vacuum Cleaner EAF", min_val=1, max_val=5),
    ModbusParam(1161, IntegerType.UINT, RegisterType.INPUT, "REG_USERMODE_MODE",
                "Active User mode", min_val=0, max_val=12),
    ModbusParam(1162, IntegerType.UINT, RegisterType.HOLDING, "REG_USERMODE_HMI_CHANGE_REQUEST",
                "New desired user mode", min_val=0, max_val=7),
    ModbusParam(1177, IntegerType.UINT, RegisterType.HOLDING, "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_SAF",
                "Fan speed level for PressureGuard", min_val=0, max_val=5),
    ModbusParam(1178, IntegerType.UINT, RegisterType.HOLDING, "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_EAF",
                "Fan speed level for PressureGuard EAF", min_val=0, max_val=5),

    # Digital input sensors
    ModbusParam(12306, IntegerType.UINT, RegisterType.INPUT, "REG_SENSOR_DI_COOKERHOOD",
                "Cooker hood", is_boolean=True),
    ModbusParam(12307, IntegerType.UINT, RegisterType.INPUT, "REG_SENSOR_DI_VACUUMCLEANER",
                "Vacuum cleaner", is_boolean=True),

    # Function active registers (3101-3117, INPUT registers)
    ModbusParam(3101, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_COOLING",
                "Cooling", is_boolean=True),
    ModbusParam(3102, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_FREE_COOLING",
                "Free cooling", is_boolean=True),
    ModbusParam(3103, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_HEATING",
                "Heating", is_boolean=True),
    ModbusParam(3104, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_DEFROSTING",
                "Defrosting", is_boolean=True),
    ModbusParam(3105, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_HEAT_RECOVERY",
                "Heat recovery", is_boolean=True),
    ModbusParam(3106, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_COOLING_RECOVERY",
                "Cooling recovery", is_boolean=True),
    ModbusParam(3107, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER",
                "Moisture transfer", is_boolean=True),
    ModbusParam(3108, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_SECONDARY_AIR",
                "Secondary air", is_boolean=True),
    ModbusParam(3109, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_VACUUM_CLEANER",
                "Vacuum cleaner", is_boolean=True),
    ModbusParam(3110, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_COOKER_HOOD",
                "Cooker hood", is_boolean=True),
    ModbusParam(3111, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_USER_LOCK",
                "User lock", is_boolean=True),
    ModbusParam(3112, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_ECO_MODE",
                "ECO mode active", is_boolean=True),
    ModbusParam(3113, IntegerType.INT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_HEATER_COOL_DOWN",
                "Heater cool down", is_boolean=True),
    ModbusParam(3114, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_PRESSURE_GUARD",
                "Pressure guard", is_boolean=True),
    ModbusParam(3115, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_CDI_1",
                "Configurable DI1", is_boolean=True),
    ModbusParam(3116, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_CDI_2",
                "Configurable DI2", is_boolean=True),
    ModbusParam(3117, IntegerType.UINT, RegisterType.INPUT, "REG_FUNCTION_ACTIVE_CDI_3",
                "Configurable DI3", is_boolean=True),

    # Heat exchanger configuration (HOLDING registers)
    ModbusParam(2133, IntegerType.UINT, RegisterType.HOLDING, "REG_HEAT_EXCHANGER_TYPE",
                "Heat exchanger type", min_val=0, max_val=1),
    ModbusParam(2132, IntegerType.UINT, RegisterType.HOLDING, "REG_HEAT_EXCHANGER_SPEED",
                "Heat exchanger speed", min_val=0, max_val=100),
    ModbusParam(2134, IntegerType.UINT, RegisterType.HOLDING, "REG_MOISTURE_TRANSFER_ON_OFF",
                "Moisture transfer enabled", is_boolean=True),

    # Heater configuration (HOLDING registers)
    ModbusParam(3002, IntegerType.UINT, RegisterType.HOLDING, "REG_HEATER_TYPE",
                "Heater type", min_val=0, max_val=3),
    ModbusParam(3003, IntegerType.UINT, RegisterType.HOLDING, "REG_HEATER_POSITION",
                "Heater position", min_val=0, max_val=1),

    # Airflow control
    ModbusParam(12401, IntegerType.UINT, RegisterType.INPUT, "REG_SENSOR_RPM_SAF",
                "Supply Air Fan RPM", min_val=0, max_val=5000),
    ModbusParam(12402, IntegerType.UINT, RegisterType.INPUT, "REG_SENSOR_RPM_EAF",
                "Extract Air Fan RPM", min_val=0, max_val=5000),
    ModbusParam(14001, IntegerType.UINT, RegisterType.INPUT, "REG_OUTPUT_SAF",
                "SAF fan speed", min_val=0, max_val=100),
    ModbusParam(14002, IntegerType.UINT, RegisterType.INPUT, "REG_OUTPUT_EAF",
                "EAF fan speed", min_val=0, max_val=100),

    # Temperature control
    ModbusParam(2001, IntegerType.INT, RegisterType.HOLDING, "REG_TC_SP",
                "Temperature setpoint", scale_factor=10, min_val=120, max_val=300),

    # Cooler
    ModbusParam(14201, IntegerType.INT, RegisterType.INPUT, "REG_OUTPUT_Y3_ANALOG",
                "Cooler AO state", min_val=0, max_val=100),
    ModbusParam(14202, IntegerType.INT, RegisterType.INPUT, "REG_OUTPUT_Y3_DIGITAL",
                "Cooler DO state", is_boolean=True),

    # Heater
    ModbusParam(14101, IntegerType.INT, RegisterType.INPUT, "REG_OUTPUT_Y1_ANALOG",
                "Heater AO state", min_val=0, max_val=100),
    ModbusParam(14102, IntegerType.INT, RegisterType.INPUT, "REG_OUTPUT_Y1_DIGITAL",
                "Heater DO state", is_boolean=True),

    # ECO mode
    ModbusParam(2505, IntegerType.UINT, RegisterType.HOLDING, "REG_ECO_MODE_ON_OFF",
                "Enabling of eco mode", is_boolean=True),

    # Filter replacement
    ModbusParam(7005, IntegerType.UINT, RegisterType.INPUT, "REG_FILTER_REMAINING_TIME_L",
                "Remaining filter time in seconds, lower 16 bits"),
    ModbusParam(7006, IntegerType.UINT, RegisterType.INPUT, "REG_FILTER_REMAINING_TIME_H",
                "Remaining filter time in seconds, higher 16 bits"),

    # Temperature sensors
    ModbusParam(12102, IntegerType.INT, RegisterType.HOLDING, "REG_SENSOR_OAT",
                "Outdoor Air Temperature", scale_factor=10, min_val=-400, max_val=800),
    ModbusParam(12103, IntegerType.INT, RegisterType.HOLDING, "REG_SENSOR_SAT",
                "Supply Air Temperature", scale_factor=10, min_val=-400, max_val=800),
    ModbusParam(12105, IntegerType.INT, RegisterType.HOLDING, "REG_SENSOR_EAT",
                "Extract Air Temperature", scale_factor=10, min_val=-400, max_val=800),
    ModbusParam(12108, IntegerType.INT, RegisterType.HOLDING, "REG_SENSOR_OHT",
                "Overheat Temperature", scale_factor=10, min_val=-400, max_val=800),
    ModbusParam(12109, IntegerType.UINT, RegisterType.HOLDING, "REG_SENSOR_RHS",
                "Relative Humidity Sensor", min_val=0, max_val=100),
    ModbusParam(12544, IntegerType.INT, RegisterType.HOLDING, "REG_SENSOR_PDM_EAT_VALUE",
                "PDM EAT sensor value", scale_factor=10, min_val=-400, max_val=800),
    ModbusParam(12136, IntegerType.UINT, RegisterType.HOLDING, "REG_SENSOR_RHS_PDM",
                "PDM RHS sensor value", min_val=0, max_val=100),

    # Alarms
    ModbusParam(15016, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_FROST_PROT_ALARM",
                "Frost protection", min_val=0, max_val=3),
    ModbusParam(15023, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_DEFROSTING_ALARM",
                "Defrosting", min_val=0, max_val=3),
    ModbusParam(15030, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_SAF_RPM_ALARM",
                "Supply air fan RPM", min_val=0, max_val=3),
    ModbusParam(15037, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_EAF_RPM_ALARM",
                "Extract air fan RPM", min_val=0, max_val=3),
    ModbusParam(15072, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_SAT_ALARM",
                "Supply air temperature", min_val=0, max_val=3),
    ModbusParam(15086, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_EAT_ALARM",
                "Extract air temperature", min_val=0, max_val=3),
    ModbusParam(15121, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_RGS_ALARM",
                "Rotation guard (RGS)", min_val=0, max_val=3),
    ModbusParam(15142, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_FILTER_ALARM",
                "Filter", min_val=0, max_val=3),
    ModbusParam(15170, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_CO2_ALARM",
                "CO2", min_val=0, max_val=3),
    ModbusParam(15177, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_LOW_SAT_ALARM",
                "Low supply air temperature", min_val=0, max_val=3),
    ModbusParam(15530, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_OVERHEAT_TEMPERATURE_ALARM",
                "Overheat temperature", min_val=0, max_val=3),
    ModbusParam(15537, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_FIRE_ALARM_ALARM",
                "Fire alarm", min_val=0, max_val=3),
    ModbusParam(15544, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_FILTER_WARNING_ALARM",
                "Filter warning", min_val=0, max_val=3),
    ModbusParam(15901, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_TYPE_A",
                "Alarm Type A active", is_boolean=True),
    ModbusParam(15902, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_TYPE_B",
                "Alarm Type B active", is_boolean=True),
    ModbusParam(15903, IntegerType.UINT, RegisterType.INPUT, "REG_ALARM_TYPE_C",
                "Alarm Type C active", is_boolean=True),
]

# Build parameter lookup map
PARAMETER_MAP: dict[str, ModbusParam] = {p.short: p for p in PARAMETERS}

# Parameter groups for polling
OPERATION_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_TC_SP",
        "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_MODE",
        "REG_ECO_MODE_ON_OFF",
        "REG_SENSOR_RPM_SAF",
        "REG_SENSOR_RPM_EAF",
        "REG_OUTPUT_SAF",
        "REG_OUTPUT_EAF",
        "REG_OUTPUT_Y1_ANALOG",
        "REG_OUTPUT_Y1_DIGITAL",
        "REG_OUTPUT_Y3_ANALOG",
        "REG_OUTPUT_Y3_DIGITAL",
        "REG_USERMODE_REMAINING_TIME_L",
        "REG_USERMODE_REMAINING_TIME_H",
    ]
]

SENSOR_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_SENSOR_RHS_PDM",
        "REG_SENSOR_OAT",
        "REG_SENSOR_SAT",
        "REG_SENSOR_PDM_EAT_VALUE",
        "REG_SENSOR_OHT",
    ]
]

CONFIG_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_FILTER_REMAINING_TIME_L",
        "REG_FILTER_REMAINING_TIME_H",
        "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_AWAY_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_SAF",
        "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_EAF",
        "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_SAF",
        "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_EAF",
        "REG_USERMODE_HOLIDAY_TIME",
        "REG_USERMODE_AWAY_TIME",
        "REG_USERMODE_FIREPLACE_TIME",
        "REG_USERMODE_REFRESH_TIME",
        "REG_USERMODE_CROWDED_TIME",
    ]
]

ALARM_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_ALARM_FROST_PROT_ALARM",
        "REG_ALARM_DEFROSTING_ALARM",
        "REG_ALARM_SAF_RPM_ALARM",
        "REG_ALARM_EAF_RPM_ALARM",
        "REG_ALARM_SAT_ALARM",
        "REG_ALARM_EAT_ALARM",
        "REG_ALARM_RGS_ALARM",
        "REG_ALARM_FILTER_ALARM",
        "REG_ALARM_CO2_ALARM",
        "REG_ALARM_LOW_SAT_ALARM",
        "REG_ALARM_OVERHEAT_TEMPERATURE_ALARM",
        "REG_ALARM_FIRE_ALARM_ALARM",
        "REG_ALARM_FILTER_WARNING_ALARM",
        "REG_ALARM_TYPE_A",
        "REG_ALARM_TYPE_B",
        "REG_ALARM_TYPE_C",
    ]
]

DIAGNOSTIC_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_HEAT_EXCHANGER_TYPE",
        "REG_HEAT_EXCHANGER_SPEED",
        "REG_MOISTURE_TRANSFER_ON_OFF",
        "REG_HEATER_TYPE",
        "REG_HEATER_POSITION",
    ]
]

FUNCTION_PARAMS = [
    PARAMETER_MAP[k] for k in [
        "REG_FUNCTION_ACTIVE_COOLING",
        "REG_FUNCTION_ACTIVE_FREE_COOLING",
        "REG_FUNCTION_ACTIVE_HEATING",
        "REG_FUNCTION_ACTIVE_DEFROSTING",
        "REG_FUNCTION_ACTIVE_HEAT_RECOVERY",
        "REG_FUNCTION_ACTIVE_COOLING_RECOVERY",
        "REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER",
        "REG_FUNCTION_ACTIVE_SECONDARY_AIR",
        "REG_FUNCTION_ACTIVE_VACUUM_CLEANER",
        "REG_FUNCTION_ACTIVE_COOKER_HOOD",
        "REG_FUNCTION_ACTIVE_USER_LOCK",
        "REG_FUNCTION_ACTIVE_ECO_MODE",
        "REG_FUNCTION_ACTIVE_HEATER_COOL_DOWN",
        "REG_FUNCTION_ACTIVE_PRESSURE_GUARD",
        "REG_FUNCTION_ACTIVE_CDI_1",
        "REG_FUNCTION_ACTIVE_CDI_2",
        "REG_FUNCTION_ACTIVE_CDI_3",
        "REG_SENSOR_DI_COOKERHOOD",
        "REG_SENSOR_DI_VACUUMCLEANER",
    ]
]

# ──────────────────────────────────────────────
# Mode & fan mode mappings
# ──────────────────────────────────────────────

FAN_MODES: dict[int, str] = {
    0: "Off",
    1: "Off",
    2: "Low",
    3: "Normal",
    4: "High",
    5: "Maximum",
}

FAN_MODES_SETTABLE: dict[int, str] = {
    2: "Low",
    3: "Normal",
    4: "High",
}

MODES: dict[int, str] = {
    0: "Auto",
    1: "Manual",
    2: "Crowded",
    3: "Refresh",
    4: "Fireplace",
    5: "Away",
    6: "Holiday",
    7: "Cooker Hood",
    8: "Vacuum Cleaner",
    9: "CDI1",
    10: "CDI2",
    11: "CDI3",
    12: "PressureGuard",
}

MODES_SETTABLE: dict[int, str] = {
    0: "Auto",
    1: "Manual",
}

# HMI change request codes (mode value + 1)
MODE_CHANGE_CODES: dict[str, int] = {
    "auto": 1,
    "manual": 2,
    "crowded": 3,
    "refresh": 4,
    "fireplace": 5,
    "away": 6,
    "holiday": 7,
}

# ──────────────────────────────────────────────
# Preset mode definitions for the climate entity
# ──────────────────────────────────────────────

# Heat exchanger type values (Modbus 2133 / REG_HEAT_EXCHANGER_TYPE)
HEAT_EXCHANGER_TYPES: dict[int, str] = {
    0: "Rotating",
    1: "Plate",
}

# Heater type values (Modbus 3002 / REG_HEATER_TYPE)
HEATER_TYPES: dict[int, str] = {
    0: "None",
    1: "Electrical",
    2: "Water",
    3: "Change Over",
}

# Heater position values (Modbus 3003 / REG_HEATER_POSITION)
HEATER_POSITIONS: dict[int, str] = {
    0: "Supply",
    1: "Extract",
}

# HA preset name -> timed mode name (as used by coordinator.async_set_timed_mode)
PRESET_TO_TIMED_MODE: dict[str, str] = {
    "away": "away",
    "boost": "refresh",
    "comfort": "crowded",
    "fireplace": "fireplace",
    "holiday": "holiday",
}

# Default durations for timed modes when activated via preset (native units).
# away=hours, crowded=hours, fireplace=minutes, refresh=minutes, holiday=days
TIMED_MODE_DEFAULTS: dict[str, int] = {
    "away": 8,        # 8 hours
    "crowded": 4,     # 4 hours
    "fireplace": 30,  # 30 minutes
    "refresh": 60,    # 60 minutes
    "holiday": 7,     # 7 days
}

# Timed mode duration registers for number entities
# (register_short, mode_name, unit)
TIMED_MODE_DURATION_REGISTERS: list[tuple[str, str, str]] = [
    ("REG_USERMODE_HOLIDAY_TIME", "Holiday", "d"),
    ("REG_USERMODE_AWAY_TIME", "Away", "h"),
    ("REG_USERMODE_FIREPLACE_TIME", "Fireplace", "min"),
    ("REG_USERMODE_REFRESH_TIME", "Refresh", "min"),
    ("REG_USERMODE_CROWDED_TIME", "Crowded", "h"),
]

# User mode value (from device) -> HA preset name
USER_MODE_TO_PRESET: dict[int, str] = {
    2: "comfort",    # Crowded -> "comfort" preset
    3: "boost",      # Refresh -> "boost" preset
    4: "fireplace",  # Fireplace -> "fireplace" preset
    5: "away",       # Away -> "away" preset
    6: "holiday",    # Holiday -> "holiday" preset
}

# ──────────────────────────────────────────────
# Cloud API parameter names
# ──────────────────────────────────────────────

CLOUD_ALARMS = [
    {"id": "alarm_co2_state", "description": "CO2"},
    {"id": "alarm_defrosting_state", "description": "Defrosting"},
    {"id": "alarm_eaf_rpm_state", "description": "Extract air fan RPM"},
    {"id": "alarm_eat_state", "description": "Extract air temperature"},
    {"id": "alarm_emt_state", "description": "Frost protection (EMT)"},
    {"id": "alarm_filter_state", "description": "Filter"},
    {"id": "alarm_filter_warning_state", "description": "Filter warning"},
    {"id": "alarm_fire_alarm_state", "description": "Fire alarm"},
    {"id": "alarm_frost_prot_state", "description": "Frost protection"},
    {"id": "alarm_low_sat_state", "description": "Low supply air temperature"},
    {"id": "alarm_manual_mode_state", "description": "Manual mode"},
    {"id": "alarm_overheat_temperature_state", "description": "Overheat temperature"},
    {"id": "alarm_pdm_rhs_state", "description": "Rel. humidity sensor malfunction (PDM)"},
    {"id": "alarm_rgs_state", "description": "Rotation guard (RGS)"},
    {"id": "alarm_rh_state", "description": "Rel. humidity sensor malfunction (RH)"},
    {"id": "alarm_rotor_motor_feedback_state", "description": "Rotor motor feedback"},
    {"id": "alarm_saf_rpm_state", "description": "Supply air fan RPM"},
    {"id": "alarm_sat_state", "description": "Supply air temperature"},
]

CLOUD_FUNCTIONS = [
    {"id": "function_active_cooling", "description": "Cooling", "register": "REG_FUNCTION_ACTIVE_COOLING"},
    {"id": "function_active_free_cooling", "description": "Free cooling", "register": "REG_FUNCTION_ACTIVE_FREE_COOLING"},
    {"id": "function_active_heating", "description": "Heating", "register": "REG_FUNCTION_ACTIVE_HEATING"},
    {"id": "function_active_defrosting", "description": "Defrosting", "register": "REG_FUNCTION_ACTIVE_DEFROSTING"},
    {"id": "function_active_heat_recovery", "description": "Heat recovery", "register": "REG_FUNCTION_ACTIVE_HEAT_RECOVERY"},
    {"id": "function_active_cooling_recovery", "description": "Cooling recovery", "register": "REG_FUNCTION_ACTIVE_COOLING_RECOVERY"},
    {"id": "function_active_moisture_transfer", "description": "Moisture transfer", "register": "REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER"},
    {"id": "function_active_secondary_air", "description": "Secondary air", "register": "REG_FUNCTION_ACTIVE_SECONDARY_AIR"},
    {"id": "function_active_vacuum_cleaner", "description": "Vacuum cleaner", "register": "REG_FUNCTION_ACTIVE_VACUUM_CLEANER"},
    {"id": "function_active_cooker_hood", "description": "Cooker hood", "register": "REG_FUNCTION_ACTIVE_COOKER_HOOD"},
    {"id": "function_active_user_lock", "description": "User lock", "register": "REG_FUNCTION_ACTIVE_USER_LOCK"},
    {"id": "function_active_eco_mode", "description": "ECO mode active", "register": "REG_FUNCTION_ACTIVE_ECO_MODE"},
    {"id": "function_active_heater_cooldown", "description": "Heater cool down", "register": "REG_FUNCTION_ACTIVE_HEATER_COOL_DOWN"},
    {"id": "function_active_pressure_guard", "description": "Pressure guard", "register": "REG_FUNCTION_ACTIVE_PRESSURE_GUARD"},
    {"id": "function_active_configurable_di1", "description": "Configurable DI1", "register": "REG_FUNCTION_ACTIVE_CDI_1"},
    {"id": "function_active_configurable_di2", "description": "Configurable DI2", "register": "REG_FUNCTION_ACTIVE_CDI_2"},
    {"id": "function_active_configurable_di3", "description": "Configurable DI3", "register": "REG_FUNCTION_ACTIVE_CDI_3"},
    {"id": "function_active_service_user_lock", "description": "Service user lock"},
]

# ──────────────────────────────────────────────
# Cloud sensor data item ID mapping
# ──────────────────────────────────────────────
# Maps 1-indexed Modbus register numbers (as used in const.py ModbusParam
# definitions) to cloud data item IDs that can be read via GetDataItems.
#
# These INPUT registers are NOT returned by ExportDataItems but *are*
# accessible via GetDataItems when the correct data item ID is used.
# Discovered via exhaustive scan of data item IDs 0-2000.
CLOUD_SENSOR_DATA_ITEMS: dict[int, int] = {
    # Note: REG_USERMODE_MODE (1161) is read via GetDeviceStatus, not GetDataItems
    # Temperature sensors
    12102: 54,    # REG_SENSOR_OAT (Outdoor Air Temp)
    12103: 53,    # REG_SENSOR_SAT (Supply Air Temp)
    12108: 60,    # REG_SENSOR_OHT (Overheat Temp)
    12136: 78,    # REG_SENSOR_RHS_PDM (Humidity)
    12544: 89,    # REG_SENSOR_PDM_EAT_VALUE (Extract Air Temp)
    # Fan RPM and speed
    12401: 83,    # REG_SENSOR_RPM_SAF (Supply Fan RPM)
    12402: 84,    # REG_SENSOR_RPM_EAF (Extract Fan RPM)
    14001: 1023,  # REG_OUTPUT_SAF (Supply Fan Speed %)
    14002: 1024,  # REG_OUTPUT_EAF (Extract Fan Speed %)
    # Function active registers (3101-3117 -> data items 102-118)
    3101: 102,    # REG_FUNCTION_ACTIVE_COOLING
    3102: 103,    # REG_FUNCTION_ACTIVE_FREE_COOLING
    3103: 104,    # REG_FUNCTION_ACTIVE_HEATING
    3104: 105,    # REG_FUNCTION_ACTIVE_DEFROSTING
    3105: 106,    # REG_FUNCTION_ACTIVE_HEAT_RECOVERY
    3106: 107,    # REG_FUNCTION_ACTIVE_COOLING_RECOVERY
    3107: 108,    # REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER
    3108: 109,    # REG_FUNCTION_ACTIVE_SECONDARY_AIR
    3109: 110,    # REG_FUNCTION_ACTIVE_VACUUM_CLEANER
    3110: 111,    # REG_FUNCTION_ACTIVE_COOKER_HOOD
    3111: 112,    # REG_FUNCTION_ACTIVE_USER_LOCK
    3112: 113,    # REG_FUNCTION_ACTIVE_ECO_MODE
    3113: 114,    # REG_FUNCTION_ACTIVE_HEATER_COOL_DOWN
    3114: 115,    # REG_FUNCTION_ACTIVE_PRESSURE_GUARD
    3115: 116,    # REG_FUNCTION_ACTIVE_CDI_1
    3116: 117,    # REG_FUNCTION_ACTIVE_CDI_2
    3117: 118,    # REG_FUNCTION_ACTIVE_CDI_3
}

# ──────────────────────────────────────────────
# Cloud control data items (HOLDING registers)
# ──────────────────────────────────────────────
# Mappings for writable HOLDING registers used for control operations.
# Discovered from Systemair web UI GraphQL mutations.
CLOUD_CONTROL_DATA_ITEMS: dict[int, int] = {
    1162: 30,     # REG_USERMODE_HMI_CHANGE_REQUEST (Auto=1, Manual=2, Crowded=3, Refresh=4, Fireplace=5, Away=6, Holiday=7)
    # Timed mode duration registers (sequential pattern)
    1101: 251,    # REG_USERMODE_HOLIDAY_TIME (hours)
    1102: 252,    # REG_USERMODE_AWAY_TIME (hours)
    1103: 253,    # REG_USERMODE_FIREPLACE_TIME (minutes)
    1104: 254,    # REG_USERMODE_REFRESH_TIME (minutes)
    1105: 255,    # REG_USERMODE_CROWDED_TIME (hours) [CONFIRMED from browser]
}

# ──────────────────────────────────────────────
# Cloud-unavailable sensor keys
# ──────────────────────────────────────────────
# These SystemairData fields cannot be populated via the cloud API because
# the underlying Modbus registers have no known data item IDs and
# GetDeviceStatus / WebSocket don't provide them.
# Sensor entities should mark themselves as unavailable for cloud
# connections when their value_fn reads from these fields.
CLOUD_UNAVAILABLE_SENSORS: set[str] = {
    "heater_output", # REG_OUTPUT_Y1_ANALOG (14101) — no data item ID
    "cooler_output", # REG_OUTPUT_Y3_ANALOG (14201) — no data item ID
}

# ──────────────────────────────────────────────
# Fan level register definitions for number entities
# ──────────────────────────────────────────────

# Each entry: (register_short_name, mode_name, air_type)
FAN_LEVEL_REGISTERS: list[tuple[str, str, str]] = [
    ("REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF", "Crowded", "Supply"),
    ("REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF", "Crowded", "Extract"),
    ("REG_USERMODE_REFRESH_AIRFLOW_LEVEL_SAF", "Refresh", "Supply"),
    ("REG_USERMODE_REFRESH_AIRFLOW_LEVEL_EAF", "Refresh", "Extract"),
    ("REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_SAF", "Fireplace", "Supply"),
    ("REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_EAF", "Fireplace", "Extract"),
    ("REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF", "Away", "Supply"),
    ("REG_USERMODE_AWAY_AIRFLOW_LEVEL_EAF", "Away", "Extract"),
    ("REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_SAF", "Holiday", "Supply"),
    ("REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_EAF", "Holiday", "Extract"),
    ("REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_SAF", "Cooker Hood", "Supply"),
    ("REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_EAF", "Cooker Hood", "Extract"),
    ("REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_SAF", "Vacuum Cleaner", "Supply"),
    ("REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_EAF", "Vacuum Cleaner", "Extract"),
    ("REG_PRESSURE_GUARD_AIRFLOW_LEVEL_SAF", "Pressure Guard", "Supply"),
    ("REG_PRESSURE_GUARD_AIRFLOW_LEVEL_EAF", "Pressure Guard", "Extract"),
]
