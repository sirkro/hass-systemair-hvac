"""Tests for the number platform (fan levels & timed mode durations)."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.number import (
    FAN_LEVEL_DESCRIPTIONS,
    TIMED_MODE_DURATION_DESCRIPTIONS,
    SystemairFanLevelDescription,
    SystemairFanLevelNumber,
    SystemairTimedModeDurationDescription,
    SystemairTimedModeDurationNumber,
    async_setup_entry,
)
from custom_components.systemair.coordinator import SystemairData
from custom_components.systemair.const import (
    CONN_CLOUD,
    DOMAIN,
    FAN_LEVEL_REGISTERS,
    PARAMETER_MAP,
    TIMED_MODE_DURATION_REGISTERS,
)
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal mock coordinator for entity tests."""

    def __init__(self, data: SystemairData | None = None, connection_type: str = CONN_CLOUD):
        self.data = data
        self.connection_type = connection_type
        self.async_set_fan_level = AsyncMock()
        self.async_set_timed_mode_duration = AsyncMock()

    async def async_add_listener(self, *args, **kwargs):
        return lambda: None


# ---------------------------------------------------------------------------
# Description tests
# ---------------------------------------------------------------------------


class TestFanLevelDescriptions:
    """Tests for the generated fan level entity descriptions."""

    def test_correct_count(self):
        """Should have 16 descriptions (8 modes x SAF + EAF)."""
        assert len(FAN_LEVEL_DESCRIPTIONS) == 16

    def test_unique_keys(self):
        """All description keys should be unique."""
        keys = [d.key for d in FAN_LEVEL_DESCRIPTIONS]
        assert len(keys) == len(set(keys))

    def test_all_have_register_short(self):
        """Every description should have a register_short pointing to PARAMETER_MAP."""
        for desc in FAN_LEVEL_DESCRIPTIONS:
            assert desc.register_short in PARAMETER_MAP, (
                f"{desc.key} has register_short={desc.register_short} not in PARAMETER_MAP"
            )

    def test_all_have_mode_name_and_air_type(self):
        """Every description should have mode_name and air_type set."""
        for desc in FAN_LEVEL_DESCRIPTIONS:
            assert desc.mode_name, f"{desc.key} missing mode_name"
            assert desc.air_type in ("Supply", "Extract"), (
                f"{desc.key} has invalid air_type={desc.air_type}"
            )

    def test_min_max_values(self):
        """Min/max should reflect the PARAMETER_MAP bounds."""
        for desc in FAN_LEVEL_DESCRIPTIONS:
            param = PARAMETER_MAP[desc.register_short]
            expected_min = float(param.min_val if param.min_val is not None else 0)
            expected_max = float(param.max_val if param.max_val is not None else 5)
            assert desc.native_min_value == expected_min, (
                f"{desc.key}: expected min {expected_min}, got {desc.native_min_value}"
            )
            assert desc.native_max_value == expected_max, (
                f"{desc.key}: expected max {expected_max}, got {desc.native_max_value}"
            )

    def test_step_is_one(self):
        """All fan level entities use step=1.0."""
        for desc in FAN_LEVEL_DESCRIPTIONS:
            assert desc.native_step == 1.0

    def test_icon_is_fan(self):
        """All fan level entities have the mdi:fan icon."""
        for desc in FAN_LEVEL_DESCRIPTIONS:
            assert desc.icon == "mdi:fan"

    def test_matches_fan_level_registers(self):
        """Descriptions should be in same order and match FAN_LEVEL_REGISTERS."""
        for desc, (reg_short, mode_name, air_type) in zip(
            FAN_LEVEL_DESCRIPTIONS, FAN_LEVEL_REGISTERS
        ):
            assert desc.register_short == reg_short
            assert desc.mode_name == mode_name
            assert desc.air_type == air_type


