"""Shared test fixtures for Systemair integration tests."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONN_CLOUD,
    DOMAIN,
    FAN_MODES,
    MODES,
)
from custom_components.systemair.coordinator import SystemairCoordinator, SystemairData


# ---------------------------------------------------------------------------
# Mock config entries
# ---------------------------------------------------------------------------


class MockConfigEntry:
    """Minimal mock of homeassistant.config_entries.ConfigEntry."""

    def __init__(
        self,
        *,
        entry_id: str = "test_entry_id",
        domain: str = DOMAIN,
        title: str = "Systemair Test",
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.domain = domain
        self.title = title
        self.data = data or {}
        self.options = options or {}


@pytest.fixture
def cloud_entry() -> MockConfigEntry:
    """Return a mock config entry for Cloud connection."""
    return MockConfigEntry(
        title="Systemair Cloud (Living Room)",
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_POLL_INTERVAL: 30,
            "machine_id": "machine_123",
            "machine_name": "Living Room",
            "device_type": "LEGACY",
        },
    )


# ---------------------------------------------------------------------------
# Mock API clients
# ---------------------------------------------------------------------------


def make_mock_cloud_api() -> MagicMock:
    """Create a mock CloudAPI with standard responses.

    The cloud API now uses the same register-based interface
    (read_params, write_param, write_params).
    """
    api = MagicMock()
    api.machine_id = "machine_123"
    api.machine_name = "Living Room"
    api._device_id = "machine_123"
    api._device_name = "Living Room"
    api._device_type = "LEGACY"
    api.login = AsyncMock(return_value="fake_token")
    api.close = AsyncMock()
    api.get_devices = AsyncMock(return_value=[
        {
            "machine_id": "machine_123",
            "name": "Living Room",
            "connection_status": "ONLINE",
            "device_type": "LEGACY",
        },
    ])
    api.set_machine = MagicMock()

    # Same interface as Modbus/SaveConnect
    api.read_params = AsyncMock(return_value={
        "REG_TC_SP": 21.0,
        "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF": 3,
        "REG_USERMODE_MODE": 0,
        "REG_ECO_MODE_ON_OFF": False,
        "REG_SENSOR_RPM_SAF": 1200.0,
        "REG_SENSOR_RPM_EAF": 1100.0,
        "REG_OUTPUT_SAF": 65.0,
        "REG_OUTPUT_EAF": 60.0,
    })
    api.write_param = AsyncMock()
    api.write_params = AsyncMock()

    # Cloud-specific methods
    api.get_device_status = AsyncMock(return_value={
        "id": "machine_123",
        "connectivity": "ONLINE",
        "activeAlarms": 0,
        "temperature": 21.5,
        "airflow": 3,
        "filterExpiration": "2026-06-15",
        "serialNumber": "12345",
        "model": "VTR300",
        "humidity": 45,
        "userMode": 0,
    })
    api.get_active_alarms = AsyncMock(return_value=[])
    api.get_filter_information = AsyncMock(return_value={
        "selectedFilter": "F7",
        "itemNumber": "123456",
    })
    api._ensure_mapping = AsyncMock()
    api.connect_websocket = AsyncMock(return_value=MagicMock())

    # Backward-compatible write() method (still exists for convenience)
    api.write = AsyncMock()

    api.read_data_items = AsyncMock(return_value=[
        {"id": 1, "value": "210"},
        {"id": 2, "value": "45"},
    ])
    api.collect_diagnostics_data = AsyncMock(return_value={
        "device_id": "machine_123",
        "device_name": "Living Room",
        "device_type": "LEGACY",
        "account_devices": [
            {
                "identifier": "machine_123",
                "name": "Living Room",
                "deviceType": {"type": "LEGACY"},
                "status": {
                    "connectionStatus": "ONLINE",
                    "serialNumber": "12345",
                    "model": "VTR300",
                    "hasAlarms": False,
                    "units": {"temperature": "C", "pressure": "Pa", "flow": "l/s"},
                },
            }
        ],
        "export_data_items": {
            "version": "1.0",
            "type": "LEGACY",
            "data_item_count": 2,
            "data_items": [
                {"id": 1, "extension": {"modbusRegister": 100}},
                {"id": 2, "extension": {"modbusRegister": 101}},
            ],
        },
        "device_status": {
            "id": "machine_123",
            "connectivity": "ONLINE",
            "activeAlarms": 0,
            "temperature": 21.5,
            "airflow": 3,
            "filterExpiration": "2026-06-15",
            "serialNumber": "12345",
            "model": "VTR300",
        },
        "active_alarms": [],
        "filter_information": {"selectedFilter": "F7", "itemNumber": "123456"},
        "all_data_item_values": {
            "requested_count": 2,
            "received_count": 2,
            "items": [
                {"id": 1, "value": "210"},
                {"id": 2, "value": "45"},
            ],
        },
        "sensor_data_item_values": {
            "mapping": {"12001": 5001},
            "requested_count": 1,
            "received_count": 1,
            "items": [{"id": 5001, "value": "22"}],
        },
    })

    api.test_connection = AsyncMock(return_value=True)
    return api


@pytest.fixture
def mock_cloud_api() -> MagicMock:
    return make_mock_cloud_api()


# ---------------------------------------------------------------------------
# Sample SystemairData
# ---------------------------------------------------------------------------


def make_sample_data(connection_type: str = CONN_CLOUD) -> SystemairData:
    """Create a fully-populated SystemairData for testing."""
    data = SystemairData()
    data.connection_type = connection_type
    data.target_temperature = 21.0
    data.supply_air_temperature = 21.5
    data.outdoor_air_temperature = 5.0
    data.extract_air_temperature = 22.0
    data.overheat_temperature = 25.0
    data.humidity = 45.0
    data.co2 = 450
    data.air_quality = 0
    data.fan_mode = 3
    data.fan_mode_name = "Normal"
    data.saf_rpm = 1200.0
    data.eaf_rpm = 1100.0
    data.saf_speed = 65.0
    data.eaf_speed = 60.0
    data.user_mode = 0
    data.user_mode_name = "Auto"
    data.eco_mode = False
    data.filter_days_left = 60
    data.heater_output = 0.0
    data.heater_active = False
    data.cooler_output = 0.0
    data.cooler_active = False
    data.remaining_time_seconds = 0
    data.fan_levels = {
        "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF": 4,
        "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF": 4,
        "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_SAF": 4,
        "REG_USERMODE_REFRESH_AIRFLOW_LEVEL_EAF": 4,
        "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_SAF": 4,
        "REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_EAF": 2,
        "REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF": 2,
        "REG_USERMODE_AWAY_AIRFLOW_LEVEL_EAF": 2,
        "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_SAF": 1,
        "REG_USERMODE_HOLIDAY_AIRFLOW_LEVEL_EAF": 1,
        "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_SAF": 3,
        "REG_USERMODE_COOKERHOOD_AIRFLOW_LEVEL_EAF": 3,
        "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_SAF": 3,
        "REG_USERMODE_VACUUMCLEANER_AIRFLOW_LEVEL_EAF": 3,
        "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_SAF": 3,
        "REG_PRESSURE_GUARD_AIRFLOW_LEVEL_EAF": 3,
    }
    # Timed mode durations (days/hours/minutes depending on mode)
    data.timed_mode_durations = {
        "REG_USERMODE_HOLIDAY_TIME": 7,
        "REG_USERMODE_AWAY_TIME": 24,
        "REG_USERMODE_FIREPLACE_TIME": 30,
        "REG_USERMODE_REFRESH_TIME": 120,
        "REG_USERMODE_CROWDED_TIME": 4,
    }

    # Diagnostic fields
    data.heat_exchanger_type = "Rotating"
    data.heat_exchanger_speed = 60
    data.moisture_transfer_enabled = False
    data.heater_type = "Electrical"
    data.heater_position = "Supply"

    data.alarms = {
        "REG_ALARM_FROST_PROT_ALARM": 0,
        "REG_ALARM_FILTER_ALARM": 0,
        "REG_ALARM_TYPE_A": False,
    }
    data.functions = {
        "REG_FUNCTION_ACTIVE_COOLING": False,
        "REG_FUNCTION_ACTIVE_FREE_COOLING": False,
        "REG_FUNCTION_ACTIVE_HEATING": True,
        "REG_FUNCTION_ACTIVE_DEFROSTING": False,
        "REG_FUNCTION_ACTIVE_HEAT_RECOVERY": True,
        "REG_FUNCTION_ACTIVE_COOLING_RECOVERY": False,
        "REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER": True,
        "REG_FUNCTION_ACTIVE_SECONDARY_AIR": False,
        "REG_FUNCTION_ACTIVE_VACUUM_CLEANER": False,
        "REG_FUNCTION_ACTIVE_COOKER_HOOD": False,
        "REG_FUNCTION_ACTIVE_USER_LOCK": False,
        "REG_FUNCTION_ACTIVE_ECO_MODE": False,
        "REG_FUNCTION_ACTIVE_HEATER_COOL_DOWN": False,
        "REG_FUNCTION_ACTIVE_PRESSURE_GUARD": False,
        "REG_FUNCTION_ACTIVE_CDI_1": False,
        "REG_FUNCTION_ACTIVE_CDI_2": False,
        "REG_FUNCTION_ACTIVE_CDI_3": False,
        "REG_SENSOR_DI_COOKERHOOD": False,
        "REG_SENSOR_DI_VACUUMCLEANER": False,
    }
    return data


@pytest.fixture
def sample_data() -> SystemairData:
    return make_sample_data()


@pytest.fixture
def sample_data_cloud() -> SystemairData:
    data = make_sample_data(CONN_CLOUD)
    # Cloud now uses the same Modbus-style register keys as other
    # connection types (since cloud API maps data item IDs to registers).
    # Alarm/function keys are therefore the same as Modbus.
    return data
