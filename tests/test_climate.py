"""Tests for the climate platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.climate import (
    HA_FAN_MODE_MAP,
    HA_FAN_MODE_REVERSE,
    PRESET_MODES,
    PRESET_NONE,
    SystemairClimate,
)
from custom_components.systemair.const import (
    PRESET_TO_TIMED_MODE,
    TIMED_MODE_DEFAULTS,
    USER_MODE_TO_PRESET,
)
from custom_components.systemair.coordinator import SystemairData
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# We can't easily import HVACMode/HVACAction without HA installed,
# so we define the string values we expect.
HVAC_MODE_AUTO = "auto"
HVAC_MODE_FAN_ONLY = "fan_only"
HVAC_ACTION_FAN = "fan"
HVAC_ACTION_IDLE = "idle"
HVAC_ACTION_HEATING = "heating"
HVAC_ACTION_COOLING = "cooling"


class MockCoordinator:
    """Minimal mock coordinator for entity tests."""

    def __init__(self, data: SystemairData | None = None):
        self.data = data
        self.async_set_target_temperature = AsyncMock()
        self.async_set_fan_mode = AsyncMock()
        self.async_set_mode = AsyncMock()
        self.async_set_timed_mode = AsyncMock()
        self.async_request_refresh = AsyncMock()

    async def async_add_listener(self, *args, **kwargs):
        return lambda: None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFanModeMappings:
    """Test fan mode mapping constants."""

    def test_ha_fan_mode_map(self):
        assert HA_FAN_MODE_MAP == {2: "low", 3: "medium", 4: "high"}

    def test_ha_fan_mode_reverse(self):
        assert HA_FAN_MODE_REVERSE == {"low": 2, "medium": 3, "high": 4}


class TestPresetModeConstants:
    """Test preset mode constants."""

    def test_preset_modes_sorted(self):
        """Preset modes should have 'none' first, then sorted timed modes."""
        assert PRESET_MODES[0] == "none"
        assert PRESET_MODES[1:] == sorted(PRESET_MODES[1:])

    def test_preset_modes_match_timed_mode_mapping(self):
        """All preset modes except 'none' should map to a timed mode."""
        for preset in PRESET_MODES:
            if preset == "none":
                continue
            assert preset in PRESET_TO_TIMED_MODE

    def test_all_timed_modes_have_defaults(self):
        """Every timed mode referenced by a preset should have a default duration."""
        for preset, timed_mode in PRESET_TO_TIMED_MODE.items():
            assert timed_mode in TIMED_MODE_DEFAULTS, (
                f"Preset '{preset}' maps to timed mode '{timed_mode}' "
                f"which has no default duration"
            )

    def test_user_mode_to_preset_covers_all_timed_modes(self):
        """All timed user modes (2-6) should map to a preset."""
        for mode_val in (2, 3, 4, 5, 6):
            assert mode_val in USER_MODE_TO_PRESET

    def test_preset_none_is_in_presets(self):
        """PRESET_NONE should be in the list of selectable presets (first entry)."""
        assert PRESET_NONE in PRESET_MODES
        assert PRESET_MODES[0] == PRESET_NONE


class TestSystemairClimate:
    """Tests for the SystemairClimate entity."""

    def _create_entity(
        self, data: SystemairData | None = None
    ) -> tuple[SystemairClimate, MockCoordinator]:
        """Create a climate entity with mock coordinator."""
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        with patch.object(SystemairClimate, "__init__", lambda self, *a, **kw: None):
            entity = SystemairClimate.__new__(SystemairClimate)
            entity.coordinator = coordinator
            entity._attr_unique_id = f"{entry.entry_id}_climate"
            entity._attr_device_info = {
                "identifiers": {("systemair", entry.entry_id)},
                "name": entry.title,
                "manufacturer": "Systemair",
                "model": "HVAC",
            }

        return entity, coordinator

    def test_current_temperature(self):
        data = make_sample_data()
        data.supply_air_temperature = 21.5
        entity, _ = self._create_entity(data)
        assert entity.current_temperature == 21.5

    def test_current_temperature_none(self):
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.current_temperature is None

    def test_target_temperature(self):
        data = make_sample_data()
        data.target_temperature = 22.0
        entity, _ = self._create_entity(data)
        assert entity.target_temperature == 22.0

    def test_fan_mode_low(self):
        data = make_sample_data()
        data.fan_mode = 2
        entity, _ = self._create_entity(data)
        assert entity.fan_mode == "low"

    def test_fan_mode_medium(self):
        data = make_sample_data()
        data.fan_mode = 3
        entity, _ = self._create_entity(data)
        assert entity.fan_mode == "medium"

    def test_fan_mode_high(self):
        data = make_sample_data()
        data.fan_mode = 4
        entity, _ = self._create_entity(data)
        assert entity.fan_mode == "high"

    def test_fan_mode_unknown(self):
        data = make_sample_data()
        data.fan_mode = 1  # "Off" is not in HA_FAN_MODE_MAP
        entity, _ = self._create_entity(data)
        assert entity.fan_mode is None

    def test_fan_mode_none_data(self):
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.fan_mode is None

    def test_hvac_mode_auto(self):
        data = make_sample_data()
        data.user_mode = 0
        entity, _ = self._create_entity(data)
        # The entity uses HVACMode enum but the value is "auto"
        mode = entity.hvac_mode
        assert mode is not None
        assert mode.value == HVAC_MODE_AUTO if hasattr(mode, "value") else str(mode) == HVAC_MODE_AUTO

    def test_hvac_mode_manual_fan_only(self):
        data = make_sample_data()
        data.user_mode = 1
        entity, _ = self._create_entity(data)
        mode = entity.hvac_mode
        assert mode is not None

    def test_hvac_action_fan(self):
        data = make_sample_data()
        data.saf_speed = 65.0
        data.heater_active = False
        data.heater_output = 0.0
        data.cooler_active = False
        data.cooler_output = 0.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        assert action is not None
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_FAN

    def test_hvac_action_idle(self):
        data = make_sample_data()
        data.saf_speed = 0
        data.heater_active = False
        data.heater_output = 0.0
        data.cooler_active = False
        data.cooler_output = 0.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        assert action is not None
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_IDLE

    def test_hvac_action_heating_active(self):
        """Test HEATING action when heater_active is True."""
        data = make_sample_data()
        data.heater_active = True
        data.heater_output = 35.0
        data.cooler_active = False
        data.cooler_output = 0.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_HEATING

    def test_hvac_action_heating_by_output(self):
        """Test HEATING action when heater_output > 0 but heater_active is False."""
        data = make_sample_data()
        data.heater_active = False
        data.heater_output = 50.0
        data.cooler_active = False
        data.cooler_output = 0.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_HEATING

    def test_hvac_action_cooling_active(self):
        """Test COOLING action when cooler_active is True."""
        data = make_sample_data()
        data.heater_active = False
        data.heater_output = 0.0
        data.cooler_active = True
        data.cooler_output = 60.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_COOLING

    def test_hvac_action_cooling_by_output(self):
        """Test COOLING action when cooler_output > 0 but cooler_active is False."""
        data = make_sample_data()
        data.heater_active = False
        data.heater_output = 0.0
        data.cooler_active = False
        data.cooler_output = 30.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_COOLING

    def test_hvac_action_heating_takes_precedence(self):
        """Test that heating takes precedence over cooling."""
        data = make_sample_data()
        data.heater_active = True
        data.heater_output = 30.0
        data.cooler_active = True
        data.cooler_output = 50.0
        entity, _ = self._create_entity(data)
        action = entity.hvac_action
        action_str = action.value if hasattr(action, "value") else str(action)
        assert action_str == HVAC_ACTION_HEATING

    def test_hvac_action_none_data(self):
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.hvac_action is None

    def test_extra_state_attributes(self):
        data = make_sample_data()
        entity, _ = self._create_entity(data)
        attrs = entity.extra_state_attributes
        assert attrs["user_mode"] == "Auto"
        assert attrs["user_mode_id"] == 0
        assert attrs["outdoor_temperature"] == 5.0
        assert attrs["extract_temperature"] == 22.0
        assert attrs["eco_mode"] is False

    def test_extra_state_attributes_empty_data(self):
        entity, coord = self._create_entity()
        coord.data = None
        attrs = entity.extra_state_attributes
        assert attrs == {}

    @pytest.mark.asyncio
    async def test_set_temperature(self):
        entity, coord = self._create_entity()
        await entity.async_set_temperature(temperature=22.5)
        coord.async_set_target_temperature.assert_called_once_with(22.5)

    @pytest.mark.asyncio
    async def test_set_temperature_no_value(self):
        entity, coord = self._create_entity()
        await entity.async_set_temperature()
        coord.async_set_target_temperature.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_fan_mode(self):
        entity, coord = self._create_entity()
        await entity.async_set_fan_mode("high")
        coord.async_set_fan_mode.assert_called_once_with(4)

    @pytest.mark.asyncio
    async def test_set_fan_mode_unknown(self):
        entity, coord = self._create_entity()
        await entity.async_set_fan_mode("turbo")
        coord.async_set_fan_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto(self):
        entity, coord = self._create_entity()
        # We need to import HVACMode to pass the right value
        from custom_components.systemair.climate import HVACMode
        await entity.async_set_hvac_mode(HVACMode.AUTO)
        coord.async_set_mode.assert_called_once_with("auto")

    @pytest.mark.asyncio
    async def test_set_hvac_mode_fan_only(self):
        entity, coord = self._create_entity()
        from custom_components.systemair.climate import HVACMode
        await entity.async_set_hvac_mode(HVACMode.FAN_ONLY)
        coord.async_set_mode.assert_called_once_with("manual")


class TestPresetModes:
    """Tests for preset mode support."""

    def _create_entity(
        self, data: SystemairData | None = None
    ) -> tuple[SystemairClimate, MockCoordinator]:
        """Create a climate entity with mock coordinator."""
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        with patch.object(SystemairClimate, "__init__", lambda self, *a, **kw: None):
            entity = SystemairClimate.__new__(SystemairClimate)
            entity.coordinator = coordinator
            entity._attr_unique_id = f"{entry.entry_id}_climate"
            entity._attr_device_info = {
                "identifiers": {("systemair", entry.entry_id)},
                "name": entry.title,
                "manufacturer": "Systemair",
                "model": "HVAC",
            }

        return entity, coordinator

    # --- Reading preset mode ---

    def test_preset_mode_auto_returns_none_preset(self):
        """Auto mode (0) should return PRESET_NONE ('none') — no timed preset active."""
        data = make_sample_data()
        data.user_mode = 0
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == PRESET_NONE

    def test_preset_mode_manual_returns_none_preset(self):
        """Manual mode (1) should return PRESET_NONE ('none') — no timed preset active."""
        data = make_sample_data()
        data.user_mode = 1
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == PRESET_NONE

    def test_preset_mode_crowded_returns_comfort(self):
        """Crowded mode (2) -> comfort preset."""
        data = make_sample_data()
        data.user_mode = 2
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == "comfort"

    def test_preset_mode_refresh_returns_boost(self):
        """Refresh mode (3) -> boost preset."""
        data = make_sample_data()
        data.user_mode = 3
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == "boost"

    def test_preset_mode_fireplace(self):
        """Fireplace mode (4) -> fireplace preset."""
        data = make_sample_data()
        data.user_mode = 4
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == "fireplace"

    def test_preset_mode_away(self):
        """Away mode (5) -> away preset."""
        data = make_sample_data()
        data.user_mode = 5
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == "away"

    def test_preset_mode_holiday(self):
        """Holiday mode (6) -> holiday preset."""
        data = make_sample_data()
        data.user_mode = 6
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == "holiday"

    def test_preset_mode_cooker_hood_returns_none_preset(self):
        """Cooker hood mode (7) is not a user preset -> PRESET_NONE ('none')."""
        data = make_sample_data()
        data.user_mode = 7
        entity, _ = self._create_entity(data)
        assert entity.preset_mode == PRESET_NONE

    def test_preset_mode_none_data(self):
        """No data -> None."""
        entity, coord = self._create_entity()
        coord.data = None
        assert entity.preset_mode is None

    def test_preset_mode_none_user_mode(self):
        """user_mode is None -> None."""
        data = make_sample_data()
        data.user_mode = None
        entity, _ = self._create_entity(data)
        assert entity.preset_mode is None

    # --- Setting preset mode ---

    @pytest.mark.asyncio
    async def test_set_preset_away(self):
        """Setting 'away' preset should call async_set_timed_mode with correct args."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("away")
        coord.async_set_timed_mode.assert_called_once_with("away", 8)

    @pytest.mark.asyncio
    async def test_set_preset_boost(self):
        """Setting 'boost' preset should trigger 'refresh' timed mode."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("boost")
        coord.async_set_timed_mode.assert_called_once_with("refresh", 60)

    @pytest.mark.asyncio
    async def test_set_preset_comfort(self):
        """Setting 'comfort' preset should trigger 'crowded' timed mode."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("comfort")
        coord.async_set_timed_mode.assert_called_once_with("crowded", 4)

    @pytest.mark.asyncio
    async def test_set_preset_fireplace(self):
        """Setting 'fireplace' preset should trigger 'fireplace' timed mode."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("fireplace")
        coord.async_set_timed_mode.assert_called_once_with("fireplace", 30)

    @pytest.mark.asyncio
    async def test_set_preset_holiday(self):
        """Setting 'holiday' preset should trigger 'holiday' timed mode."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("holiday")
        coord.async_set_timed_mode.assert_called_once_with("holiday", 7)

    @pytest.mark.asyncio
    async def test_set_preset_none_cancels(self):
        """Setting 'none' preset should call async_set_mode('auto') to cancel timed mode."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode(PRESET_NONE)
        coord.async_set_mode.assert_called_once_with("auto")
        coord.async_set_timed_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_preset_unknown(self):
        """Setting an unknown preset should not call any mode change."""
        entity, coord = self._create_entity()
        await entity.async_set_preset_mode("turbo_unknown")
        coord.async_set_timed_mode.assert_not_called()
        coord.async_set_mode.assert_not_called()

    # --- Feature flags ---

    def test_supported_features_include_preset_mode(self):
        """Supported features should include PRESET_MODE."""
        from custom_components.systemair.climate import ClimateEntityFeature
        entity, _ = self._create_entity()
        assert entity._attr_supported_features & ClimateEntityFeature.PRESET_MODE

    def test_preset_modes_list(self):
        """Check the preset_modes attribute is the expected list."""
        entity, _ = self._create_entity()
        assert entity._attr_preset_modes == PRESET_MODES
        assert "away" in PRESET_MODES
        assert "boost" in PRESET_MODES
        assert "comfort" in PRESET_MODES
        assert "fireplace" in PRESET_MODES
        assert "holiday" in PRESET_MODES


# ---------------------------------------------------------------------------
# Cloud HVAC mode control tests
# ---------------------------------------------------------------------------


class TestCloudHvacMode:
    """Tests for HVAC mode control via cloud connections."""

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_cloud(self):
        """Setting HVAC mode to AUTO via cloud should call async_set_mode."""
        from custom_components.systemair.const import CONN_CLOUD

        coord = MockCoordinator(make_sample_data())
        coord.connection_type = CONN_CLOUD
        coord.async_set_mode = AsyncMock()
        entry = MockConfigEntry()
        entity = SystemairClimate(coord, entry)

        await entity.async_set_hvac_mode(HVAC_MODE_AUTO)

        coord.async_set_mode.assert_called_once_with("auto")

    @pytest.mark.asyncio
    async def test_set_hvac_mode_manual_cloud(self):
        """Setting HVAC mode to FAN_ONLY (manual) via cloud should call async_set_mode."""
        from custom_components.systemair.const import CONN_CLOUD

        coord = MockCoordinator(make_sample_data())
        coord.connection_type = CONN_CLOUD
        coord.async_set_mode = AsyncMock()
        entry = MockConfigEntry()
        entity = SystemairClimate(coord, entry)

        await entity.async_set_hvac_mode(HVAC_MODE_FAN_ONLY)

        coord.async_set_mode.assert_called_once_with("manual")