# ---------------------------------------------------------------------------
# async_setup_entry tests
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_cloud_creates_all_entities(self):
        """Cloud connection creates fan level + timed mode duration entities."""
        coordinator = MockCoordinator(connection_type=CONN_CLOUD)
        entry = MockConfigEntry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}
        add_entities = MagicMock()

        await async_setup_entry(hass, entry, add_entities)
        add_entities.assert_called_once()
        entities = add_entities.call_args[0][0]
        fan_level_entities = [e for e in entities if isinstance(e, SystemairFanLevelNumber)]
        duration_entities = [e for e in entities if isinstance(e, SystemairTimedModeDurationNumber)]
        assert len(fan_level_entities) == 16
        assert len(duration_entities) == 5
        # Cloud fan levels should be read-only
        for e in fan_level_entities:
            assert e._read_only is True

    @pytest.mark.asyncio
    async def test_non_cloud_creates_writable_fan_levels(self):
        """Non-cloud connection creates writable fan level entities."""
        coordinator = MockCoordinator(connection_type="modbus")
        entry = MockConfigEntry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}
        add_entities = MagicMock()

        await async_setup_entry(hass, entry, add_entities)
        add_entities.assert_called_once()
        entities = add_entities.call_args[0][0]
        fan_level_entities = [e for e in entities if isinstance(e, SystemairFanLevelNumber)]
        for e in fan_level_entities:
            assert e._read_only is False


# ---------------------------------------------------------------------------
# Entity tests
# ---------------------------------------------------------------------------


