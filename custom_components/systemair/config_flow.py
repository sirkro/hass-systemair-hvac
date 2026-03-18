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

"""Config flow for Systemair integration."""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
)
from homeassistant.data_entry_flow import section

from .const import (
    CONF_API_URL,
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_WS_URL,
    CONN_CLOUD,
    DEFAULT_CLOUD_API_URL,
    DEFAULT_CLOUD_WS_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _validate_url(url: str, allowed_schemes: tuple[str, ...]) -> bool:
    """Validate that a URL has an allowed scheme and a non-private host.

    Resolves DNS names to check that they don't point to private/reserved IPs
    (SSRF mitigation). If DNS resolution fails, the URL is still allowed since
    it may resolve at runtime on the user's network.
    """
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in allowed_schemes:
            return False
        if not parsed.hostname:
            return False
        # Check the hostname — either a literal IP or a DNS name
        hostname = parsed.hostname
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_reserved or addr.is_loopback:
                return False
        except ValueError:
            # hostname is a DNS name — resolve and check all resulting IPs
            try:
                results = socket.getaddrinfo(hostname, None)
                for _family, _type, _proto, _canonname, sockaddr in results:
                    ip_str = sockaddr[0]
                    addr = ipaddress.ip_address(ip_str)
                    if addr.is_private or addr.is_reserved or addr.is_loopback:
                        return False
            except socket.gaierror:
                # DNS resolution failed — allow the URL (may resolve at runtime)
                pass
        return True
    except Exception:  # noqa: BLE001
        return False


class SystemairConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Systemair."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._cloud_devices: list[dict[str, Any]] = []
        self._cloud_email: str = ""
        self._cloud_password: str = ""
        self._cloud_poll_interval: int = DEFAULT_POLL_INTERVAL
        self._cloud_api_url: str | None = None
        self._cloud_ws_url: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - go directly to cloud login."""
        return await self.async_step_cloud(user_input)

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Cloud WebSocket configuration - credentials step.

        Note: The password is stored in the config entry data in plain text.
        This is a standard Home Assistant convention for integrations that
        need to re-authenticate (e.g., after HA restart). HA encrypts the
        storage file at rest on supported platforms.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            advanced = user_input.get("advanced") or {}
            poll_interval = advanced.get(
                CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
            )
            api_url = advanced.get(CONF_API_URL, "").strip() or None
            ws_url = advanced.get(CONF_WS_URL, "").strip() or None

            # Validate custom URLs if provided
            if api_url and not _validate_url(api_url, ("http", "https")):
                errors["base"] = "invalid_url"
            elif ws_url and not _validate_url(ws_url, ("ws", "wss")):
                errors["base"] = "invalid_url"
            else:
                from .cloud_api import SystemairCloudAPI, CloudAPIError, AuthenticationError

                api = SystemairCloudAPI(email, password, api_url=api_url, ws_url=ws_url)
                try:
                    await api.login()
                    devices = await api.get_devices()
                    if not devices:
                        errors["base"] = "no_devices"
                    elif len(devices) == 1:
                        # Single device, create entry directly
                        device = devices[0]
                        await self.async_set_unique_id(
                            f"systemair_cloud_{device['machine_id']}"
                        )
                        self._abort_if_unique_id_configured()

                        entry_data = {
                            CONF_CONNECTION_TYPE: CONN_CLOUD,
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                            CONF_POLL_INTERVAL: poll_interval,
                            "machine_id": device["machine_id"],
                            "machine_name": device["name"],
                            "device_type": device.get("device_type", "LEGACY"),
                        }
                        if api_url:
                            entry_data[CONF_API_URL] = api_url
                        if ws_url:
                            entry_data[CONF_WS_URL] = ws_url

                        return self.async_create_entry(
                            title=f"Systemair Cloud ({device['name']})",
                            data=entry_data,
                        )
                    else:
                        # Multiple devices, let user choose
                        self._cloud_devices = devices
                        self._cloud_email = email
                        self._cloud_password = password
                        self._cloud_poll_interval = poll_interval
                        self._cloud_api_url = api_url
                        self._cloud_ws_url = ws_url
                        return await self.async_step_cloud_device()
                except AuthenticationError as err:
                    _LOGGER.warning("Cloud authentication failed: %s", err)
                    errors["base"] = "invalid_auth"
                except CloudAPIError as err:
                    _LOGGER.exception("Cloud connection failed: %s", err)
                    errors["base"] = "cannot_connect"
                finally:
                    await api.close()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional("advanced"): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    CONF_POLL_INTERVAL,
                                    default=DEFAULT_POLL_INTERVAL,
                                ): vol.All(
                                    vol.Coerce(int), vol.Range(min=10, max=300)
                                ),
                                vol.Optional(CONF_API_URL, default=""): str,
                                vol.Optional(CONF_WS_URL, default=""): str,
                            }
                        ),
                        {"collapsed": True},
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_cloud_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle cloud device selection when multiple devices exist."""
        if user_input is not None:
            machine_id = user_input["machine_id"]
            device = next(
                (d for d in self._cloud_devices if d["machine_id"] == machine_id),
                None,
            )
            if device:
                await self.async_set_unique_id(
                    f"systemair_cloud_{machine_id}"
                )
                self._abort_if_unique_id_configured()

                entry_data = {
                    CONF_CONNECTION_TYPE: CONN_CLOUD,
                    CONF_EMAIL: self._cloud_email,
                    CONF_PASSWORD: self._cloud_password,
                    CONF_POLL_INTERVAL: self._cloud_poll_interval,
                    "machine_id": machine_id,
                    "machine_name": device["name"],
                    "device_type": device.get("device_type", "LEGACY"),
                }
                if self._cloud_api_url:
                    entry_data[CONF_API_URL] = self._cloud_api_url
                if self._cloud_ws_url:
                    entry_data[CONF_WS_URL] = self._cloud_ws_url

                return self.async_create_entry(
                    title=f"Systemair Cloud ({device['name']})",
                    data=entry_data,
                )

        device_options = {
            d["machine_id"]: f"{d['name']} ({d.get('connection_status', 'unknown')})"
            for d in self._cloud_devices
        }

        return self.async_show_form(
            step_id="cloud_device",
            data_schema=vol.Schema(
                {
                    vol.Required("machine_id"): vol.In(device_options),
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SystemairOptionsFlow:
        """Get the options flow for this handler."""
        return SystemairOptionsFlow(config_entry)


class SystemairOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options flow for Systemair."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_poll = self.options.get(
            CONF_POLL_INTERVAL,
            self.config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=current_poll
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
        )
