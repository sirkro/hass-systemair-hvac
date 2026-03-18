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

"""The Systemair integration."""
from __future__ import annotations

import functools
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_API_URL,
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_WS_URL,
    CONN_CLOUD,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import SystemairCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

# Service names
SERVICE_SET_AWAY = "set_away_mode"
SERVICE_SET_CROWDED = "set_crowded_mode"
SERVICE_SET_FIREPLACE = "set_fireplace_mode"
SERVICE_SET_HOLIDAY = "set_holiday_mode"
SERVICE_SET_REFRESH = "set_refresh_mode"

# Service schemas
SERVICE_AWAY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=72)
        ),
    }
)

SERVICE_CROWDED_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
    }
)

SERVICE_FIREPLACE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
    }
)

SERVICE_HOLIDAY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
    }
)

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=240)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Systemair from a config entry."""
    connection_type = entry.data[CONF_CONNECTION_TYPE]
    poll_interval = entry.options.get(
        CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    )

    # Create the appropriate API client
    api = await _create_api(hass, entry)

    # Create coordinator
    coordinator = SystemairCoordinator(
        hass,
        connection_type=connection_type,
        api=api,
        poll_interval=poll_interval,
    )

    # Do initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start cloud WebSocket for real-time push events (cloud only)
    if connection_type == CONN_CLOUD:
        await coordinator.async_start_cloud_websocket()

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_AWAY):
        _register_services(hass)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — reload the entry to apply new settings."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SystemairCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Cancel WebSocket listener task if running
        ws_task = getattr(coordinator.api, "_ws_listener_task", None)
        if ws_task is not None:
            ws_task.cancel()
        # Close API connection
        await coordinator.api.close()

    # Remove services if no entries left
    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)
        for service in (
            SERVICE_SET_AWAY,
            SERVICE_SET_CROWDED,
            SERVICE_SET_FIREPLACE,
            SERVICE_SET_HOLIDAY,
            SERVICE_SET_REFRESH,
        ):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def _create_api(hass: HomeAssistant, entry: ConfigEntry):
    """Create the Cloud API client."""
    connection_type = entry.data[CONF_CONNECTION_TYPE]

    if connection_type != CONN_CLOUD:
        raise ValueError(f"Unsupported connection type: {connection_type}")

    from .cloud_api import SystemairCloudAPI
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    api = SystemairCloudAPI(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        session=session,
        api_url=entry.data.get(CONF_API_URL),
        ws_url=entry.data.get(CONF_WS_URL),
    )
    await api.login()
    api.set_machine(
        entry.data["machine_id"],
        entry.data.get("machine_name"),
        device_type=entry.data.get("device_type", "LEGACY"),
    )
    return api


def _get_coordinator_for_entity(
    hass: HomeAssistant, entity_id: str
) -> SystemairCoordinator | None:
    """Find the coordinator for a given entity_id."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return None
    coordinators = hass.data.get(DOMAIN, {})
    return coordinators.get(entry.config_entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register Systemair services."""

    async def _handle_timed_mode(call: ServiceCall, *, mode: str) -> None:
        """Handle a timed mode service call."""
        entity_id = call.data["entity_id"]
        duration = call.data["duration"]

        coordinator = _get_coordinator_for_entity(hass, entity_id)
        if coordinator is None:
            _LOGGER.error("Could not find coordinator for entity %s", entity_id)
            return

        await coordinator.async_set_timed_mode(mode, duration)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AWAY,
        functools.partial(_handle_timed_mode, mode="away"),
        schema=SERVICE_AWAY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CROWDED,
        functools.partial(_handle_timed_mode, mode="crowded"),
        schema=SERVICE_CROWDED_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FIREPLACE,
        functools.partial(_handle_timed_mode, mode="fireplace"),
        schema=SERVICE_FIREPLACE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HOLIDAY,
        functools.partial(_handle_timed_mode, mode="holiday"),
        schema=SERVICE_HOLIDAY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_REFRESH,
        functools.partial(_handle_timed_mode, mode="refresh"),
        schema=SERVICE_REFRESH_SCHEMA,
    )