class TestSystemairFanLevelNumber:
    """Tests for the SystemairFanLevelNumber entity."""

    def _create_entity(
        self,
        data: SystemairData | None = None,
        desc_index: int = 0,
    ) -> tuple[SystemairFanLevelNumber, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()
        desc = FAN_LEVEL_DESCRIPTIONS[desc_index]

        with patch.object(SystemairFanLevelNumber, "__init__", lambda self, *a, **kw: None):
            entity = SystemairFanLevelNumber.__new__(SystemairFanLevelNumber)
            entity.coordinator = coordinator
            entity.entity_description = desc
            entity._attr_unique_id = f"{entry.entry_id}_{desc.key}"
            entity._attr_entity_registry_enabled_default = False
            entity._read_only = False

        return entity, coordinator

    def test_native_value(self):
        """Should return the fan level value from coordinator data."""
        data = make_sample_data()
        # First description is REG_USERMODE_CROWDED_AIRFLOW_LEVEL_SAF = 4
        entity, _ = self._create_entity(data, desc_index=0)
        assert entity.native_value == 4.0

    def test_native_value_different_register(self):
        """Should look up the correct register for each description."""
        data = make_sample_data()
        # Index 5 is REG_USERMODE_FIREPLACE_AIRFLOW_LEVEL_EAF = 2
        entity, _ = self._create_entity(data, desc_index=5)
        assert entity.native_value == 2.0

    def test_native_value_none_data(self):
        """Should return None when coordinator data is None."""
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.native_value is None

    def test_native_value_missing_register(self):
        """Should return None when register is not in fan_levels dict."""
        data = make_sample_data()
        data.fan_levels = {}  # empty — no levels available
        entity, _ = self._create_entity(data, desc_index=0)
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_set_native_value(self):
        """Should call coordinator.async_set_fan_level with register and int value."""
        entity, coord = self._create_entity()
        desc = entity.entity_description
        await entity.async_set_native_value(3.0)
        coord.async_set_fan_level.assert_called_once_with(desc.register_short, 3)

    @pytest.mark.asyncio
    async def test_set_native_value_rounds_to_int(self):
        """Value passed to coordinator should be converted to int."""
        entity, coord = self._create_entity()
        desc = entity.entity_description
        await entity.async_set_native_value(4.7)
        coord.async_set_fan_level.assert_called_once_with(desc.register_short, 4)

    def test_entity_disabled_by_default(self):
        """Fan level entities should be disabled by default."""
        entity, _ = self._create_entity()
        assert entity._attr_entity_registry_enabled_default is False

    def test_all_descriptions_produce_valid_entities(self):
        """Every description should create a working entity with native_value."""
        data = make_sample_data()
        for i, desc in enumerate(FAN_LEVEL_DESCRIPTIONS):
            entity, _ = self._create_entity(data, desc_index=i)
            val = entity.native_value
            # All fan_levels are populated in sample data, so value should be a float
            assert isinstance(val, float), (
                f"Description index {i} ({desc.key}) returned {val!r} instead of float"
            )


class TestFanLevelCloudReadOnly:
    """Tests for read-only fan level behavior on cloud connections."""

    def _create_entity(
        self,
        data: SystemairData | None = None,
        desc_index: int = 0,
        read_only: bool = True,
    ) -> tuple[SystemairFanLevelNumber, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()
        desc = FAN_LEVEL_DESCRIPTIONS[desc_index]

        with patch.object(SystemairFanLevelNumber, "__init__", lambda self, *a, **kw: None):
            entity = SystemairFanLevelNumber.__new__(SystemairFanLevelNumber)
            entity.coordinator = coordinator
            entity.entity_description = desc
            entity._attr_unique_id = f"{entry.entry_id}_{desc.key}"
            entity._attr_entity_registry_enabled_default = False
            entity._read_only = read_only

        return entity, coordinator

    @pytest.mark.asyncio
    async def test_read_only_set_raises_error(self):
        """Setting value on read-only entity should raise HomeAssistantError."""
        from homeassistant.exceptions import HomeAssistantError

        entity, coord = self._create_entity(read_only=True)
        with pytest.raises(HomeAssistantError, match="read-only"):
            await entity.async_set_native_value(3.0)
        coord.async_set_fan_level.assert_not_called()

    @pytest.mark.asyncio
    async def test_writable_set_calls_coordinator(self):
        """Setting value on writable entity should call coordinator."""
        entity, coord = self._create_entity(read_only=False)
        desc = entity.entity_description
        await entity.async_set_native_value(3.0)
        coord.async_set_fan_level.assert_called_once_with(desc.register_short, 3)

    def test_read_only_still_returns_value(self):
        """Read-only entity should still return the native_value from data."""
        entity, _ = self._create_entity(read_only=True)
        assert entity.native_value is not None


# ---------------------------------------------------------------------------
# Timed mode duration description tests
# ---------------------------------------------------------------------------


class TestTimedModeDurationDescriptions:
    """Tests for the generated timed mode duration entity descriptions."""

    def test_correct_count(self):
        """Should have 5 descriptions (one per timed mode)."""
        assert len(TIMED_MODE_DURATION_DESCRIPTIONS) == 5

    def test_unique_keys(self):
        """All description keys should be unique."""
        keys = [d.key for d in TIMED_MODE_DURATION_DESCRIPTIONS]
        assert len(keys) == len(set(keys))

    def test_all_have_register_short(self):
        """Every description should have a register_short pointing to PARAMETER_MAP."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            assert desc.register_short in PARAMETER_MAP, (
                f"{desc.key} has register_short={desc.register_short} not in PARAMETER_MAP"
            )

    def test_all_have_mode_name(self):
        """Every description should have mode_name set."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            assert desc.mode_name, f"{desc.key} missing mode_name"

    def test_all_have_unit_of_measurement(self):
        """Every description should have a native_unit_of_measurement."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            assert desc.native_unit_of_measurement is not None, (
                f"{desc.key} missing native_unit_of_measurement"
            )

    def test_min_max_values(self):
        """Min/max should reflect the PARAMETER_MAP bounds."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            param = PARAMETER_MAP[desc.register_short]
            expected_min = float(param.min_val if param.min_val is not None else 1)
            expected_max = float(param.max_val if param.max_val is not None else 365)
            assert desc.native_min_value == expected_min, (
                f"{desc.key}: expected min {expected_min}, got {desc.native_min_value}"
            )
            assert desc.native_max_value == expected_max, (
                f"{desc.key}: expected max {expected_max}, got {desc.native_max_value}"
            )

    def test_step_is_one(self):
        """All duration entities use step=1.0."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            assert desc.native_step == 1.0

    def test_icon(self):
        """All duration entities have the mdi:timer-cog-outline icon."""
        for desc in TIMED_MODE_DURATION_DESCRIPTIONS:
            assert desc.icon == "mdi:timer-cog-outline"

    def test_matches_duration_registers(self):
        """Descriptions should match TIMED_MODE_DURATION_REGISTERS order."""
        for desc, (reg_short, mode_name, _) in zip(
            TIMED_MODE_DURATION_DESCRIPTIONS, TIMED_MODE_DURATION_REGISTERS
        ):
            assert desc.register_short == reg_short
            assert desc.mode_name == mode_name


# ---------------------------------------------------------------------------
# Timed mode duration entity tests
# ---------------------------------------------------------------------------


class TestSystemairTimedModeDurationNumber:
    """Tests for the SystemairTimedModeDurationNumber entity."""

    def _create_entity(
        self,
        data: SystemairData | None = None,
        desc_index: int = 0,
    ) -> tuple[SystemairTimedModeDurationNumber, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()
        desc = TIMED_MODE_DURATION_DESCRIPTIONS[desc_index]

        with patch.object(SystemairTimedModeDurationNumber, "__init__", lambda self, *a, **kw: None):
            entity = SystemairTimedModeDurationNumber.__new__(SystemairTimedModeDurationNumber)
            entity.coordinator = coordinator
            entity.entity_description = desc
            entity._attr_unique_id = f"{entry.entry_id}_{desc.key}"
            entity._attr_entity_registry_enabled_default = False

        return entity, coordinator

    def test_native_value(self):
        """Should return the duration value from coordinator data."""
        data = make_sample_data()
        # Index 0 = Holiday = REG_USERMODE_HOLIDAY_TIME = 7
        entity, _ = self._create_entity(data, desc_index=0)
        assert entity.native_value == 7.0

    def test_native_value_away(self):
        """Should return correct value for Away mode (index 1)."""
        data = make_sample_data()
        entity, _ = self._create_entity(data, desc_index=1)
        assert entity.native_value == 24.0

    def test_native_value_fireplace(self):
        """Should return correct value for Fireplace mode (index 2)."""
        data = make_sample_data()
        entity, _ = self._create_entity(data, desc_index=2)
        assert entity.native_value == 30.0

    def test_native_value_refresh(self):
        """Should return correct value for Refresh mode (index 3)."""
        data = make_sample_data()
        entity, _ = self._create_entity(data, desc_index=3)
        assert entity.native_value == 120.0

    def test_native_value_crowded(self):
        """Should return correct value for Crowded mode (index 4)."""
        data = make_sample_data()
        entity, _ = self._create_entity(data, desc_index=4)
        assert entity.native_value == 4.0

    def test_native_value_none_data(self):
        """Should return None when coordinator data is None."""
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.native_value is None

    def test_native_value_missing_register(self):
        """Should return None when register is not in timed_mode_durations dict."""
        data = make_sample_data()
        data.timed_mode_durations = {}
        entity, _ = self._create_entity(data, desc_index=0)
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_set_native_value(self):
        """Should call coordinator.async_set_timed_mode_duration with register and int value."""
        entity, coord = self._create_entity()
        desc = entity.entity_description
        await entity.async_set_native_value(10.0)
        coord.async_set_timed_mode_duration.assert_called_once_with(desc.register_short, 10)

    @pytest.mark.asyncio
    async def test_set_native_value_rounds_to_int(self):
        """Value passed to coordinator should be converted to int."""
        entity, coord = self._create_entity()
        desc = entity.entity_description
        await entity.async_set_native_value(7.9)
        coord.async_set_timed_mode_duration.assert_called_once_with(desc.register_short, 7)

    def test_entity_disabled_by_default(self):
        """Duration entities should be disabled by default."""
        entity, _ = self._create_entity()
        assert entity._attr_entity_registry_enabled_default is False

    def test_all_descriptions_produce_valid_entities(self):
        """Every description should create a working entity with native_value."""
        data = make_sample_data()
        for i, desc in enumerate(TIMED_MODE_DURATION_DESCRIPTIONS):
            entity, _ = self._create_entity(data, desc_index=i)
            val = entity.native_value
            assert isinstance(val, float), (
                f"Description index {i} ({desc.key}) returned {val!r} instead of float"
            )
