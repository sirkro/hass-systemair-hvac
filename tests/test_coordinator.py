"""Tests for the SystemairCoordinator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.coordinator import (
    EVENT_ALARM_CHANGED,
    EVENT_FUNCTION_CHANGED,
    SystemairCoordinator,
    SystemairData,
    _apply_filter_expiration,
)
from custom_components.systemair.const import (
    CONN_CLOUD,
    DOMAIN,
    FAN_LEVEL_REGISTERS,
    FAN_MODES,
    MODES,
    PARAMETER_MAP,
)
from tests.conftest import (
    make_mock_cloud_api,
    make_sample_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockHass:
    """Minimal mock of HomeAssistant."""

    def __init__(self):
        self.data = {}
        self.loop = None
        self.bus = MagicMock()
        self.bus.async_fire = MagicMock()


# ---------------------------------------------------------------------------
# SystemairData tests
# ---------------------------------------------------------------------------


class TestSystemairData:
    """Tests for the SystemairData container."""

    def test_default_values(self):
        data = SystemairData()
        assert data.target_temperature is None
        assert data.supply_air_temperature is None
        assert data.outdoor_air_temperature is None
        assert data.extract_air_temperature is None
        assert data.overheat_temperature is None
        assert data.humidity is None
        assert data.fan_mode is None
        assert data.fan_mode_name is None
        assert data.saf_rpm is None
        assert data.eaf_rpm is None
        assert data.saf_speed is None
        assert data.eaf_speed is None
        assert data.user_mode is None
        assert data.user_mode_name is None
        assert data.eco_mode is None
        assert data.filter_days_left is None
        assert data.alarms == {}
        assert data.functions == {}
        assert data.connection_type == ""

    def test_populated_values(self):
        data = make_sample_data()
        assert data.target_temperature == 21.0
        assert data.supply_air_temperature == 21.5
        assert data.outdoor_air_temperature == 5.0
        assert data.fan_mode == 3
        assert data.user_mode == 0
        assert data.eco_mode is False
        assert data.filter_days_left == 60


# ---------------------------------------------------------------------------
# Coordinator data parsing tests
# ---------------------------------------------------------------------------


class TestCoordinatorParsing:
    """Test the data parsing logic."""

    def _get_coordinator(self) -> SystemairCoordinator:
        """Create a coordinator for testing parse methods."""
        hass = MockHass()
        api = make_mock_cloud_api()
        # We need to avoid the DataUpdateCoordinator __init__ calling HA internals
        # So we patch it
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_temperature_setpoint(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 21.5}, data)
        assert data.target_temperature == 21.5

    def test_parse_temperatures(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_SENSOR_SAT": 21.5,
            "REG_SENSOR_OAT": 5.3,
            "REG_SENSOR_PDM_EAT_VALUE": 22.1,
            "REG_SENSOR_OHT": 25.0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.supply_air_temperature == 21.5
        assert data.outdoor_air_temperature == 5.3
        assert data.extract_air_temperature == 22.1
        assert data.overheat_temperature == 25.0

    def test_parse_humidity(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_SENSOR_RHS_PDM": 45.0}, data)
        assert data.humidity == 45.0

    def test_parse_fan_mode(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF": 3}, data)
        assert data.fan_mode == 3
        assert data.fan_mode_name == "Normal"

    def test_parse_fan_mode_unknown(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF": 99}, data)
        assert data.fan_mode == 99
        assert data.fan_mode_name == "99"

    def test_parse_fan_rpm_and_speed(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_SENSOR_RPM_SAF": 1200.0,
            "REG_SENSOR_RPM_EAF": 1100.0,
            "REG_OUTPUT_SAF": 65.0,
            "REG_OUTPUT_EAF": 60.0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.saf_rpm == 1200.0
        assert data.eaf_rpm == 1100.0
        assert data.saf_speed == 65.0
        assert data.eaf_speed == 60.0

    def test_parse_user_mode(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_USERMODE_MODE": 0}, data)
        assert data.user_mode == 0
        assert data.user_mode_name == "Auto"

    def test_parse_user_mode_manual(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_USERMODE_MODE": 1}, data)
        assert data.user_mode == 1
        assert data.user_mode_name == "Manual"

    def test_parse_eco_mode(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_ECO_MODE_ON_OFF": 1}, data)
        assert data.eco_mode is True

    def test_parse_eco_mode_off(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_ECO_MODE_ON_OFF": 0}, data)
        assert data.eco_mode is False

    def test_parse_filter_time(self):
        coord = self._get_coordinator()
        data = SystemairData()
        # 60 days = 5,184,000 seconds
        # 5,184,000 = 79 * 65536 + 6656
        raw = {
            "REG_FILTER_REMAINING_TIME_L": 6656,
            "REG_FILTER_REMAINING_TIME_H": 79,
        }
        coord._parse_modbus_data(raw, data)
        assert data.filter_days_left == 60

    def test_parse_filter_time_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_FILTER_REMAINING_TIME_L": 0,
            "REG_FILTER_REMAINING_TIME_H": 0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.filter_days_left == 0

    def test_parse_alarms(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_ALARM_FROST_PROT_ALARM": 2,
            "REG_ALARM_TYPE_A": True,
        }
        # Need to make sure ALARM_PARAMS includes these
        from custom_components.systemair.const import ALARM_PARAMS
        coord._parse_modbus_data(raw, data)
        assert data.alarms["REG_ALARM_FROST_PROT_ALARM"] == 2
        assert data.alarms["REG_ALARM_TYPE_A"] is True

    def test_parse_functions(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_FUNCTION_ACTIVE_PRESSURE_GUARD": 1,
            "REG_SENSOR_DI_COOKERHOOD": 0,
        }
        from custom_components.systemair.const import FUNCTION_PARAMS
        coord._parse_modbus_data(raw, data)
        assert data.functions["REG_FUNCTION_ACTIVE_PRESSURE_GUARD"] is True
        assert data.functions["REG_SENSOR_DI_COOKERHOOD"] is False

    def test_parse_partial_data(self):
        """Test that missing fields stay None."""
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 22.0}, data)
        assert data.target_temperature == 22.0
        assert data.supply_air_temperature is None
        assert data.fan_mode is None


class TestCoordinatorCloudParsing:
    """Cloud now uses _parse_modbus_data (same register-keyed data).

    These tests verify that the cloud coordinator correctly uses
    _parse_modbus_data instead of the removed _parse_cloud_data.
    """

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_cloud_uses_parse_modbus_data(self):
        """Cloud coordinator uses _parse_modbus_data since cloud API
        now returns register-keyed data (same format as Modbus)."""
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_TC_SP": 21.5,
            "REG_SENSOR_SAT": 22.0,
            "REG_SENSOR_OAT": 5.3,
            "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF": 3,
            "REG_USERMODE_MODE": 0,
            "REG_ECO_MODE_ON_OFF": 1,
        }
        coord._parse_modbus_data(raw, data)
        assert data.target_temperature == 21.5
        assert data.supply_air_temperature == 22.0
        assert data.outdoor_air_temperature == 5.3
        assert data.fan_mode == 3
        assert data.fan_mode_name == "Normal"
        assert data.user_mode == 0
        assert data.user_mode_name == "Auto"
        assert data.eco_mode is True

    def test_parse_cloud_data_method_removed(self):
        """Verify that _parse_cloud_data no longer exists on the coordinator."""
        coord = self._get_coordinator()
        assert not hasattr(coord, "_parse_cloud_data")


# ---------------------------------------------------------------------------
# Coordinator write method tests
# ---------------------------------------------------------------------------


class TestCoordinatorWriteCloud:
    """Test coordinator write operations for Cloud.

    Cloud now uses the same unified write path as Modbus/SaveConnect
    (write_param / write_params), since the cloud API maps register
    numbers to data item IDs internally.
    """

    def _get_coordinator(self) -> tuple[SystemairCoordinator, MagicMock]:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
            coord.async_request_refresh = AsyncMock()
        return coord, api

    @pytest.mark.asyncio
    async def test_set_target_temperature(self):
        coord, api = self._get_coordinator()
        await coord.async_set_target_temperature(22.0)
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_TC_SP"
        assert value == 22.0
        coord.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_fan_mode(self):
        coord, api = self._get_coordinator()
        await coord.async_set_fan_mode(4)
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"
        assert value == 4
        coord.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_mode_auto(self):
        coord, api = self._get_coordinator()
        await coord.async_set_mode("auto")
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_USERMODE_HMI_CHANGE_REQUEST"
        assert value == 1

    @pytest.mark.asyncio
    async def test_set_mode_manual(self):
        coord, api = self._get_coordinator()
        await coord.async_set_mode("manual")
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_USERMODE_HMI_CHANGE_REQUEST"
        assert value == 2

    @pytest.mark.asyncio
    async def test_set_eco_mode(self):
        coord, api = self._get_coordinator()
        await coord.async_set_eco_mode(True)
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_ECO_MODE_ON_OFF"
        assert value is True

    @pytest.mark.asyncio
    async def test_set_timed_mode_away(self):
        """Cloud uses batch write_params for timed modes (same as SaveConnect)."""
        coord, api = self._get_coordinator()
        await coord.async_set_timed_mode("away", 24)
        api.write_params.assert_called_once()
        params, values = api.write_params.call_args[0]
        assert len(params) == 2
        assert params[0].short == "REG_USERMODE_AWAY_TIME"
        assert params[1].short == "REG_USERMODE_HMI_CHANGE_REQUEST"
        assert values == [24, 6]

    @pytest.mark.asyncio
    async def test_set_timed_mode_fireplace(self):
        """Cloud uses batch write_params for timed modes."""
        coord, api = self._get_coordinator()
        await coord.async_set_timed_mode("fireplace", 30)
        api.write_params.assert_called_once()
        params, values = api.write_params.call_args[0]
        assert len(params) == 2
        assert params[0].short == "REG_USERMODE_FIREPLACE_TIME"
        assert params[1].short == "REG_USERMODE_HMI_CHANGE_REQUEST"
        assert values == [30, 5]


# ---------------------------------------------------------------------------
# Feature 1: Heater/Cooler output parsing
# ---------------------------------------------------------------------------


class TestCoordinatorHeaterCoolerParsing:
    """Test heater and cooler output parsing."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_heater_output(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y1_ANALOG": 75.5}, data)
        assert data.heater_output == 75.5

    def test_parse_heater_output_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y1_ANALOG": 0}, data)
        assert data.heater_output == 0.0

    def test_parse_heater_active(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y1_DIGITAL": 1}, data)
        assert data.heater_active is True

    def test_parse_heater_inactive(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y1_DIGITAL": 0}, data)
        assert data.heater_active is False

    def test_parse_cooler_output(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y3_ANALOG": 50.0}, data)
        assert data.cooler_output == 50.0

    def test_parse_cooler_output_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y3_ANALOG": 0}, data)
        assert data.cooler_output == 0.0

    def test_parse_cooler_active(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y3_DIGITAL": 1}, data)
        assert data.cooler_active is True

    def test_parse_cooler_inactive(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_OUTPUT_Y3_DIGITAL": 0}, data)
        assert data.cooler_active is False

    def test_parse_heater_cooler_not_present(self):
        """When registers are missing, values stay None."""
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 21.0}, data)
        assert data.heater_output is None
        assert data.heater_active is None
        assert data.cooler_output is None
        assert data.cooler_active is None


# ---------------------------------------------------------------------------
# Feature 1: Cloud heater/cooler parsing
# ---------------------------------------------------------------------------


# Cloud heater/cooler parsing removed — cloud now uses _parse_modbus_data
# which is already tested by TestCoordinatorHeaterCoolerParsing above.


# ---------------------------------------------------------------------------
# Feature 2: Remaining time parsing
# ---------------------------------------------------------------------------


class TestCoordinatorRemainingTimeParsing:
    """Test remaining time parsing for timed modes."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_remaining_time(self):
        coord = self._get_coordinator()
        data = SystemairData()
        # 3600 seconds = 0 * 65536 + 3600
        raw = {
            "REG_USERMODE_REMAINING_TIME_L": 3600,
            "REG_USERMODE_REMAINING_TIME_H": 0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.remaining_time_seconds == 3600

    def test_remaining_time_large(self):
        coord = self._get_coordinator()
        data = SystemairData()
        # 86400 seconds (1 day) = 1 * 65536 + 20864
        raw = {
            "REG_USERMODE_REMAINING_TIME_L": 20864,
            "REG_USERMODE_REMAINING_TIME_H": 1,
        }
        coord._parse_modbus_data(raw, data)
        assert data.remaining_time_seconds == 86400

    def test_remaining_time_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_USERMODE_REMAINING_TIME_L": 0,
            "REG_USERMODE_REMAINING_TIME_H": 0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.remaining_time_seconds == 0

    def test_remaining_time_partial_missing(self):
        """If only one register is present, remaining_time stays None."""
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_USERMODE_REMAINING_TIME_L": 500}, data)
        assert data.remaining_time_seconds is None


# ---------------------------------------------------------------------------
# Feature 4: Fan levels parsing
# ---------------------------------------------------------------------------


class TestCoordinatorFanLevelsParsing:
    """Test per-mode fan level parsing."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_fan_levels(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF": 4,
            "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF": 3,
            "REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF": 2,
        }
        coord._parse_modbus_data(raw, data)
        assert data.fan_levels["REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF"] == 4
        assert data.fan_levels["REG_USERMODE_CROWDED_AIRFLOW_LEVEL_EAF"] == 3
        assert data.fan_levels["REG_USERMODE_AWAY_AIRFLOW_LEVEL_SAF"] == 2

    def test_parse_all_fan_levels(self):
        """All 16 fan level registers should be parsed when present."""
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {reg_short: i + 1 for i, (reg_short, _, _) in enumerate(FAN_LEVEL_REGISTERS)}
        coord._parse_modbus_data(raw, data)
        assert len(data.fan_levels) == 16
        for i, (reg_short, _, _) in enumerate(FAN_LEVEL_REGISTERS):
            assert data.fan_levels[reg_short] == i + 1

    def test_parse_no_fan_levels(self):
        """Fan levels dict stays empty when no registers are present."""
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 21.0}, data)
        assert data.fan_levels == {}


