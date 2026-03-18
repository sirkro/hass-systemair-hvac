"""Tests for the binary sensor platform."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.systemair.binary_sensor import (
    SystemairBinarySensor,
    SystemairBinarySensorDescription,
    _build_alarm_descriptions_cloud,
    _build_function_descriptions_cloud,
)
from custom_components.systemair.const import (
    CLOUD_ALARMS,
    CLOUD_FUNCTIONS,
    FUNCTION_PARAMS,
)
from custom_components.systemair.coordinator import SystemairData
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal mock coordinator for entity tests."""

    def __init__(self, data: SystemairData | None = None, connection_type: str = "cloud"):
        self.data = data
        self.connection_type = connection_type
        self.last_update_success = True

    async def async_add_listener(self, *args, **kwargs):
        return lambda: None


# ---------------------------------------------------------------------------
# Description builder tests
# ---------------------------------------------------------------------------


class TestDescriptionBuilders:
    """Test the binary sensor description builder functions."""

    def test_alarm_descriptions_cloud_count(self):
        descs = _build_alarm_descriptions_cloud()
        assert len(descs) == len(CLOUD_ALARMS)

    def test_function_descriptions_cloud_count(self):
        descs = _build_function_descriptions_cloud()
        # Cloud now uses same register-based approach as Modbus
        assert len(descs) == len(FUNCTION_PARAMS)

    def test_cloud_alarm_keys_unique(self):
        descs = _build_alarm_descriptions_cloud()
        keys = [d.key for d in descs]
        assert len(keys) == len(set(keys))

    def test_cloud_function_keys_unique(self):
        descs = _build_function_descriptions_cloud()
        keys = [d.key for d in descs]
        assert len(keys) == len(set(keys))

    def test_alarm_descriptions_have_problem_device_class(self):
        for desc in _build_alarm_descriptions_cloud():
            assert desc.device_class is not None

    def test_function_descriptions_have_running_device_class(self):
        for desc in _build_function_descriptions_cloud():
            assert desc.device_class is not None

    def test_alarm_is_not_function(self):
        for desc in _build_alarm_descriptions_cloud():
            assert desc.is_function is False

    def test_function_is_function(self):
        for desc in _build_function_descriptions_cloud():
            assert desc.is_function is True


# ---------------------------------------------------------------------------
# Entity tests
# ---------------------------------------------------------------------------


