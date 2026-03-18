"""Tests for the diagnostics module."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.systemair.const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONN_CLOUD,
    DOMAIN,
)
from custom_components.systemair.diagnostics import (
    _redact_cloud_data,
    async_get_config_entry_diagnostics,
)
from custom_components.systemair.coordinator import SystemairData
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockHass:
    """Minimal HomeAssistant mock for diagnostics tests."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}


class MockCoordinator:
    """Minimal coordinator mock for diagnostics tests."""

    def __init__(
        self,
        *,
        connection_type: str = CONN_CLOUD,
        data: SystemairData | None = None,
        api: Any = None,
    ) -> None:
        self.connection_type = connection_type
        self.data = data
        self._poll_count = 42
        self.last_update_success = True
        self.api = api


# ---------------------------------------------------------------------------
# Tests — _redact_cloud_data
# ---------------------------------------------------------------------------


class TestRedactCloudData:
    """Tests for the recursive cloud data redaction helper."""

    def test_redacts_serial_number(self):
        data = {"serialNumber": "12345", "model": "VTR300"}
        result = _redact_cloud_data(data)
        assert result["serialNumber"] == "**REDACTED**"
        assert result["model"] == "VTR300"

    def test_redacts_serial_number_snake_case(self):
        data = {"serial_number": "12345", "name": "Unit"}
        result = _redact_cloud_data(data)
        assert result["serial_number"] == "**REDACTED**"
        assert result["name"] == "Unit"

    def test_redacts_nested_dicts(self):
        data = {
            "status": {
                "connectionStatus": "ONLINE",
                "serialNumber": "SN999",
            }
        }
        result = _redact_cloud_data(data)
        assert result["status"]["serialNumber"] == "**REDACTED**"
        assert result["status"]["connectionStatus"] == "ONLINE"

    def test_redacts_in_lists(self):
        data = [
            {"serialNumber": "SN1", "name": "A"},
            {"serialNumber": "SN2", "name": "B"},
        ]
        result = _redact_cloud_data(data)
        assert result[0]["serialNumber"] == "**REDACTED**"
        assert result[1]["serialNumber"] == "**REDACTED**"
        assert result[0]["name"] == "A"

    def test_redacts_deeply_nested(self):
        data = {
            "devices": [
                {
                    "status": {
                        "serialNumber": "deep",
                        "model": "VTR300",
                    }
                }
            ]
        }
        result = _redact_cloud_data(data)
        assert result["devices"][0]["status"]["serialNumber"] == "**REDACTED**"
        assert result["devices"][0]["status"]["model"] == "VTR300"

    def test_leaves_scalars_unchanged(self):
        assert _redact_cloud_data(42) == 42
        assert _redact_cloud_data("hello") == "hello"
        assert _redact_cloud_data(None) is None

    def test_handles_error_strings(self):
        """Error strings from failed queries pass through."""
        data = {"account_devices": "Error: Connection refused"}
        result = _redact_cloud_data(data)
        assert result["account_devices"] == "Error: Connection refused"