# ---------------------------------------------------------------------------
# Feature 3: Event firing on alarm/function state changes
# ---------------------------------------------------------------------------


class TestCoordinatorEventFiring:
    """Test _fire_state_change_events."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
            coord.data = None
        return coord

    def test_no_event_on_first_update(self):
        """No events should fire when there is no previous data."""
        coord = self._get_coordinator()
        coord.data = None
        new_data = make_sample_data()
        coord._fire_state_change_events(new_data)
        coord.hass.bus.async_fire.assert_not_called()

    def test_alarm_change_fires_event(self):
        """An alarm state change should fire EVENT_ALARM_CHANGED."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {"REG_ALARM_FILTER_ALARM": 0}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_FILTER_ALARM": 2}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_called_once()
        event_type, event_data = coord.hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_ALARM_CHANGED
        assert event_data["alarm_id"] == "REG_ALARM_FILTER_ALARM"
        assert event_data["old_state"] == 0
        assert event_data["new_state"] == 2
        assert event_data["is_active"] is True

    def test_alarm_clear_fires_event(self):
        """Alarm going from active to inactive should fire with is_active=False."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {"REG_ALARM_FILTER_ALARM": 2}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_FILTER_ALARM": 0}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_called_once()
        event_data = coord.hass.bus.async_fire.call_args[0][1]
        assert event_data["is_active"] is False

    def test_alarm_bool_change_fires_event(self):
        """Boolean alarm changing from False to True should fire event."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {"REG_ALARM_TYPE_A": False}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_TYPE_A": True}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_called_once()
        event_data = coord.hass.bus.async_fire.call_args[0][1]
        assert event_data["is_active"] is True

    def test_no_event_when_alarm_unchanged(self):
        """No event when alarm values haven't changed."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {"REG_ALARM_FILTER_ALARM": 0}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_FILTER_ALARM": 0}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_not_called()

    def test_no_event_for_new_alarm_key(self):
        """No event when an alarm key is new (not in previous data)."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_FILTER_ALARM": 2}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_not_called()

    def test_function_change_fires_event(self):
        """A function state change should fire EVENT_FUNCTION_CHANGED."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.functions = {"REG_FUNCTION_ACTIVE_PRESSURE_GUARD": False}
        coord.data = prev

        new_data = make_sample_data()
        new_data.functions = {"REG_FUNCTION_ACTIVE_PRESSURE_GUARD": True}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_called_once()
        event_type, event_data = coord.hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_FUNCTION_CHANGED
        assert event_data["function_id"] == "REG_FUNCTION_ACTIVE_PRESSURE_GUARD"
        assert event_data["old_state"] is False
        assert event_data["new_state"] is True
        assert event_data["is_active"] is True

    def test_function_deactivation_fires_event(self):
        """Function going from active to inactive fires event."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.functions = {"REG_SENSOR_DI_COOKERHOOD": True}
        coord.data = prev

        new_data = make_sample_data()
        new_data.functions = {"REG_SENSOR_DI_COOKERHOOD": False}
        coord._fire_state_change_events(new_data)

        coord.hass.bus.async_fire.assert_called_once()
        event_data = coord.hass.bus.async_fire.call_args[0][1]
        assert event_data["is_active"] is False

    def test_multiple_changes_fire_multiple_events(self):
        """Multiple alarm + function changes fire multiple events."""
        coord = self._get_coordinator()
        prev = make_sample_data()
        prev.alarms = {"REG_ALARM_FILTER_ALARM": 0, "REG_ALARM_TYPE_A": False}
        prev.functions = {"REG_FUNCTION_ACTIVE_PRESSURE_GUARD": False}
        coord.data = prev

        new_data = make_sample_data()
        new_data.alarms = {"REG_ALARM_FILTER_ALARM": 2, "REG_ALARM_TYPE_A": True}
        new_data.functions = {"REG_FUNCTION_ACTIVE_PRESSURE_GUARD": True}
        coord._fire_state_change_events(new_data)

        # 2 alarm changes + 1 function change = 3 events
        assert coord.hass.bus.async_fire.call_count == 3