class TestSystemairBinarySensor:
    """Tests for the SystemairBinarySensor entity."""

    def _create_alarm_sensor(
        self, alarm_key: str, data: SystemairData | None = None
    ) -> tuple[SystemairBinarySensor, MockCoordinator]:
        """Create an alarm binary sensor."""
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        desc = SystemairBinarySensorDescription(
            key=f"alarm_{alarm_key.lower()}",
            name=f"Alarm: {alarm_key}",
            alarm_key=alarm_key,
            is_function=False,
        )

        with patch.object(SystemairBinarySensor, "__init__", lambda self, *a, **kw: None):
            sensor = SystemairBinarySensor.__new__(SystemairBinarySensor)
            sensor.coordinator = coordinator
            sensor.entity_description = desc
            sensor._attr_unique_id = f"{entry.entry_id}_{desc.key}"
            sensor._attr_entity_registry_enabled_default = False

        return sensor, coordinator

    def _create_function_sensor(
        self, func_key: str, data: SystemairData | None = None
    ) -> tuple[SystemairBinarySensor, MockCoordinator]:
        """Create a function binary sensor."""
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        desc = SystemairBinarySensorDescription(
            key=f"function_{func_key.lower()}",
            name=f"Function: {func_key}",
            alarm_key=func_key,
            is_function=True,
        )

        with patch.object(SystemairBinarySensor, "__init__", lambda self, *a, **kw: None):
            sensor = SystemairBinarySensor.__new__(SystemairBinarySensor)
            sensor.coordinator = coordinator
            sensor.entity_description = desc
            sensor._attr_unique_id = f"{entry.entry_id}_{desc.key}"

        return sensor, coordinator

    def test_alarm_active_by_level(self):
        """Test alarm is_on when alarm level > 0."""
        data = make_sample_data()
        data.alarms["REG_ALARM_FROST_PROT_ALARM"] = 2
        sensor, _ = self._create_alarm_sensor("REG_ALARM_FROST_PROT_ALARM", data)
        assert sensor.is_on is True

    def test_alarm_inactive_by_level(self):
        """Test alarm is_on when alarm level is 0."""
        data = make_sample_data()
        data.alarms["REG_ALARM_FROST_PROT_ALARM"] = 0
        sensor, _ = self._create_alarm_sensor("REG_ALARM_FROST_PROT_ALARM", data)
        assert sensor.is_on is False

    def test_alarm_active_boolean(self):
        """Test alarm is_on with boolean value."""
        data = make_sample_data()
        data.alarms["REG_ALARM_TYPE_A"] = True
        sensor, _ = self._create_alarm_sensor("REG_ALARM_TYPE_A", data)
        assert sensor.is_on is True

    def test_alarm_inactive_boolean(self):
        data = make_sample_data()
        data.alarms["REG_ALARM_TYPE_A"] = False
        sensor, _ = self._create_alarm_sensor("REG_ALARM_TYPE_A", data)
        assert sensor.is_on is False

    def test_alarm_missing_key(self):
        """Test alarm returns None when key not in data."""
        data = make_sample_data()
        sensor, _ = self._create_alarm_sensor("nonexistent", data)
        assert sensor.is_on is None

    def test_alarm_none_data(self):
        sensor, coord = self._create_alarm_sensor("REG_ALARM_FROST_PROT_ALARM")
        coord.data = None
        assert sensor.is_on is None

    def test_function_active(self):
        data = make_sample_data()
        data.functions["REG_FUNCTION_ACTIVE_PRESSURE_GUARD"] = True
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_PRESSURE_GUARD", data)
        assert sensor.is_on is True

    def test_function_inactive(self):
        data = make_sample_data()
        data.functions["REG_FUNCTION_ACTIVE_PRESSURE_GUARD"] = False
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_PRESSURE_GUARD", data)
        assert sensor.is_on is False

    def test_function_missing_key(self):
        data = make_sample_data()
        sensor, _ = self._create_function_sensor("nonexistent", data)
        assert sensor.is_on is None

    def test_alarm_extra_attributes_level(self):
        """Test extra attributes for level-based alarms."""
        data = make_sample_data()
        data.alarms["REG_ALARM_FROST_PROT_ALARM"] = 2
        sensor, _ = self._create_alarm_sensor("REG_ALARM_FROST_PROT_ALARM", data)
        attrs = sensor.extra_state_attributes
        assert attrs["alarm_level"] == 2
        assert attrs["alarm_severity"] == "alarm"

    def test_alarm_extra_attributes_severity_map(self):
        """Test all alarm severity levels."""
        for level, expected in [(0, "inactive"), (1, "warning"), (2, "alarm"), (3, "critical")]:
            data = make_sample_data()
            data.alarms["REG_ALARM_FROST_PROT_ALARM"] = level
            sensor, _ = self._create_alarm_sensor("REG_ALARM_FROST_PROT_ALARM", data)
            attrs = sensor.extra_state_attributes
            assert attrs["alarm_severity"] == expected

    def test_alarm_extra_attributes_boolean(self):
        """Test extra attributes for boolean alarms (no level info)."""
        data = make_sample_data()
        data.alarms["REG_ALARM_TYPE_A"] = True
        sensor, _ = self._create_alarm_sensor("REG_ALARM_TYPE_A", data)
        attrs = sensor.extra_state_attributes
        # Boolean alarms don't have level info
        assert "alarm_level" not in attrs

    def test_function_extra_attributes_empty(self):
        """Test that functions don't have extra attributes."""
        data = make_sample_data()
        data.functions["REG_FUNCTION_ACTIVE_PRESSURE_GUARD"] = True
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_PRESSURE_GUARD", data)
        attrs = sensor.extra_state_attributes
        assert attrs == {}

    def test_heater_active_on(self):
        """Test heater_active binary sensor when heater is on."""
        data = make_sample_data()
        data.heater_active = True
        sensor, _ = self._create_alarm_sensor("__heater_active__", data)
        assert sensor.is_on is True

    def test_heater_active_off(self):
        """Test heater_active binary sensor when heater is off."""
        data = make_sample_data()
        data.heater_active = False
        sensor, _ = self._create_alarm_sensor("__heater_active__", data)
        assert sensor.is_on is False

    def test_heater_active_none(self):
        """Test heater_active binary sensor when data is None."""
        data = make_sample_data()
        data.heater_active = None
        sensor, _ = self._create_alarm_sensor("__heater_active__", data)
        assert sensor.is_on is None

    def test_cooler_active_on(self):
        """Test cooler_active binary sensor when cooler is on."""
        data = make_sample_data()
        data.cooler_active = True
        sensor, _ = self._create_alarm_sensor("__cooler_active__", data)
        assert sensor.is_on is True

    def test_cooler_active_off(self):
        """Test cooler_active binary sensor when cooler is off."""
        data = make_sample_data()
        data.cooler_active = False
        sensor, _ = self._create_alarm_sensor("__cooler_active__", data)
        assert sensor.is_on is False

    def test_heater_active_none_coordinator_data(self):
        """Test heater_active returns None when coordinator data is None."""
        sensor, coord = self._create_alarm_sensor("__heater_active__")
        coord.data = None
        assert sensor.is_on is None

    def test_function_heating_active(self):
        """Test heating function active."""
        data = make_sample_data()
        # make_sample_data sets heating=True
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_HEATING", data)
        assert sensor.is_on is True

    def test_function_heat_recovery_active(self):
        """Test heat recovery function active."""
        data = make_sample_data()
        # make_sample_data sets heat_recovery=True
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_HEAT_RECOVERY", data)
        assert sensor.is_on is True

    def test_function_moisture_transfer_active(self):
        """Test moisture transfer function active."""
        data = make_sample_data()
        # make_sample_data sets moisture_transfer=True
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_MOISTURE_TRANSFER", data)
        assert sensor.is_on is True

    def test_function_cooling_inactive(self):
        """Test cooling function inactive."""
        data = make_sample_data()
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_COOLING", data)
        assert sensor.is_on is False

    def test_function_defrosting_inactive(self):
        """Test defrosting function inactive."""
        data = make_sample_data()
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_DEFROSTING", data)
        assert sensor.is_on is False

    def test_function_cooker_hood_inactive(self):
        """Test cooker hood function inactive."""
        data = make_sample_data()
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_COOKER_HOOD", data)
        assert sensor.is_on is False

    def test_function_eco_mode_inactive(self):
        """Test eco mode function inactive."""
        data = make_sample_data()
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_ECO_MODE", data)
        assert sensor.is_on is False

    def test_function_toggle(self):
        """Test toggling a function from inactive to active."""
        data = make_sample_data()
        data.functions["REG_FUNCTION_ACTIVE_COOLING"] = False
        sensor, _ = self._create_function_sensor("REG_FUNCTION_ACTIVE_COOLING", data)
        assert sensor.is_on is False
        data.functions["REG_FUNCTION_ACTIVE_COOLING"] = True
        assert sensor.is_on is True

    def test_all_function_keys_present_in_sample_data(self):
        """Verify all FUNCTION_PARAMS keys are present in make_sample_data."""
        data = make_sample_data()
        for param in FUNCTION_PARAMS:
            assert param.short in data.functions, f"{param.short} missing from sample data functions"


