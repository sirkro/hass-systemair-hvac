"""Tests for the select platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.select import SystemairUserModeSelect, USER_MODE_OPTIONS
from custom_components.systemair.coordinator import SystemairData
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal mock coordinator for entity tests."""

    def __init__(self, data: SystemairData | None = None):
        self.data = data
        self.last_update_success = True
        self.async_set_mode = AsyncMock()

    async def async_add_listener(self, *args, **kwargs):
        return lambda: None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUserModeOptions:
    """Test the user mode options constant."""

    def test_options(self):
        assert "Auto" in USER_MODE_OPTIONS
        assert "Manual" in USER_MODE_OPTIONS
        assert len(USER_MODE_OPTIONS) == 2


class TestSystemairUserModeSelect:
    """Tests for the user mode select entity."""

    def _create_select(
        self, data: SystemairData | None = None
    ) -> tuple[SystemairUserModeSelect, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        with patch.object(SystemairUserModeSelect, "__init__", lambda self, *a, **kw: None):
            select = SystemairUserModeSelect.__new__(SystemairUserModeSelect)
            select.coordinator = coordinator
            select._attr_unique_id = f"{entry.entry_id}_user_mode_select"
            select._attr_options = USER_MODE_OPTIONS

        return select, coordinator

    def test_current_option_auto(self):
        data = make_sample_data()
        data.user_mode = 0
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_manual(self):
        data = make_sample_data()
        data.user_mode = 1
        select, _ = self._create_select(data)
        assert select.current_option == "Manual"

    def test_current_option_timed_mode_returns_auto(self):
        """Timed modes show 'Auto' as the base mode that will resume."""
        data = make_sample_data()
        data.user_mode = 5  # Away mode
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_crowded(self):
        """Crowded mode (2) is a timed mode -> shows Auto."""
        data = make_sample_data()
        data.user_mode = 2
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_refresh(self):
        """Refresh mode (3) is a timed mode -> shows Auto."""
        data = make_sample_data()
        data.user_mode = 3
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_fireplace(self):
        """Fireplace mode (4) is a timed mode -> shows Auto."""
        data = make_sample_data()
        data.user_mode = 4
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_holiday(self):
        """Holiday mode (6) is a timed mode -> shows Auto."""
        data = make_sample_data()
        data.user_mode = 6
        select, _ = self._create_select(data)
        assert select.current_option == "Auto"

    def test_current_option_none_data(self):
        select, coord = self._create_select()
        coord.data = None
        assert select.current_option is None

    def test_current_option_none_mode(self):
        data = make_sample_data()
        data.user_mode = None
        select, _ = self._create_select(data)
        assert select.current_option is None

    @pytest.mark.asyncio
    async def test_select_auto(self):
        select, coord = self._create_select()
        await select.async_select_option("Auto")
        coord.async_set_mode.assert_called_once_with("auto")

    @pytest.mark.asyncio
    async def test_select_manual(self):
        select, coord = self._create_select()
        await select.async_select_option("Manual")
        coord.async_set_mode.assert_called_once_with("manual")