# ---------------------------------------------------------------------------
# Feature 4: async_set_fan_level write tests
# ---------------------------------------------------------------------------


class TestCoordinatorSetFanLevelCloud:
    """Test async_set_fan_level for Cloud connection.

    Cloud now supports per-mode fan levels via write_param
    (same behavior as Modbus/SaveConnect).
    """

    def _get_coordinator(self) -> tuple[SystemairCoordinator, MagicMock]:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
            coord.async_request_refresh = AsyncMock()
        return coord, api

    @pytest.mark.asyncio
    async def test_set_fan_level_writes_param(self):
        """Cloud now writes per-mode fan levels via write_param."""
        coord, api = self._get_coordinator()
        await coord.async_set_fan_level("REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF", 4)
        api.write_param.assert_called_once()
        param, value = api.write_param.call_args[0]
        assert param.short == "REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF"
        assert value == 4
        coord.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_fan_level_unknown_register(self):
        """Unknown register should log error and not write."""
        coord, api = self._get_coordinator()
        await coord.async_set_fan_level("REG_NONEXISTENT", 3)
        api.write_param.assert_not_called()
        coord.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_fan_level_below_min(self):
        """Value below min should be rejected."""
        coord, api = self._get_coordinator()
        await coord.async_set_fan_level("REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF", 1)
        api.write_param.assert_not_called()
        coord.async_request_refresh.assert_not_called()


# ---------------------------------------------------------------------------
# SystemairData default values for new fields
# ---------------------------------------------------------------------------


class TestSystemairDataNewFields:
    """Test default values for the new SystemairData fields."""

    def test_heater_cooler_defaults(self):
        data = SystemairData()
        assert data.heater_output is None
        assert data.heater_active is None
        assert data.cooler_output is None
        assert data.cooler_active is None

    def test_remaining_time_default(self):
        data = SystemairData()
        assert data.remaining_time_seconds is None

    def test_fan_levels_default(self):
        data = SystemairData()
        assert data.fan_levels == {}

    def test_populated_new_fields(self):
        data = make_sample_data()
        assert data.heater_output == 0.0
        assert data.heater_active is False
        assert data.cooler_output == 0.0
        assert data.cooler_active is False
        assert data.remaining_time_seconds == 0
        assert len(data.fan_levels) == 16