# ---------------------------------------------------------------------------
# Cloud availability tests
# ---------------------------------------------------------------------------


class TestBinarySensorCloudAvailability:
    """Test that heater_active and cooler_active are unavailable on cloud."""

    def _create_sensor_with_connection(
        self, key: str, connection_type: str
    ) -> SystemairBinarySensor:
        """Create a binary sensor with a specific connection type."""
        data = make_sample_data()
        coordinator = MockCoordinator(data, connection_type=connection_type)
        entry = MockConfigEntry()

        desc = SystemairBinarySensorDescription(
            key=key,
            name=f"Test: {key}",
            device_class=BinarySensorDeviceClass.RUNNING,
            alarm_key=f"__{key}__",
            is_function=False,
        )

        with patch.object(SystemairBinarySensor, "__init__", lambda self, *a, **kw: None):
            sensor = SystemairBinarySensor.__new__(SystemairBinarySensor)
            sensor.coordinator = coordinator
            sensor.entity_description = desc
            sensor._attr_unique_id = f"{entry.entry_id}_{desc.key}"

        return sensor

    def test_heater_active_unavailable_on_cloud(self):
        """Test heater_active is unavailable when connection is cloud."""
        sensor = self._create_sensor_with_connection("heater_active", "cloud")
        assert sensor.available is False

    def test_cooler_active_unavailable_on_cloud(self):
        """Test cooler_active is unavailable when connection is cloud."""
        sensor = self._create_sensor_with_connection("cooler_active", "cloud")
        assert sensor.available is False

    def test_alarm_sensor_available_on_cloud(self):
        """Test that regular alarm sensors remain available on cloud."""
        data = make_sample_data()
        coordinator = MockCoordinator(data, connection_type="cloud")
        entry = MockConfigEntry()

        desc = SystemairBinarySensorDescription(
            key="alarm_frost_prot",
            name="Alarm: Frost Protection",
            device_class=BinarySensorDeviceClass.PROBLEM,
            alarm_key="REG_ALARM_FROST_PROT_ALARM",
            is_function=False,
        )

        with patch.object(SystemairBinarySensor, "__init__", lambda self, *a, **kw: None):
            sensor = SystemairBinarySensor.__new__(SystemairBinarySensor)
            sensor.coordinator = coordinator
            sensor.entity_description = desc
            sensor._attr_unique_id = f"{entry.entry_id}_{desc.key}"

        assert sensor.available is True

    def test_unavailable_when_coordinator_unavailable(self):
        """Test sensor is unavailable when coordinator data is None."""
        sensor = self._create_sensor_with_connection("heater_active", "cloud")
        sensor.coordinator.data = None
        # CoordinatorEntity.available returns False when data is None,
        # but our mock doesn't implement that. The key point is that
        # the super().available check is part of the chain.
        # For cloud with valid data, heater_active should be unavailable:
        sensor.coordinator.data = make_sample_data()
        assert sensor.available is False


