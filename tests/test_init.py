"""Tests for Systemair integration __init__.py (setup, teardown, services)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair import (
    SERVICE_SET_AWAY,
    SERVICE_SET_CROWDED,
    SERVICE_SET_FIREPLACE,
    SERVICE_SET_HOLIDAY,
    SERVICE_SET_REFRESH,
    PLATFORMS,
    async_setup_entry,
    async_unload_entry,
    _create_api,
    _register_services,
    _get_coordinator_for_entity,
)
from custom_components.systemair.const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONN_CLOUD,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from custom_components.systemair.coordinator import SystemairCoordinator, SystemairData
from tests.conftest import MockConfigEntry, make_mock_cloud_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockHass:
    """Minimal mock of HomeAssistant for testing __init__.py."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.services = MockServiceRegistry()
        self.config_entries = MockConfigEntries()
        self.helpers = MagicMock()

    async def async_create_task(self, coro):
        """Run a coroutine synchronously (mock)."""
        return await coro


class MockServiceRegistry:
    """Minimal service registry mock."""

    def __init__(self) -> None:
        self._services: dict[str, dict[str, Any]] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return domain in self._services and service in self._services[domain]

    def async_register(self, domain: str, service: str, handler, schema=None) -> None:
        self._services.setdefault(domain, {})[service] = {
            "handler": handler,
            "schema": schema,
        }

    def async_remove(self, domain: str, service: str) -> None:
        if domain in self._services:
            self._services[domain].pop(service, None)
            if not self._services[domain]:
                del self._services[domain]


class MockConfigEntries:
    """Minimal config entries mock."""

    def __init__(self) -> None:
        pass

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        pass

    async def async_unload_platforms(self, entry, platforms) -> bool:
        return True

    async def async_reload(self, entry_id: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests: PLATFORMS list
# ---------------------------------------------------------------------------


def test_platforms_list():
    """Verify all expected platforms are present."""
    names = [p.value if hasattr(p, "value") else str(p) for p in PLATFORMS]
    assert "climate" in names
    assert "sensor" in names
    assert "binary_sensor" in names
    assert "switch" in names
    assert "select" in names
    assert "number" in names
    assert len(PLATFORMS) == 6


# ---------------------------------------------------------------------------
# Tests: _create_api
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_api_cloud():
    """Test _create_api for Cloud connection."""
    entry = MockConfigEntry(data={
        CONF_CONNECTION_TYPE: CONN_CLOUD,
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        "machine_id": "machine_123",
        "machine_name": "Living Room",
    })
    hass = MockHass()

    mock_api_instance = MagicMock()
    mock_api_instance.login = AsyncMock()
    mock_api_instance.set_machine = MagicMock()

    with patch(
        "custom_components.systemair.cloud_api.SystemairCloudAPI",
        return_value=mock_api_instance,
    ):
        api = await _create_api(hass, entry)
    assert api is mock_api_instance
    mock_api_instance.login.assert_awaited_once()
    mock_api_instance.set_machine.assert_called_once_with("machine_123", "Living Room", device_type="LEGACY")


@pytest.mark.asyncio
async def test_create_api_unknown_type():
    """Test _create_api raises for unknown connection type."""
    entry = MockConfigEntry(data={CONF_CONNECTION_TYPE: "unknown"})
    hass = MockHass()
    with pytest.raises(ValueError, match="Unsupported connection type"):
        await _create_api(hass, entry)


# ---------------------------------------------------------------------------
# Tests: async_setup_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_reads_poll_interval_from_options():
    """Test that poll_interval is read from options first, then data."""
    hass = MockHass()
    entry = MockConfigEntry(
        data={
            CONF_CONNECTION_TYPE: CONN_CLOUD,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_POLL_INTERVAL: 20,
            "machine_id": "machine_123",
            "machine_name": "Living Room",
        },
        options={CONF_POLL_INTERVAL: 45},
    )
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    mock_api = make_mock_cloud_api()
    captured_poll_interval = None

    def capturing_init(self, hass_, *, connection_type, api, poll_interval=DEFAULT_POLL_INTERVAL):
        nonlocal captured_poll_interval
        captured_poll_interval = poll_interval

    with (
        patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI",
            return_value=mock_api,
        ),
        patch.object(
            SystemairCoordinator,
            "__init__",
            capturing_init,
        ),
        patch.object(
            SystemairCoordinator,
            "async_config_entry_first_refresh",
            new_callable=AsyncMock,
        ),
        patch.object(
            SystemairCoordinator,
            "async_start_cloud_websocket",
            new_callable=AsyncMock,
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert captured_poll_interval == 45


# ---------------------------------------------------------------------------
# Tests: async_unload_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unload_entry_cloud_with_close():
    """Test unloading a Cloud entry calls close() instead of disconnect()."""
    hass = MockHass()
    entry = MockConfigEntry(data={
        CONF_CONNECTION_TYPE: CONN_CLOUD,
    })

    mock_api = make_mock_cloud_api()
    # Remove disconnect to ensure close() is used
    del mock_api.disconnect

    coordinator = MagicMock(spec=SystemairCoordinator)
    coordinator.api = mock_api

    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    _register_services(hass)

    result = await async_unload_entry(hass, entry)
    assert result is True
    mock_api.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_keeps_services_if_other_entries_remain():
    """Test services are NOT removed if other entries still exist."""
    hass = MockHass()
    entry1 = MockConfigEntry(entry_id="entry_1")
    entry2 = MockConfigEntry(entry_id="entry_2")

    mock_api1 = make_mock_cloud_api()
    mock_api2 = make_mock_cloud_api()

    coord1 = MagicMock(spec=SystemairCoordinator)
    coord1.api = mock_api1
    coord2 = MagicMock(spec=SystemairCoordinator)
    coord2.api = mock_api2

    hass.data[DOMAIN] = {
        entry1.entry_id: coord1,
        entry2.entry_id: coord2,
    }
    _register_services(hass)

    result = await async_unload_entry(hass, entry1)
    assert result is True
    # entry2 still present, so services should remain
    assert hass.services.has_service(DOMAIN, SERVICE_SET_AWAY)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_REFRESH)


# ---------------------------------------------------------------------------
# Tests: _register_services
# ---------------------------------------------------------------------------


def test_register_services():
    """Test that all 5 timed-mode services are registered."""
    hass = MockHass()
    _register_services(hass)

    for svc in (
        SERVICE_SET_AWAY,
        SERVICE_SET_CROWDED,
        SERVICE_SET_FIREPLACE,
        SERVICE_SET_HOLIDAY,
        SERVICE_SET_REFRESH,
    ):
        assert hass.services.has_service(DOMAIN, svc), f"Service {svc} not registered"


def test_register_services_idempotent():
    """Registering services twice should not raise."""
    hass = MockHass()
    _register_services(hass)
    _register_services(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_AWAY)


# ---------------------------------------------------------------------------
# Tests: _get_coordinator_for_entity
# ---------------------------------------------------------------------------


def test_get_coordinator_for_entity_not_found():
    """Test returns None when entity_id is not in registry."""
    hass = MockHass()
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=mock_registry,
    ):
        result = _get_coordinator_for_entity(hass, "climate.fake_entity")
    assert result is None