# ---------------------------------------------------------------------------
# Cloud-specific: _apply_device_status
# ---------------------------------------------------------------------------


class TestApplyDeviceStatus:
    """Test _apply_device_status static method."""

    def test_temperature(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"temperature": 21.5}, op_data
        )
        assert op_data["REG_SENSOR_SAT"] == 21.5

    def test_user_mode(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"userMode": 1}, op_data
        )
        assert op_data["REG_USERMODE_MODE"] == 1

    def test_humidity(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"humidity": 51}, op_data
        )
        assert op_data["REG_SENSOR_RHS_PDM"] == 51

    def test_filter_expiration_iso_date(self):
        op_data: dict = {}
        # Use a date far in the future to ensure positive result
        SystemairCoordinator._apply_device_status(
            {"filterExpiration": "2027-01-01"}, op_data
        )
        assert "REG_FILTER_REMAINING_TIME_L" in op_data
        assert "REG_FILTER_REMAINING_TIME_H" in op_data
        # Should be > 0 days
        total_sec = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total_sec > 0

    def test_none_values_ignored(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"temperature": None, "userMode": None, "humidity": None, "filterExpiration": None},
            op_data,
        )
        assert op_data == {}

    def test_missing_keys_no_op(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status({}, op_data)
        assert op_data == {}

    def test_all_fields_together(self):
        op_data: dict = {"REG_TC_SP": 21.0}  # pre-existing key preserved
        SystemairCoordinator._apply_device_status(
            {"temperature": 16.3, "userMode": 0, "humidity": 45, "filterExpiration": 90},
            op_data,
        )
        assert op_data["REG_TC_SP"] == 21.0  # untouched
        assert op_data["REG_SENSOR_SAT"] == 16.3
        assert op_data["REG_USERMODE_MODE"] == 0
        assert op_data["REG_SENSOR_RHS_PDM"] == 45

    def test_does_not_overwrite_register_based_sat(self):
        """Register-based sensor values should not be overwritten by GetDeviceStatus."""
        op_data: dict = {"REG_SENSOR_SAT": 17.9}  # from read_params
        SystemairCoordinator._apply_device_status(
            {"temperature": 17.1}, op_data
        )
        assert op_data["REG_SENSOR_SAT"] == 17.9  # register value preserved

    def test_does_not_overwrite_register_based_humidity(self):
        """Register-based humidity should not be overwritten by GetDeviceStatus."""
        op_data: dict = {"REG_SENSOR_RHS_PDM": 59}  # from read_params
        SystemairCoordinator._apply_device_status(
            {"humidity": 49}, op_data
        )
        assert op_data["REG_SENSOR_RHS_PDM"] == 59  # register value preserved

    def test_does_not_overwrite_register_based_user_mode(self):
        """Register-based user mode should not be overwritten by GetDeviceStatus."""
        op_data: dict = {"REG_USERMODE_MODE": 1}  # from read_params
        SystemairCoordinator._apply_device_status(
            {"userMode": 0}, op_data
        )
        assert op_data["REG_USERMODE_MODE"] == 1  # register value preserved

    def test_co2_always_set(self):
        """CO2 has no register source, so it should always be set."""
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"co2": 450}, op_data
        )
        assert op_data["_CO2"] == 450


# ---------------------------------------------------------------------------
# Cloud-specific: _apply_ws_status
# ---------------------------------------------------------------------------