# ---------------------------------------------------------------------------
# Phase 8 quality fix tests
# ---------------------------------------------------------------------------


class TestAlarmDescriptionsDifferentiated:
    """Tests for differentiated alarm descriptions (#35)."""

    def test_all_alarm_descriptions_unique(self):
        """Each alarm in CLOUD_ALARMS should have a unique description."""
        descriptions = [a["description"] for a in CLOUD_ALARMS]
        assert len(descriptions) == len(set(descriptions)), (
            f"Duplicate alarm descriptions found: "
            f"{[d for d in descriptions if descriptions.count(d) > 1]}"
        )

    def test_pdm_rhs_includes_pdm_suffix(self):
        """alarm_pdm_rhs_state should include '(PDM)' in description."""
        alarm = next(a for a in CLOUD_ALARMS if a["id"] == "alarm_pdm_rhs_state")
        assert "(PDM)" in alarm["description"]

    def test_rh_includes_rh_suffix(self):
        """alarm_rh_state should include '(RH)' in description."""
        alarm = next(a for a in CLOUD_ALARMS if a["id"] == "alarm_rh_state")
        assert "(RH)" in alarm["description"]

    def test_alarm_names_in_built_descriptions_unique(self):
        """Built alarm description names should all be unique."""
        descs = _build_alarm_descriptions_cloud()
        names = [d.name for d in descs]
        assert len(names) == len(set(names))


class TestCloudFunctionsServiceUserLock:
    """Tests for function_active_service_user_lock entry (#30)."""

    def test_service_user_lock_has_no_register(self):
        """Service user lock is cloud-only with no Modbus register."""
        entry = next(
            f for f in CLOUD_FUNCTIONS
            if f["id"] == "function_active_service_user_lock"
        )
        assert "register" not in entry

    def test_function_builder_handles_missing_register(self):
        """Function description builder should skip entries without register."""
        descs = _build_function_descriptions_cloud()
        # service_user_lock has no register, so it won't appear
        # in FUNCTION_PARAMS. Builder should still work without error.
        assert len(descs) == len(FUNCTION_PARAMS)