def test_get_coordinator_for_entity_found():
    """Test returns correct coordinator when entity exists."""
    hass = MockHass()

    mock_entity = MagicMock()
    mock_entity.config_entry_id = "test_entry_id"

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entity

    coordinator = MagicMock(spec=SystemairCoordinator)
    hass.data[DOMAIN] = {"test_entry_id": coordinator}

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=mock_registry,
    ):
        result = _get_coordinator_for_entity(hass, "climate.systemair")
    assert result is coordinator


def test_get_coordinator_for_entity_entry_not_in_data():
    """Test returns None when entity exists but coordinator is not in data."""
    hass = MockHass()

    mock_entity = MagicMock()
    mock_entity.config_entry_id = "missing_entry_id"

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entity

    hass.data[DOMAIN] = {}

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=mock_registry,
    ):
        result = _get_coordinator_for_entity(hass, "climate.systemair")
    assert result is None


# ---------------------------------------------------------------------------
# Tests: Service schemas
# ---------------------------------------------------------------------------


def test_service_schemas_imported():
    """Verify that service schema constants are importable."""
    from custom_components.systemair import (
        SERVICE_AWAY_SCHEMA,
        SERVICE_CROWDED_SCHEMA,
        SERVICE_FIREPLACE_SCHEMA,
        SERVICE_HOLIDAY_SCHEMA,
        SERVICE_REFRESH_SCHEMA,
    )
    # Each schema should be a voluptuous Schema
    for schema in (
        SERVICE_AWAY_SCHEMA,
        SERVICE_CROWDED_SCHEMA,
        SERVICE_FIREPLACE_SCHEMA,
        SERVICE_HOLIDAY_SCHEMA,
        SERVICE_REFRESH_SCHEMA,
    ):
        assert schema is not None


# ---------------------------------------------------------------------------
# Tests: Cloud WebSocket lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_cloud_starts_websocket():
    """Test that cloud connection type starts the WebSocket after setup."""
    hass = MockHass()
    entry = MockConfigEntry(data={
        CONF_CONNECTION_TYPE: CONN_CLOUD,
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        "machine_id": "machine_123",
        "machine_name": "Living Room",
    })
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    mock_api = make_mock_cloud_api()

    with (
        patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI",
            return_value=mock_api,
        ),
        patch(
            "custom_components.systemair.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ),
        patch.object(
            SystemairCoordinator,
            "async_config_entry_first_refresh",
            new_callable=AsyncMock,
        ),
        patch.object(
            SystemairCoordinator,
            "async_start_cloud_websocket",
            new_callable=AsyncMock,
        ) as mock_ws_start,
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    mock_ws_start.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_entry_cloud_cancels_ws_task():
    """Test that unloading a cloud entry cancels the WebSocket listener task."""
    hass = MockHass()
    entry = MockConfigEntry(data={
        CONF_CONNECTION_TYPE: CONN_CLOUD,
    })

    mock_api = make_mock_cloud_api()
    # Remove disconnect to ensure close() is used
    del mock_api.disconnect

    # Simulate an active WS listener task on the API
    mock_ws_task = MagicMock()
    mock_api._ws_listener_task = mock_ws_task

    coordinator = MagicMock(spec=SystemairCoordinator)
    coordinator.api = mock_api

    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    _register_services(hass)

    result = await async_unload_entry(hass, entry)
    assert result is True
    mock_ws_task.cancel.assert_called_once()
    mock_api.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_entry_no_ws_task():
    """Test that unloading works fine when there is no WS listener task."""
    hass = MockHass()
    entry = MockConfigEntry(data={
        CONF_CONNECTION_TYPE: CONN_CLOUD,
    })

    mock_api = make_mock_cloud_api()
    del mock_api.disconnect

    # No active WS listener task
    mock_api._ws_listener_task = None

    coordinator = MagicMock(spec=SystemairCoordinator)
    coordinator.api = mock_api

    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    _register_services(hass)

    result = await async_unload_entry(hass, entry)
    assert result is True
    # No crash, and close() is still called
    mock_api.close.assert_awaited_once()
