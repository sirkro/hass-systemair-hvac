"""Tests for the switch platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.switch import (
    SystemairEcoModeSwitch,
    SystemairMoistureTransferSwitch,
    async_setup_entry,
)
from custom_components.systemair.const import DOMAIN
from custom_components.systemair.coordinator import SystemairData
from tests.conftest import MockConfigEntry, make_sample_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal mock coordinator for entity tests."""

    def __init__(self, data: SystemairData | None = None):
        self.data = data
        self.async_set_eco_mode = AsyncMock()
        self.async_set_moisture_transfer = AsyncMock()

    async def async_add_listener(self, *args, **kwargs):
        return lambda: None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSystemairEcoModeSwitch:
    """Tests for the ECO mode switch entity."""

    def _create_switch(
        self, data: SystemairData | None = None
    ) -> tuple[SystemairEcoModeSwitch, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        with patch.object(SystemairEcoModeSwitch, "__init__", lambda self, *a, **kw: None):
            switch = SystemairEcoModeSwitch.__new__(SystemairEcoModeSwitch)
            switch.coordinator = coordinator
            switch._attr_unique_id = f"{entry.entry_id}_eco_mode"
            switch._attr_name = "ECO mode"
            switch._attr_icon = "mdi:leaf"

        return switch, coordinator

    def test_is_on_true(self):
        data = make_sample_data()
        data.eco_mode = True
        switch, _ = self._create_switch(data)
        assert switch.is_on is True

    def test_is_on_false(self):
        data = make_sample_data()
        data.eco_mode = False
        switch, _ = self._create_switch(data)
        assert switch.is_on is False

    def test_is_on_none_data(self):
        switch, coord = self._create_switch()
        coord.data = None
        assert switch.is_on is None

    def test_is_on_eco_none(self):
        """When eco_mode is None (not yet populated), switch defaults to off."""
        data = make_sample_data()
        data.eco_mode = None
        switch, _ = self._create_switch(data)
        assert switch.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on(self):
        switch, coord = self._create_switch()
        await switch.async_turn_on()
        coord.async_set_eco_mode.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_turn_off(self):
        switch, coord = self._create_switch()
        await switch.async_turn_off()
        coord.async_set_eco_mode.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# async_setup_entry tests
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_creates_both_switches(self):
        """Should create both ECO mode and moisture transfer switches."""
        coordinator = MockCoordinator(data=make_sample_data())
        entry = MockConfigEntry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}
        add_entities = MagicMock()

        await async_setup_entry(hass, entry, add_entities)
        add_entities.assert_called_once()
        entities = add_entities.call_args[0][0]
        assert len(entities) == 2
        assert isinstance(entities[0], SystemairEcoModeSwitch)
        assert isinstance(entities[1], SystemairMoistureTransferSwitch)


# ---------------------------------------------------------------------------
# Moisture transfer switch tests
# ---------------------------------------------------------------------------


class TestSystemairMoistureTransferSwitch:
    """Tests for the moisture transfer switch entity."""

    def _create_switch(
        self, data: SystemairData | None = None
    ) -> tuple[SystemairMoistureTransferSwitch, MockCoordinator]:
        if data is None:
            data = make_sample_data()
        coordinator = MockCoordinator(data)
        entry = MockConfigEntry()

        with patch.object(SystemairMoistureTransferSwitch, "__init__", lambda self, *a, **kw: None):
            switch = SystemairMoistureTransferSwitch.__new__(SystemairMoistureTransferSwitch)
            switch.coordinator = coordinator
            switch._attr_unique_id = f"{entry.entry_id}_moisture_transfer"
            switch._attr_name = "Moisture transfer"
            switch._attr_icon = "mdi:water-sync"
            switch._attr_entity_registry_enabled_default = False

        return switch, coordinator

    def test_is_on_true(self):
        data = make_sample_data()
        data.moisture_transfer_enabled = True
        switch, _ = self._create_switch(data)
        assert switch.is_on is True

    def test_is_on_false(self):
        data = make_sample_data()
        data.moisture_transfer_enabled = False
        switch, _ = self._create_switch(data)
        assert switch.is_on is False

    def test_is_on_none_data(self):
        switch, coord = self._create_switch()
        coord.data = None
        assert switch.is_on is None

    def test_is_on_moisture_none(self):
        data = make_sample_data()
        data.moisture_transfer_enabled = None
        switch, _ = self._create_switch(data)
        assert switch.is_on is None

    @pytest.mark.asyncio
    async def test_turn_on(self):
        switch, coord = self._create_switch()
        await switch.async_turn_on()
        coord.async_set_moisture_transfer.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_turn_off(self):
        switch, coord = self._create_switch()
        await switch.async_turn_off()
        coord.async_set_moisture_transfer.assert_called_once_with(False)

    def test_disabled_by_default(self):
        """Moisture transfer switch should be disabled by default."""
        switch, _ = self._create_switch()
        assert switch._attr_entity_registry_enabled_default is False