class TestApplyWsStatus:
    """Test _apply_ws_status static method."""

    def test_basic_temperature(self):
        op_data: dict = {}
        ws_data = {"properties": {"temperature": 16.3}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_SENSOR_SAT"] == 16.3

    def test_nested_temperatures(self):
        op_data: dict = {}
        ws_data = {
            "properties": {
                "temperatures": {"oat": 9.6, "sat": 16.3, "setpoint": 18.0}
            }
        }
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_SENSOR_SAT"] == 16.3
        assert op_data["REG_SENSOR_OAT"] == 9.6
        assert op_data["REG_TC_SP"] == 18.0

    def test_user_mode(self):
        op_data: dict = {}
        ws_data = {"properties": {"userMode": 1}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_USERMODE_MODE"] == 1

    def test_humidity(self):
        op_data: dict = {}
        ws_data = {"properties": {"humidity": 51}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_SENSOR_RHS_PDM"] == 51

    def test_airflow(self):
        op_data: dict = {}
        ws_data = {"properties": {"airflow": 3}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"] == 3

    def test_none_values_ignored(self):
        op_data: dict = {}
        ws_data = {
            "properties": {
                "temperature": None,
                "userMode": None,
                "humidity": None,
                "airflow": None,
            }
        }
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data == {}

    def test_flat_data_without_properties_key(self):
        """_apply_ws_status falls back to ws_data itself if 'properties' missing."""
        op_data: dict = {}
        ws_data = {"temperature": 16.3, "humidity": 51}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_SENSOR_SAT"] == 16.3
        assert op_data["REG_SENSOR_RHS_PDM"] == 51

    def test_sat_from_nested_overrides_top_level_temperature(self):
        """Nested temperatures.sat should override the top-level temperature."""
        op_data: dict = {}
        ws_data = {
            "properties": {
                "temperature": 15.0,
                "temperatures": {"sat": 16.3},
            }
        }
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        # sat=16.3 is set after temperature=15.0, so it should win
        assert op_data["REG_SENSOR_SAT"] == 16.3

    def test_full_ws_message(self):
        """Test with a realistic full WS message."""
        op_data: dict = {}
        ws_data = {
            "action": "DEVICE_STATUS_UPDATE",
            "type": "SYSTEM_EVENT",
            "properties": {
                "id": "IAM_24800001239C",
                "temperature": 16.3,
                "airflow": 3,
                "humidity": 51,
                "co2": 0,
                "userMode": 1,
                "temperatures": {"oat": 9.6, "sat": 16.3, "setpoint": 18},
                "versions": [
                    {"type": "mb", "version": "1.22.0"},
                    {"type": "iam", "version": "2.4.0"},
                ],
            },
        }
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["REG_SENSOR_SAT"] == 16.3
        assert op_data["REG_SENSOR_OAT"] == 9.6
        assert op_data["REG_TC_SP"] == 18
        assert op_data["REG_USERMODE_MODE"] == 1
        assert op_data["REG_SENSOR_RHS_PDM"] == 51
        assert op_data["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"] == 3


# ---------------------------------------------------------------------------
# Cloud-specific: _apply_filter_expiration (module-level function)
# ---------------------------------------------------------------------------


class TestApplyFilterExpiration:
    """Test the _apply_filter_expiration helper."""

    def test_iso_date_future(self):
        op_data: dict = {}
        _apply_filter_expiration("2027-01-01", op_data)
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total > 0

    def test_iso_date_past(self):
        op_data: dict = {}
        _apply_filter_expiration("2020-01-01", op_data)
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total == 0

    def test_numeric_days(self):
        op_data: dict = {}
        _apply_filter_expiration(90, op_data)  # 90 days
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total == 90 * 86400

    def test_numeric_seconds_large_value(self):
        op_data: dict = {}
        _apply_filter_expiration(5184000, op_data)  # 60 days in seconds (> 1000)
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total == 5184000

    def test_none(self):
        op_data: dict = {}
        _apply_filter_expiration(None, op_data)
        assert "REG_FILTER_REMAINING_TIME_L" not in op_data
        assert "REG_FILTER_REMAINING_TIME_H" not in op_data

    def test_numeric_string_days(self):
        op_data: dict = {}
        _apply_filter_expiration("90", op_data)  # numeric string
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total == 90 * 86400

    def test_invalid_string(self):
        op_data: dict = {}
        _apply_filter_expiration("not-a-date", op_data)
        assert "REG_FILTER_REMAINING_TIME_L" not in op_data

    def test_float_days(self):
        op_data: dict = {}
        _apply_filter_expiration(30.5, op_data)  # < 1000, treated as days
        total = op_data["REG_FILTER_REMAINING_TIME_L"] + op_data["REG_FILTER_REMAINING_TIME_H"] * 65536
        assert total == 30 * 86400  # int(30.5) = 30

    def test_low_high_split(self):
        """Verify low/high 16-bit split is correct."""
        op_data: dict = {}
        _apply_filter_expiration(1, op_data)  # 1 day = 86400 sec
        low = op_data["REG_FILTER_REMAINING_TIME_L"]
        high = op_data["REG_FILTER_REMAINING_TIME_H"]
        assert low == 86400 & 0xFFFF
        assert high == (86400 >> 16) & 0xFFFF
        assert low + high * 65536 == 86400


# ---------------------------------------------------------------------------
# Cloud-specific: _carry_forward_sensors
# ---------------------------------------------------------------------------


class TestCarryForwardSensors:
    """Test _carry_forward_sensors static method."""

    def test_carries_all_sensor_fields(self):
        prev = make_sample_data()
        data = SystemairData()
        SystemairCoordinator._carry_forward_sensors(prev, data)
        assert data.supply_air_temperature == prev.supply_air_temperature
        assert data.outdoor_air_temperature == prev.outdoor_air_temperature
        assert data.extract_air_temperature == prev.extract_air_temperature
        assert data.overheat_temperature == prev.overheat_temperature
        assert data.humidity == prev.humidity
        assert data.saf_rpm == prev.saf_rpm
        assert data.eaf_rpm == prev.eaf_rpm
        assert data.saf_speed == prev.saf_speed
        assert data.eaf_speed == prev.eaf_speed

    def test_carries_none_values(self):
        prev = SystemairData()  # all None
        data = SystemairData()
        data.supply_air_temperature = 99.9  # will be overwritten
        SystemairCoordinator._carry_forward_sensors(prev, data)
        assert data.supply_air_temperature is None


# ---------------------------------------------------------------------------
# Cloud-specific: _on_ws_message
# ---------------------------------------------------------------------------


class TestOnWsMessage:
    """Test the _on_ws_message callback."""

    def _get_cloud_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord._ws_data = {}
            coord.logger = MagicMock()
            coord.hass = hass
            coord.async_request_refresh = AsyncMock()
        return coord

    @pytest.mark.asyncio
    async def test_stores_device_status_update(self):
        coord = self._get_cloud_coordinator()
        msg = {
            "action": "DEVICE_STATUS_UPDATE",
            "properties": {"temperature": 16.3, "humidity": 51},
        }
        await coord._on_ws_message(msg)
        assert coord._ws_data == msg
        coord.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_non_status_update(self):
        coord = self._get_cloud_coordinator()
        msg = {"action": "SOMETHING_ELSE", "data": {}}
        await coord._on_ws_message(msg)
        assert coord._ws_data == {}
        coord.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_overwrites_previous_ws_data(self):
        coord = self._get_cloud_coordinator()
        msg1 = {
            "action": "DEVICE_STATUS_UPDATE",
            "properties": {"temperature": 15.0},
        }
        msg2 = {
            "action": "DEVICE_STATUS_UPDATE",
            "properties": {"temperature": 16.3},
        }
        await coord._on_ws_message(msg1)
        await coord._on_ws_message(msg2)
        assert coord._ws_data["properties"]["temperature"] == 16.3
        assert coord.async_request_refresh.call_count == 2


# ---------------------------------------------------------------------------
# Cloud-specific: async_start_cloud_websocket
# ---------------------------------------------------------------------------


class TestAsyncStartCloudWebsocket:
    """Test async_start_cloud_websocket method."""

    def _get_coordinator(self, connection_type: str = CONN_CLOUD) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = connection_type
            coord.api = api
            coord._poll_count = 0
            coord._ws_data = {}
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    @pytest.mark.asyncio
    async def test_calls_connect_websocket_for_cloud(self):
        coord = self._get_coordinator(CONN_CLOUD)
        await coord.async_start_cloud_websocket()
        coord.api.connect_websocket.assert_called_once()
        # Callback should be _on_ws_message
        call_kwargs = coord.api.connect_websocket.call_args
        assert call_kwargs[1]["callback"] == coord._on_ws_message

    @pytest.mark.asyncio
    async def test_handles_connect_failure(self):
        coord = self._get_coordinator(CONN_CLOUD)
        coord.api.connect_websocket = AsyncMock(side_effect=Exception("WS error"))
        # Should not raise
        await coord.async_start_cloud_websocket()


# ---------------------------------------------------------------------------
# Diagnostic register parsing tests
# ---------------------------------------------------------------------------


class TestCoordinatorDiagnosticParsing:
    """Test diagnostic register parsing in _parse_modbus_data."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_heat_exchanger_type_rotating(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEAT_EXCHANGER_TYPE": 0}, data)
        assert data.heat_exchanger_type == "Rotating"

    def test_parse_heat_exchanger_type_plate(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEAT_EXCHANGER_TYPE": 1}, data)
        assert data.heat_exchanger_type == "Plate"

    def test_parse_heat_exchanger_type_unknown(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEAT_EXCHANGER_TYPE": 99}, data)
        assert data.heat_exchanger_type == "99"

    def test_parse_heat_exchanger_speed(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEAT_EXCHANGER_SPEED": 60}, data)
        assert data.heat_exchanger_speed == 60

    def test_parse_heat_exchanger_speed_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEAT_EXCHANGER_SPEED": 0}, data)
        assert data.heat_exchanger_speed == 0

    def test_parse_moisture_transfer_enabled(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_MOISTURE_TRANSFER_ON_OFF": 1}, data)
        assert data.moisture_transfer_enabled is True

    def test_parse_moisture_transfer_disabled(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_MOISTURE_TRANSFER_ON_OFF": 0}, data)
        assert data.moisture_transfer_enabled is False

    def test_parse_heater_type_electrical(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_TYPE": 1}, data)
        assert data.heater_type == "Electrical"

    def test_parse_heater_type_none(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_TYPE": 0}, data)
        assert data.heater_type == "None"

    def test_parse_heater_type_water(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_TYPE": 2}, data)
        assert data.heater_type == "Water"

    def test_parse_heater_type_change_over(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_TYPE": 3}, data)
        assert data.heater_type == "Change Over"

    def test_parse_heater_type_unknown(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_TYPE": 99}, data)
        assert data.heater_type == "99"

    def test_parse_heater_position_supply(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_POSITION": 0}, data)
        assert data.heater_position == "Supply"

    def test_parse_heater_position_extract(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_POSITION": 1}, data)
        assert data.heater_position == "Extract"

    def test_parse_heater_position_unknown(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_HEATER_POSITION": 99}, data)
        assert data.heater_position == "99"

    def test_parse_all_diagnostics_together(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_HEAT_EXCHANGER_TYPE": 0,
            "REG_HEAT_EXCHANGER_SPEED": 60,
            "REG_MOISTURE_TRANSFER_ON_OFF": 0,
            "REG_HEATER_TYPE": 1,
            "REG_HEATER_POSITION": 0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.heat_exchanger_type == "Rotating"
        assert data.heat_exchanger_speed == 60
        assert data.moisture_transfer_enabled is False
        assert data.heater_type == "Electrical"
        assert data.heater_position == "Supply"

    def test_diagnostics_not_present(self):
        """When diagnostic registers are missing, values stay None."""
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 21.0}, data)
        assert data.heat_exchanger_type is None
        assert data.heat_exchanger_speed is None
        assert data.moisture_transfer_enabled is None
        assert data.heater_type is None
        assert data.heater_position is None


# ---------------------------------------------------------------------------
# Air quality parsing tests
# ---------------------------------------------------------------------------


class TestCoordinatorAirQualityParsing:
    """Test air quality synthetic key parsing."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_air_quality(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"_AIR_QUALITY": 3}, data)
        assert data.air_quality == 3

    def test_parse_air_quality_zero(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"_AIR_QUALITY": 0}, data)
        assert data.air_quality == 0

    def test_air_quality_not_present(self):
        coord = self._get_coordinator()
        data = SystemairData()
        coord._parse_modbus_data({"REG_TC_SP": 21.0}, data)
        assert data.air_quality is None


# ---------------------------------------------------------------------------
# Function active register parsing tests
# ---------------------------------------------------------------------------


class TestCoordinatorFunctionActiveParsing:
    """Test function active register parsing."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_parse_all_function_registers(self):
        """All FUNCTION_PARAMS should be parsed into data.functions."""
        from custom_components.systemair.const import FUNCTION_PARAMS
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {param.short: 1 for param in FUNCTION_PARAMS}
        coord._parse_modbus_data(raw, data)
        for param in FUNCTION_PARAMS:
            assert data.functions[param.short] is True

    def test_parse_function_false_values(self):
        from custom_components.systemair.const import FUNCTION_PARAMS
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {param.short: 0 for param in FUNCTION_PARAMS}
        coord._parse_modbus_data(raw, data)
        for param in FUNCTION_PARAMS:
            assert data.functions[param.short] is False

    def test_parse_function_mixed_values(self):
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "REG_FUNCTION_ACTIVE_HEATING": 1,
            "REG_FUNCTION_ACTIVE_COOLING": 0,
            "REG_FUNCTION_ACTIVE_HEAT_RECOVERY": 1,
            "REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER": 1,
            "REG_FUNCTION_ACTIVE_DEFROSTING": 0,
        }
        coord._parse_modbus_data(raw, data)
        assert data.functions["REG_FUNCTION_ACTIVE_HEATING"] is True
        assert data.functions["REG_FUNCTION_ACTIVE_COOLING"] is False
        assert data.functions["REG_FUNCTION_ACTIVE_HEAT_RECOVERY"] is True
        assert data.functions["REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER"] is True
        assert data.functions["REG_FUNCTION_ACTIVE_DEFROSTING"] is False

    def test_function_count_matches(self):
        """FUNCTION_PARAMS should have 19 entries (17 function + 2 DI)."""
        from custom_components.systemair.const import FUNCTION_PARAMS
        assert len(FUNCTION_PARAMS) == 19


# ---------------------------------------------------------------------------
# _apply_device_status with airQuality
# ---------------------------------------------------------------------------


class TestApplyDeviceStatusAirQuality:
    """Test _apply_device_status handling of airQuality field."""

    def test_air_quality_set(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"airQuality": 3}, op_data
        )
        assert op_data["_AIR_QUALITY"] == 3

    def test_air_quality_zero(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"airQuality": 0}, op_data
        )
        assert op_data["_AIR_QUALITY"] == 0

    def test_air_quality_none_ignored(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status(
            {"airQuality": None}, op_data
        )
        assert "_AIR_QUALITY" not in op_data

    def test_air_quality_missing_ignored(self):
        op_data: dict = {}
        SystemairCoordinator._apply_device_status({}, op_data)
        assert "_AIR_QUALITY" not in op_data


# ---------------------------------------------------------------------------
# _apply_ws_status with airQuality
# ---------------------------------------------------------------------------


class TestApplyWsStatusAirQuality:
    """Test _apply_ws_status handling of airQuality field."""

    def test_air_quality_from_ws(self):
        op_data: dict = {}
        ws_data = {"properties": {"airQuality": 2}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_AIR_QUALITY"] == 2

    def test_air_quality_zero_from_ws(self):
        op_data: dict = {}
        ws_data = {"properties": {"airQuality": 0}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_AIR_QUALITY"] == 0

    def test_air_quality_none_from_ws(self):
        op_data: dict = {}
        ws_data = {"properties": {"airQuality": None}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert "_AIR_QUALITY" not in op_data

    def test_air_quality_missing_from_ws(self):
        op_data: dict = {}
        ws_data = {"properties": {"temperature": 16.3}}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert "_AIR_QUALITY" not in op_data

    def test_full_ws_with_air_quality(self):
        """Test a full WS message with airQuality."""
        op_data: dict = {}
        ws_data = {
            "action": "DEVICE_STATUS_UPDATE",
            "type": "SYSTEM_EVENT",
            "properties": {
                "id": "IAM_24800001239C",
                "temperature": 17.1,
                "airflow": 3,
                "humidity": 49,
                "co2": 0,
                "userMode": 1,
                "airQuality": 0,
                "temperatures": {"oat": 8.5, "sat": 17.1, "setpoint": 18},
            },
        }
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_AIR_QUALITY"] == 0
        assert op_data["_CO2"] == 0
        assert op_data["REG_SENSOR_SAT"] == 17.1
        assert op_data["REG_SENSOR_OAT"] == 8.5
        assert op_data["REG_TC_SP"] == 18
        assert op_data["REG_USERMODE_MODE"] == 1
        assert op_data["REG_SENSOR_RHS_PDM"] == 49
        assert op_data["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"] == 3


# ---------------------------------------------------------------------------
# SystemairData defaults for new fields
# ---------------------------------------------------------------------------


class TestSystemairDataDiagnosticDefaults:
    """Test default values for the new diagnostic/air quality fields."""

    def test_diagnostic_defaults(self):
        data = SystemairData()
        assert data.heat_exchanger_type is None
        assert data.heat_exchanger_speed is None
        assert data.moisture_transfer_enabled is None
        assert data.heater_type is None
        assert data.heater_position is None

    def test_air_quality_default(self):
        data = SystemairData()
        assert data.air_quality is None

    def test_populated_diagnostic_fields(self):
        data = make_sample_data()
        assert data.heat_exchanger_type == "Rotating"
        assert data.heat_exchanger_speed == 60
        assert data.moisture_transfer_enabled is False
        assert data.heater_type == "Electrical"
        assert data.heater_position == "Supply"

    def test_populated_air_quality(self):
        data = make_sample_data()
        assert data.air_quality == 0

    def test_populated_functions_count(self):
        """make_sample_data should have all 19 function entries."""
        data = make_sample_data()
        assert len(data.functions) == 19


# ---------------------------------------------------------------------------
# _carry_forward_sensors includes air_quality
# ---------------------------------------------------------------------------


class TestCarryForwardSensorsAirQuality:
    """Test _carry_forward_sensors carries air_quality."""

    def test_carries_air_quality(self):
        prev = make_sample_data()
        prev.air_quality = 5
        data = SystemairData()
        SystemairCoordinator._carry_forward_sensors(prev, data)
        assert data.air_quality == 5

    def test_carries_air_quality_none(self):
        prev = SystemairData()
        data = SystemairData()
        data.air_quality = 99
        SystemairCoordinator._carry_forward_sensors(prev, data)
        assert data.air_quality is None


# ---------------------------------------------------------------------------
# _async_update_data error handling (ConfigEntryAuthFailed)
# ---------------------------------------------------------------------------


class TestAsyncUpdateDataErrors:
    """Test error handling in _async_update_data."""

    def _get_coordinator(self) -> SystemairCoordinator:
        """Create a coordinator for testing _async_update_data."""
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
            coord.data = None
            coord._ws_data = {}
        return coord

    @pytest.mark.asyncio
    async def test_update_failed_reraised(self):
        """UpdateFailed exceptions should be re-raised as-is."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._get_coordinator()
        coord.api.read_params = AsyncMock(
            side_effect=UpdateFailed("API unreachable")
        )

        with pytest.raises(UpdateFailed, match="API unreachable"):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_config_entry_auth_failed_reraised(self):
        """ConfigEntryAuthFailed exceptions should be re-raised as-is."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = self._get_coordinator()
        coord.api.read_params = AsyncMock(
            side_effect=ConfigEntryAuthFailed("Token expired")
        )

        with pytest.raises(ConfigEntryAuthFailed, match="Token expired"):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_authentication_error_wrapped(self):
        """Direct AuthenticationError should be wrapped in ConfigEntryAuthFailed."""
        from custom_components.systemair.cloud_api import AuthenticationError
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = self._get_coordinator()
        coord.api.read_params = AsyncMock(
            side_effect=AuthenticationError("Invalid credentials")
        )

        with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_exception_with_auth_cause_wrapped(self):
        """Exception with __cause__ being AuthenticationError should be wrapped."""
        from custom_components.systemair.cloud_api import AuthenticationError
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = self._get_coordinator()

        auth_err = AuthenticationError("session expired")
        wrapper_err = RuntimeError("API call failed")
        wrapper_err.__cause__ = auth_err

        coord.api.read_params = AsyncMock(side_effect=wrapper_err)

        with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped_as_update_failed(self):
        """Generic exceptions should be wrapped in UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._get_coordinator()
        coord.api.read_params = AsyncMock(
            side_effect=RuntimeError("Network timeout")
        )

        with pytest.raises(UpdateFailed, match="Error communicating with Systemair"):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_unknown_connection_type_raises_update_failed(self):
        """Unknown connection_type should raise UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._get_coordinator()
        coord.connection_type = "modbus"  # not implemented

        with pytest.raises(UpdateFailed, match="Unknown connection type"):
            await coord._async_update_data()


# ---------------------------------------------------------------------------
# _apply_ws_status alarm parsing
# ---------------------------------------------------------------------------


class TestApplyWsStatusAlarms:
    """Test alarm parsing in _apply_ws_status."""

    def test_alarm_bool_true(self):
        """Boolean True alarm should be stored as True."""
        ws_data = {"properties": {"alarm_co2_state": True}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is True

    def test_alarm_bool_false(self):
        """Boolean False alarm should be stored as False."""
        ws_data = {"properties": {"alarm_co2_state": False}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_str_active(self):
        """String 'active' should be parsed as True."""
        ws_data = {"properties": {"alarm_filter_state": "active"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_filter_state"] is True

    def test_alarm_str_inactive(self):
        """String 'inactive' should be parsed as False."""
        ws_data = {"properties": {"alarm_filter_state": "inactive"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_filter_state"] is False

    def test_alarm_str_zero(self):
        """String '0' should be parsed as False."""
        ws_data = {"properties": {"alarm_co2_state": "0"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_str_false(self):
        """String 'false' should be parsed as False."""
        ws_data = {"properties": {"alarm_co2_state": "false"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_str_empty(self):
        """Empty string should be parsed as False."""
        ws_data = {"properties": {"alarm_co2_state": ""}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_str_case_insensitive(self):
        """'INACTIVE' (uppercase) should be parsed as False."""
        ws_data = {"properties": {"alarm_co2_state": "INACTIVE"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_str_1(self):
        """String '1' should be parsed as True (not in inactive list)."""
        ws_data = {"properties": {"alarm_co2_state": "1"}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is True

    def test_alarm_int_truthy(self):
        """Integer 1 (not bool, not str) should be stored as bool(1)=True."""
        ws_data = {"properties": {"alarm_co2_state": 1}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is True

    def test_alarm_int_zero(self):
        """Integer 0 (not bool, not str) should be stored as bool(0)=False."""
        ws_data = {"properties": {"alarm_co2_state": 0}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is False

    def test_alarm_not_in_props_skipped(self):
        """Alarm IDs not present in WS data should not be stored."""
        ws_data = {"properties": {"temperature": 21.5}}
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        # No _ALARM_ keys should exist
        alarm_keys = [k for k in op_data if k.startswith("_ALARM_")]
        assert alarm_keys == []

    def test_multiple_alarms_in_one_update(self):
        """Multiple alarm properties in a single WS update."""
        ws_data = {
            "properties": {
                "alarm_co2_state": "active",
                "alarm_filter_state": "inactive",
                "alarm_fire_alarm_state": True,
            }
        }
        op_data: dict[str, Any] = {}
        SystemairCoordinator._apply_ws_status(ws_data, op_data)
        assert op_data["_ALARM_alarm_co2_state"] is True
        assert op_data["_ALARM_alarm_filter_state"] is False
        assert op_data["_ALARM_alarm_fire_alarm_state"] is True


# ---------------------------------------------------------------------------
# Cloud alarm keys flow from _apply_ws_status through _parse_modbus_data
# ---------------------------------------------------------------------------


class TestCloudAlarmKeysParsing:
    """Test that _ALARM_ keys from WS data flow into data.alarms."""

    def _get_coordinator(self) -> SystemairCoordinator:
        hass = MockHass()
        api = make_mock_cloud_api()
        with patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = SystemairCoordinator.__new__(SystemairCoordinator)
            coord.connection_type = CONN_CLOUD
            coord.api = api
            coord._poll_count = 0
            coord.logger = MagicMock()
            coord.hass = hass
        return coord

    def test_alarm_keys_stored_in_data_alarms(self):
        """_ALARM_{id} keys in raw data should be copied into data.alarms."""
        coord = self._get_coordinator()
        data = SystemairData()
        raw = {
            "_ALARM_alarm_co2_state": True,
            "_ALARM_alarm_filter_state": False,
        }
        coord._parse_modbus_data(raw, data)
        assert data.alarms["alarm_co2_state"] is True
        assert data.alarms["alarm_filter_state"] is False

    def test_alarm_keys_not_overwritten_by_missing(self):
        """Only present _ALARM_ keys should be written."""
        coord = self._get_coordinator()
        data = SystemairData()
        data.alarms = {"alarm_co2_state": True}
        raw: dict[str, Any] = {}  # No alarm keys
        coord._parse_modbus_data(raw, data)
        # Pre-existing alarm should remain since it wasn't overwritten
        assert data.alarms["alarm_co2_state"] is True


# ---------------------------------------------------------------------------
# Phase 8 quality fix tests
# ---------------------------------------------------------------------------


class TestDeadCodeRemoved:
    """Tests verifying dead code was removed (#27/#28)."""

    def test_coordinator_has_no_ws_task_attribute(self):
        """coordinator._ws_task was dead code and should be removed."""
        assert not hasattr(SystemairCoordinator, "_ws_task")

    def test_coordinator_does_not_import_cloud_unavailable_sensors(self):
        """CLOUD_UNAVAILABLE_SENSORS import was unused in coordinator."""
        import custom_components.systemair.coordinator as coord_mod
        # Should not have it as a module-level name
        assert "CLOUD_UNAVAILABLE_SENSORS" not in dir(coord_mod)

    def test_default_cloud_sso_url_removed(self):
        """DEFAULT_CLOUD_SSO_URL was unused and should be removed from const."""
        import custom_components.systemair.const as const_mod
        assert not hasattr(const_mod, "DEFAULT_CLOUD_SSO_URL")


class TestTranslationQuality:
    """Tests for translation correctness (#34)."""

    def _load_translations(self, lang: str) -> dict:
        import json
        import pathlib
        path = pathlib.Path(
            "custom_components/systemair/translations"
        ) / f"{lang}.json"
        return json.loads(path.read_text())

    def test_nb_heater_type_spelling(self):
        """Norwegian 'heater type' should be 'Varmetype' not 'Varmertype'."""
        nb = self._load_translations("nb")
        name = nb["entity"]["sensor"]["heater_type"]["name"]
        assert name == "Varmetype"

    def test_nb_heater_position_spelling(self):
        """Norwegian 'heater position' should be 'Varmeposisjon' not 'Varmerposisjon'."""
        nb = self._load_translations("nb")
        name = nb["entity"]["sensor"]["heater_position"]["name"]
        assert name == "Varmeposisjon"

    def test_en_alarm_pdm_rhs_includes_pdm(self):
        """English PDM RHS alarm should include '(PDM)' suffix."""
        en = self._load_translations("en")
        name = en["entity"]["binary_sensor"]["alarm_alarm_pdm_rhs_state"]["name"]
        assert "(PDM)" in name

    def test_en_alarm_rh_includes_rh(self):
        """English RH alarm should include '(RH)' suffix."""
        en = self._load_translations("en")
        name = en["entity"]["binary_sensor"]["alarm_alarm_rh_state"]["name"]
        assert "(RH)" in name

    def test_nb_alarm_pdm_rhs_includes_pdm(self):
        """Norwegian PDM RHS alarm should include '(PDM)' suffix."""
        nb = self._load_translations("nb")
        name = nb["entity"]["binary_sensor"]["alarm_alarm_pdm_rhs_state"]["name"]
        assert "(PDM)" in name

    def test_nb_alarm_rh_includes_rh(self):
        """Norwegian RH alarm should include '(RH)' suffix."""
        nb = self._load_translations("nb")
        name = nb["entity"]["binary_sensor"]["alarm_alarm_rh_state"]["name"]
        assert "(RH)" in name

    def test_en_di_cookerhood_includes_di(self):
        """English cooker hood DI should include '(DI)' suffix."""
        en = self._load_translations("en")
        name = en["entity"]["binary_sensor"]["function_reg_sensor_di_cookerhood"]["name"]
        assert "(DI)" in name

    def test_en_di_vacuumcleaner_includes_di(self):
        """English vacuum cleaner DI should include '(DI)' suffix."""
        en = self._load_translations("en")
        name = en["entity"]["binary_sensor"]["function_reg_sensor_di_vacuumcleaner"]["name"]
        assert "(DI)" in name

    def test_nb_di_cookerhood_includes_di(self):
        """Norwegian cooker hood DI should include '(DI)' suffix."""
        nb = self._load_translations("nb")
        name = nb["entity"]["binary_sensor"]["function_reg_sensor_di_cookerhood"]["name"]
        assert "(DI)" in name

    def test_nb_di_vacuumcleaner_includes_di(self):
        """Norwegian vacuum cleaner DI should include '(DI)' suffix."""
        nb = self._load_translations("nb")
        name = nb["entity"]["binary_sensor"]["function_reg_sensor_di_vacuumcleaner"]["name"]
        assert "(DI)" in name


class TestManifestQuality:
    """Tests for manifest.json correctness (#31)."""

    def _load_manifest(self) -> dict:
        import json
        import pathlib
        path = pathlib.Path("custom_components/systemair/manifest.json")
        return json.loads(path.read_text())

    def test_codeowners_not_empty(self):
        """manifest.json should have at least one codeowner."""
        manifest = self._load_manifest()
        assert len(manifest["codeowners"]) > 0

    def test_iot_class_is_cloud_push(self):
        """manifest.json iot_class should be cloud_push."""
        manifest = self._load_manifest()
        assert manifest["iot_class"] == "cloud_push"