# ---------------------------------------------------------------------------
# Tests — async_get_config_entry_diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_with_data():
    """Test diagnostics output with coordinator data."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(return_value={
        "device_id": "m1",
        "device_name": "Unit 1",
        "device_type": "LEGACY",
        "account_devices": [],
        "export_data_items": {"version": "1.0", "type": "LEGACY", "data_item_count": 0, "data_items": []},
        "device_status": {"id": "m1", "connectivity": "ONLINE"},
        "active_alarms": [],
        "filter_information": {"selectedFilter": "F7"},
        "all_data_item_values": {"requested_count": 0, "received_count": 0, "items": []},
        "sensor_data_item_values": {"mapping": {}, "requested_count": 0, "received_count": 0, "items": []},
    })

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_POLL_INTERVAL: 20,
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
        options={CONF_POLL_INTERVAL: 30},
    )
    sample = make_sample_data()
    coordinator = MockCoordinator(data=sample, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Config entry section
    assert result["config_entry"]["entry_id"] == entry.entry_id
    assert result["config_entry"]["title"] == entry.title
    assert result["config_entry"]["data"][CONF_EMAIL] == "**REDACTED**"
    assert result["config_entry"]["options"][CONF_POLL_INTERVAL] == 30

    # Coordinator section
    assert result["coordinator"]["connection_type"] == CONN_CLOUD
    assert result["coordinator"]["poll_count"] == 42
    assert result["coordinator"]["last_update_success"] is True

    # Data section
    assert result["data"]["target_temperature"] == 21.0
    assert result["data"]["supply_air_temperature"] == 21.5
    assert result["data"]["fan_mode"] == 3
    assert result["data"]["user_mode"] == 0
    assert result["data"]["eco_mode"] is False
    assert result["data"]["filter_days_left"] == 60
    assert isinstance(result["data"]["alarms"], dict)
    assert isinstance(result["data"]["functions"], dict)

    # Cloud raw data section
    assert "cloud_raw_data" in result
    assert result["cloud_raw_data"]["device_id"] == "m1"
    mock_api.collect_diagnostics_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_diagnostics_without_data():
    """Test diagnostics output when coordinator has no data."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(return_value={
        "device_id": "m1",
        "device_type": "LEGACY",
    })

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
    )
    coordinator = MockCoordinator(data=None, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["data"] is None
    # Cloud raw data is still collected even with no coordinator data
    assert "cloud_raw_data" in result


@pytest.mark.asyncio
async def test_diagnostics_redacts_credentials():
    """Test that email and password are redacted in diagnostics."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(return_value={
        "device_id": "m1",
        "device_type": "LEGACY",
    })

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "super_secret",
            CONF_POLL_INTERVAL: 30,
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
    )
    sample = make_sample_data(CONN_CLOUD)
    coordinator = MockCoordinator(connection_type=CONN_CLOUD, data=sample, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    config_data = result["config_entry"]["data"]
    assert config_data[CONF_EMAIL] == "**REDACTED**"
    assert config_data[CONF_PASSWORD] == "**REDACTED**"
    # Non-sensitive fields should NOT be redacted
    assert config_data[CONF_CONNECTION_TYPE] == CONN_CLOUD
    assert config_data["machine_id"] == "m1"


@pytest.mark.asyncio
async def test_diagnostics_includes_all_data_fields():
    """Test that all SystemairData fields are present in diagnostics output."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(return_value={})

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
    )
    sample = make_sample_data()
    coordinator = MockCoordinator(data=sample, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    expected_keys = {
        "target_temperature",
        "supply_air_temperature",
        "outdoor_air_temperature",
        "extract_air_temperature",
        "overheat_temperature",
        "humidity",
        "co2",
        "air_quality",
        "fan_mode",
        "fan_mode_name",
        "saf_rpm",
        "eaf_rpm",
        "saf_speed",
        "eaf_speed",
        "user_mode",
        "user_mode_name",
        "eco_mode",
        "filter_days_left",
        "remaining_time_seconds",
        "heater_output",
        "heater_active",
        "cooler_output",
        "cooler_active",
        "heat_exchanger_type",
        "heat_exchanger_speed",
        "moisture_transfer_enabled",
        "heater_type",
        "heater_position",
        "fan_levels",
        "timed_mode_durations",
        "alarms",
        "functions",
    }
    assert set(result["data"].keys()) == expected_keys


@pytest.mark.asyncio
async def test_diagnostics_cloud_raw_data_redacts_serial():
    """Test that serialNumber is redacted in cloud raw data."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(return_value={
        "device_id": "m1",
        "device_type": "LEGACY",
        "account_devices": [
            {
                "identifier": "m1",
                "name": "Unit",
                "status": {
                    "serialNumber": "SECRET_SN_12345",
                    "model": "VTR300",
                },
            }
        ],
        "device_status": {
            "serialNumber": "SECRET_SN_12345",
            "connectivity": "ONLINE",
        },
    })

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
    )
    sample = make_sample_data()
    coordinator = MockCoordinator(data=sample, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    cloud = result["cloud_raw_data"]
    # serialNumber should be redacted everywhere
    assert cloud["account_devices"][0]["status"]["serialNumber"] == "**REDACTED**"
    assert cloud["device_status"]["serialNumber"] == "**REDACTED**"
    # Other fields should be preserved
    assert cloud["account_devices"][0]["status"]["model"] == "VTR300"
    assert cloud["device_status"]["connectivity"] == "ONLINE"


@pytest.mark.asyncio
async def test_diagnostics_cloud_raw_data_collection_failure():
    """Test diagnostics handles cloud data collection failure gracefully."""
    mock_api = MagicMock()
    mock_api.collect_diagnostics_data = AsyncMock(
        side_effect=Exception("Cloud API down")
    )

    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            "machine_id": "m1",
            "machine_name": "Unit 1",
        },
    )
    sample = make_sample_data()
    coordinator = MockCoordinator(data=sample, api=mock_api)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Diagnostics should still return successfully
    assert "config_entry" in result
    assert "data" in result
    # Cloud raw data should contain error type (not message, to avoid leaking sensitive data)
    assert "Error:" in result["cloud_raw_data"]
    assert "Exception" in result["cloud_raw_data"]


@pytest.mark.asyncio
async def test_diagnostics_non_cloud_no_raw_data():
    """Test that non-cloud connections don't include cloud_raw_data."""
    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: "modbus_tcp",
            "host": "192.168.1.100",
        },
    )
    sample = make_sample_data("modbus_tcp")
    coordinator = MockCoordinator(connection_type="modbus_tcp", data=sample)

    hass = MockHass()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "cloud_raw_data" not in result
