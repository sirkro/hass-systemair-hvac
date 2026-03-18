# Systemair HVAC integration for Home Assistant
# Based on com.systemair by balmli (https://github.com/balmli/com.systemair)
# New cloud API based on python-systemair-saveconnect by perara
# (https://github.com/perara/python-systemair-saveconnect, MIT license)
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

"""Cloud API for Systemair HVAC units via Keycloak OIDC + GraphQL.

Systemair's cloud platform uses two GraphQL endpoints:
  - Gateway API (/gateway/api): Account/device listing
  - Remote API (/gateway/remote-api): Device control (read/write registers)

Authentication uses Keycloak OIDC (3-step: auth page -> form POST -> token exchange).

The Remote API uses "data item IDs" (integers) that differ from Modbus register
numbers. This module discovers the mapping at initialization via ExportDataItems
and maintains it for efficient read/write operations.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Keycloak / OIDC endpoints
DEFAULT_SSO_URL = "https://sso.systemair.com/auth/realms/iot/protocol/openid-connect"
DEFAULT_AUTH_URL = f"{DEFAULT_SSO_URL}/auth"
DEFAULT_TOKEN_URL = f"{DEFAULT_SSO_URL}/token"

# OIDC client configuration
OIDC_CLIENT_ID = "iot-application"
OIDC_REDIRECT_URI = "https://homesolutions.systemair.com"
OIDC_SCOPE = "openid email profile"

# API endpoints
DEFAULT_GATEWAY_API_URL = "https://homesolutions.systemair.com/gateway/api"
DEFAULT_REMOTE_API_URL = "https://homesolutions.systemair.com/gateway/remote-api"
DEFAULT_WS_URL = "wss://homesolutions.systemair.com/streaming/"

# Device type constants
DEVICE_TYPE_LEGACY = "LEGACY"

# Regex to extract the Keycloak form action URL from the login page HTML.
_FORM_ACTION_RE = re.compile(
    r'<form\s[^>]*action="([^"]+)"', re.IGNORECASE
)

# ──────────────────────────────────────────────
# GraphQL queries and mutations
# ──────────────────────────────────────────────

# Gateway API queries (account/device listing)
GET_ACCOUNT_DEVICES_QUERY = """{
  GetAccountDevices {
    identifier
    name
    deviceType { type }
    status {
      connectionStatus
      serialNumber
      model
      hasAlarms
      units { temperature pressure flow }
    }
  }
}"""

BROADCAST_DEVICE_STATUSES_QUERY = """query BroadcastDeviceStatuses($deviceIds: [String]) {
  BroadcastDeviceStatuses(deviceIds: $deviceIds)
}"""

# Remote API queries (device control)
GET_DEVICE_STATUS_QUERY = """{
  GetDeviceStatus {
    id
    connectivity
    activeAlarms
    temperature
    airflow
    humidity
    co2
    userMode
    filterExpiration
    serialNumber
    model
  }
}"""

# Fallback query without the extra fields (in case the schema
# doesn't include humidity/co2/userMode on GetDeviceStatus)
GET_DEVICE_STATUS_QUERY_BASIC = """{
  GetDeviceStatus {
    id
    connectivity
    activeAlarms
    temperature
    airflow
    filterExpiration
    serialNumber
    model
  }
}"""

GET_DATA_ITEMS_QUERY = """query GetDataItems($input: [Int]) {
  GetDataItems(input: $input)
}"""

EXPORT_DATA_ITEMS_QUERY = """{
  ExportDataItems {
    version
    type
    dataItems
  }
}"""

WRITE_DATA_ITEMS_MUTATION = """mutation WriteDataItems($input: WriteDataItemsInput!) {
  WriteDataItems(input: $input)
}"""

GET_ACTIVE_ALARMS_QUERY = """{
  GetActiveAlarms {
    alarms {
      title
      description
      timestamp
      stopping
      acknowledged
    }
  }
}"""

GET_FILTER_INFO_QUERY = """{
  GetFilterInformation {
    selectedFilter
    itemNumber
  }
}"""


class CloudAPIError(Exception):
    """Error communicating with Systemair cloud."""


class AuthenticationError(CloudAPIError):
    """Authentication failed (bad credentials, expired tokens, etc.)."""


class SystemairCloudAPI:
    """Client for Systemair cloud via Keycloak OIDC + GraphQL.

    Authentication flow:
      1. GET the Keycloak auth URL to receive the login form HTML
      2. POST email/password to the form action URL
      3. Exchange the authorization code for OIDC tokens

    Data operations:
      - get_devices(): List devices via GetAccountDevices (gateway API)
      - read_params(): Read register values via GetDataItems (remote API)
      - write_param(): Write register value via WriteDataItems (remote API)
      - get_device_status(): Quick status via GetDeviceStatus (remote API)
    """

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        api_url: str | None = None,
        ws_url: str | None = None,
        auth_url: str | None = None,
        token_url: str | None = None,
    ) -> None:
        """Initialize the Cloud API client.

        Args:
            email: Systemair account email.
            password: Systemair account password.
            session: Optional aiohttp session (reuse HA's session).
            api_url: Override for the gateway API URL.
            ws_url: Override for the WebSocket URL.
            auth_url: Override for the Keycloak auth URL (for testing).
            token_url: Override for the Keycloak token URL (for testing).
        """
        self._email = email
        self._password = password
        self._session = session
        self._owns_session = session is None
        self._gateway_api_url = api_url or DEFAULT_GATEWAY_API_URL
        self._remote_api_url = self._derive_remote_api_url(self._gateway_api_url)
        self._ws_url = ws_url or DEFAULT_WS_URL
        self._auth_url = auth_url or DEFAULT_AUTH_URL
        self._token_url = token_url or DEFAULT_TOKEN_URL

        # OIDC token data
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float = 0  # unix timestamp when access_token expires

        # Device selection
        self._device_id: str | None = None
        self._device_name: str | None = None
        self._device_type: str = DEVICE_TYPE_LEGACY  # From GetAccountDevices deviceType.type

        # Data item ID mapping: modbus_register -> data_item_id
        self._modbus_to_data_item: dict[int, int] = {}
        # Data item ID -> full item info (for reading values)
        self._data_item_cache: dict[int, dict[str, Any]] = {}
        self._mapping_initialized: bool = False

        # WebSocket listener task reference (prevent GC)
        self._ws_listener_task: asyncio.Task[None] | None = None

        # Rate limiting for login attempts
        self._consecutive_login_failures: int = 0
        self._last_login_attempt: float = 0

        # Whether to use the basic status query (without humidity/userMode)
        self._use_basic_status_query: bool = False

        self._lock = asyncio.Lock()
        self._mapping_lock = asyncio.Lock()

    @staticmethod
    def _derive_remote_api_url(gateway_url: str) -> str:
        """Derive the remote API URL from the gateway API URL.

        The remote API is at /gateway/remote-api, sibling of /gateway/api.
        """
        if gateway_url.endswith("/gateway/api"):
            return gateway_url.replace("/gateway/api", "/gateway/remote-api")
        # For custom/test URLs, append /remote-api
        return gateway_url.rstrip("/") + "/remote-api"

    @property
    def device_id(self) -> str | None:
        """Return the selected device identifier."""
        return self._device_id

    @property
    def device_name(self) -> str | None:
        """Return the selected device name."""
        return self._device_name

    # Keep backward-compatible aliases used by config_flow and __init__
    @property
    def machine_id(self) -> str | None:
        """Return the selected device identifier (alias)."""
        return self._device_id

    @property
    def machine_name(self) -> str | None:
        """Return the selected device name (alias)."""
        return self._device_name

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close connections and clean up."""
        if self._ws_listener_task and not self._ws_listener_task.done():
            self._ws_listener_task.cancel()
            self._ws_listener_task = None
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> str:
        """Perform the full Keycloak OIDC login flow.

        Returns:
            The access token string.

        Raises:
            AuthenticationError: If credentials are invalid or login fails.
            CloudAPIError: If there's a network or protocol error.
        """
        self._last_login_attempt = time.time()
        session = self._get_session()

        try:
            # Step 1: GET the Keycloak auth page to get the login form
            auth_params = {
                "client_id": OIDC_CLIENT_ID,
                "redirect_uri": OIDC_REDIRECT_URI,
                "response_type": "code",
                "scope": OIDC_SCOPE,
            }

            async with session.get(
                self._auth_url,
                params=auth_params,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    self._consecutive_login_failures += 1
                    raise CloudAPIError(
                        f"Failed to get login page: HTTP {resp.status}"
                    )
                auth_page_url = str(resp.url)
                html = await resp.text()
                _LOGGER.debug(
                    "Step 1: Got auth page, status=%d, url=%s, length=%d",
                    resp.status, resp.url, len(html),
                )

            # Check if Keycloak already redirected us (session cookie valid).
            # In this case the final URL already contains a 'code' parameter
            # and we can skip the login form POST entirely.
            auth_parsed = urlparse(auth_page_url)
            auth_query = parse_qs(auth_parsed.query)
            code = auth_query.get("code", [None])[0]

            if code:
                _LOGGER.debug(
                    "Already authenticated (session cookie), "
                    "skipping form POST. code=%s",
                    code[:10] + "..." if code else None,
                )
            else:
                # Step 2: Extract the form action URL from the HTML
                match = _FORM_ACTION_RE.search(html)
                if not match:
                    self._consecutive_login_failures += 1
                    raise CloudAPIError(
                        "Could not find login form action URL in Keycloak page"
                    )
                form_action = match.group(1).replace("&amp;", "&")
                _LOGGER.debug("Step 2: Form action URL: %s", form_action)

                # Step 3: POST credentials to the form action URL
                form_data = {
                    "username": self._email,
                    "password": self._password,
                    "rememberMe": "on",
                    "credentialId": "",
                }

                async with session.post(
                    form_action,
                    data=form_data,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    final_url = str(resp.url)
                    _LOGGER.debug(
                        "Step 3: Form POST final url=%s, status=%d",
                        final_url, resp.status,
                    )

                # Step 4: Extract authorization code from the final redirect URL
                parsed = urlparse(final_url)
                query_params = parse_qs(parsed.query)
                code = query_params.get("code", [None])[0]

                if not code:
                    error = query_params.get("error", [None])[0]
                    error_desc = query_params.get(
                        "error_description", [""]
                    )[0]
                    self._consecutive_login_failures += 1
                    if error:
                        raise AuthenticationError(
                            f"Login failed: {error} - {error_desc}"
                        )
                    if "sso.systemair.com" in final_url:
                        raise AuthenticationError(
                            "Invalid email or password"
                        )
                    raise CloudAPIError(
                        f"No authorization code in redirect URL: "
                        f"{final_url}"
                    )

            _LOGGER.debug(
                "Step 4: Authorization code: %s",
                code[:10] + "..." if code else None,
            )

            # Step 5: Exchange authorization code for tokens
            token_data = {
                "grant_type": "authorization_code",
                "client_id": OIDC_CLIENT_ID,
                "redirect_uri": OIDC_REDIRECT_URI,
                "code": code,
            }

            async with session.post(
                self._token_url,
                data=token_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    error_body = await resp.text()
                    _LOGGER.debug(
                        "Step 5: Token exchange failed: HTTP %d, body: %s",
                        resp.status, error_body[:500],
                    )
                    self._consecutive_login_failures += 1
                    raise CloudAPIError(
                        f"Token exchange failed: HTTP {resp.status} - "
                        f"{error_body[:200]}"
                    )
                token_response = await resp.json()

            access_token = token_response.get("access_token")
            if not access_token:
                self._consecutive_login_failures += 1
                raise CloudAPIError("No access_token in token response")

            self._access_token = access_token
            self._refresh_token = token_response.get("refresh_token")

            # Calculate expiry (subtract 30s safety margin)
            expires_in = token_response.get("expires_in", 300)
            self._token_expiry = time.time() + expires_in - 30

            self._consecutive_login_failures = 0
            _LOGGER.debug("OIDC login successful")
            return access_token

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._consecutive_login_failures += 1
            raise CloudAPIError(f"Login request failed: {err}") from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token.

        Falls back to full login if refresh fails.
        """
        if not self._refresh_token:
            await self.login()
            return

        session = self._get_session()
        try:
            token_data = {
                "grant_type": "refresh_token",
                "client_id": OIDC_CLIENT_ID,
                "refresh_token": self._refresh_token,
            }

            async with session.post(
                self._token_url,
                data=token_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug(
                        "Token refresh failed (HTTP %d), doing full login",
                        resp.status,
                    )
                    await self.login()
                    return

                token_response = await resp.json()

            access_token = token_response.get("access_token")
            if not access_token:
                _LOGGER.debug(
                    "No access_token in refresh response, doing full login"
                )
                await self.login()
                return

            self._access_token = access_token
            self._refresh_token = token_response.get(
                "refresh_token", self._refresh_token
            )
            expires_in = token_response.get("expires_in", 300)
            self._token_expiry = time.time() + expires_in - 30
            self._consecutive_login_failures = 0

            _LOGGER.debug("Token refreshed successfully")

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug(
                "Token refresh network error: %s, doing full login", err
            )
            await self.login()

    async def _ensure_token(self) -> None:
        """Ensure we have a valid access token.

        Refreshes or re-authenticates as needed, with exponential backoff
        on consecutive failures.
        """
        if self._access_token and time.time() < self._token_expiry:
            return

        async with self._lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if self._access_token and time.time() < self._token_expiry:
                return

            # Exponential backoff: 2^failures seconds, capped at 300s (5 min)
            if self._consecutive_login_failures > 0:
                backoff = min(2 ** self._consecutive_login_failures, 300)
                elapsed = time.time() - self._last_login_attempt
                if elapsed < backoff:
                    raise CloudAPIError(
                        f"Login backoff: next attempt in {backoff - elapsed:.0f}s "
                        f"(attempt {self._consecutive_login_failures + 1})"
                    )

            if self._refresh_token:
                await self._refresh_access_token()
            else:
                await self.login()

    # ------------------------------------------------------------------
    # GraphQL helpers
    # ------------------------------------------------------------------

    async def _gateway_request(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL request against the gateway API.

        Used for account/device listing operations.
        """
        return await self._graphql_request(
            self._gateway_api_url, query, variables
        )

    async def _remote_request(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL request against the remote API.

        Used for device control operations. Requires a device to be selected.
        Automatically adds device-id and device-type headers.
        """
        if not self._device_id:
            raise CloudAPIError(
                "No device selected (call set_machine first)"
            )
        extra_headers = {
            "device-id": self._device_id,
            "device-type": self._device_type,
        }
        return await self._graphql_request(
            self._remote_api_url, query, variables, extra_headers
        )

    async def _graphql_request(
        self,
        url: str,
        query: str,
        variables: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL request.

        Args:
            url: The GraphQL endpoint URL.
            query: The GraphQL query/mutation string.
            variables: Optional variables dict.
            extra_headers: Additional headers (e.g., device-id).

        Returns:
            The parsed JSON response.

        Raises:
            CloudAPIError: On network or GraphQL errors.
        """
        await self._ensure_token()
        session = self._get_session()

        payload: dict[str, Any] = {
            "query": query,
            "variables": variables or {},
        }

        headers = {
            "x-access-token": self._access_token,
            "content-type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        try:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    # Token expired mid-request, try refresh + retry once.
                    # Use lock to prevent concurrent 401 handlers from
                    # racing to refresh the token simultaneously.
                    _LOGGER.debug("Got 401, refreshing token and retrying")
                    stale_token = self._access_token
                    async with self._lock:
                        if self._access_token == stale_token:
                            # No other coroutine refreshed yet — do it now
                            await self._refresh_access_token()
                    headers["x-access-token"] = self._access_token
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as retry_resp:
                        if retry_resp.status != 200:
                            raise CloudAPIError(
                                "GraphQL request failed after retry: "
                                f"HTTP {retry_resp.status}"
                            )
                        return await retry_resp.json()

                if resp.status != 200:
                    error_body = await resp.text()
                    _LOGGER.error(
                        "GraphQL request failed: HTTP %d, body: %s",
                        resp.status,
                        error_body[:500],
                    )
                    raise CloudAPIError(
                        f"GraphQL request failed: HTTP {resp.status}"
                    )
                return await resp.json()

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise CloudAPIError(f"GraphQL request failed: {err}") from err

    # ------------------------------------------------------------------
    # Device listing (gateway API)
    # ------------------------------------------------------------------

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices associated with the account.

        Returns:
            List of dicts with keys: machine_id, name, connection_status,
            device_type, model, serial_number.
        """
        data = await self._gateway_request(GET_ACCOUNT_DEVICES_QUERY)

        if data.get("errors"):
            raise CloudAPIError(
                "GetAccountDevices failed: "
                f"{data['errors'][0].get('message', 'Unknown error')}"
            )

        devices = data.get("data", {}).get("GetAccountDevices")
        if devices is None:
            raise CloudAPIError("No device data in response")

        return [
            {
                "machine_id": d["identifier"],
                "name": d.get("name", "Unknown"),
                "connection_status": (
                    d.get("status", {}).get("connectionStatus", "unknown")
                ),
                "device_type": (
                    d.get("deviceType", {}).get("type", DEVICE_TYPE_LEGACY)
                ),
                "model": d.get("status", {}).get("model"),
                "serial_number": d.get("status", {}).get("serialNumber"),
            }
            for d in devices
        ]

    def set_machine(
        self,
        machine_id: str,
        name: str | None = None,
        device_type: str = DEVICE_TYPE_LEGACY,
    ) -> None:
        """Set the target device for read/write operations.

        Args:
            machine_id: Device identifier (e.g., 'IAM_24800001239C').
            name: Optional human-readable name.
            device_type: Device type from GetAccountDevices (e.g., 'LEGACY').
        """
        self._device_id = machine_id
        self._device_name = name
        self._device_type = device_type
        # Reset mapping when device changes
        self._mapping_initialized = False
        self._modbus_to_data_item.clear()
        self._data_item_cache.clear()

    # ------------------------------------------------------------------
    # Data item ID mapping
    # ------------------------------------------------------------------

    async def _ensure_mapping(self) -> None:
        """Ensure the modbus-to-data-item-ID mapping is initialized.

        Calls ExportDataItems to discover the mapping between Modbus
        register numbers and the cloud API's data item IDs.

        Uses a separate _mapping_lock (not _lock) to avoid deadlock:
        _remote_request -> _ensure_token also acquires _lock.
        """
        if self._mapping_initialized:
            return

        async with self._mapping_lock:
            if self._mapping_initialized:
                return

            _LOGGER.debug("Initializing data item ID mapping via ExportDataItems")
            data = await self._remote_request(EXPORT_DATA_ITEMS_QUERY)

            if data.get("errors"):
                raise CloudAPIError(
                    "ExportDataItems failed: "
                    f"{data['errors'][0].get('message', 'Unknown')}"
                )

            export = data.get("data", {}).get("ExportDataItems")
            if not export:
                raise CloudAPIError("No ExportDataItems in response")

            data_items = export.get("dataItems")
            if data_items is None:
                raise CloudAPIError("No dataItems in ExportDataItems response")

            # dataItems may be a JSON string or already a list
            if isinstance(data_items, str):
                try:
                    data_items = json.loads(data_items)
                except (json.JSONDecodeError, TypeError) as err:
                    raise CloudAPIError(
                        f"Could not parse ExportDataItems: {err}"
                    ) from err

            if not isinstance(data_items, list):
                raise CloudAPIError(
                    f"Unexpected dataItems type: {type(data_items)}"
                )

            for item in data_items:
                item_id = item.get("id")
                ext = item.get("extension", {})
                modbus_reg = ext.get("modbusRegister")
                if item_id is not None and modbus_reg is not None:
                    # Cloud modbusRegister is 0-indexed; const.py registers
                    # are 1-indexed.  Store with +1 so lookups by
                    # param.register (1-indexed) work directly.
                    self._modbus_to_data_item[modbus_reg + 1] = item_id
                    self._data_item_cache[item_id] = item

            # Inject sensor INPUT register mappings that are NOT in
            # ExportDataItems but ARE accessible via GetDataItems.
            # These were discovered by exhaustive scan of data item IDs.
            from .const import CLOUD_SENSOR_DATA_ITEMS, CLOUD_CONTROL_DATA_ITEMS

            injected_sensors = 0
            for modbus_reg_1indexed, data_item_id in CLOUD_SENSOR_DATA_ITEMS.items():
                if modbus_reg_1indexed not in self._modbus_to_data_item:
                    self._modbus_to_data_item[modbus_reg_1indexed] = data_item_id
                    injected_sensors += 1

            # Inject HOLDING register mappings for control operations
            injected_controls = 0
            for modbus_reg_1indexed, data_item_id in CLOUD_CONTROL_DATA_ITEMS.items():
                if modbus_reg_1indexed not in self._modbus_to_data_item:
                    self._modbus_to_data_item[modbus_reg_1indexed] = data_item_id
                    injected_controls += 1

            self._mapping_initialized = True
            _LOGGER.debug(
                "Data item mapping initialized: %d export items, %d modbus mappings "
                "(%d injected sensor mappings, %d injected control mappings)",
                len(self._data_item_cache),
                len(self._modbus_to_data_item),
                injected_sensors,
                injected_controls,
            )

    def _get_data_item_id(self, modbus_register: int) -> int | None:
        """Get the data item ID for a Modbus register number.

        Returns None if the register is not in the mapping (e.g.,
        read-only sensor registers that aren't in ExportDataItems).
        """
        return self._modbus_to_data_item.get(modbus_register)

    # ------------------------------------------------------------------
    # Device status (quick overview)
    # ------------------------------------------------------------------

    async def get_device_status(self) -> dict[str, Any]:
        """Get device status via GetDeviceStatus.

        Tries the enhanced query first (with humidity, co2, userMode).
        Falls back to basic query if the schema doesn't support those fields.

        Returns a dict with: id, connectivity, activeAlarms, temperature,
        airflow, filterExpiration, serialNumber, model, and optionally
        humidity, co2, userMode.
        """
        query = (
            GET_DEVICE_STATUS_QUERY_BASIC
            if self._use_basic_status_query
            else GET_DEVICE_STATUS_QUERY
        )

        data = await self._remote_request(query)

        # If enhanced query fails with schema error, fall back to basic
        if data.get("errors") and not self._use_basic_status_query:
            error_msg = data["errors"][0].get("message", "")
            if "Cannot query field" in error_msg or "Unknown field" in error_msg:
                _LOGGER.debug(
                    "Enhanced GetDeviceStatus not supported, "
                    "falling back to basic query"
                )
                self._use_basic_status_query = True
                data = await self._remote_request(GET_DEVICE_STATUS_QUERY_BASIC)

        if data.get("errors"):
            raise CloudAPIError(
                "GetDeviceStatus failed: "
                f"{data['errors'][0].get('message', 'Unknown')}"
            )

        status = data.get("data", {}).get("GetDeviceStatus")
        if not status:
            raise CloudAPIError("No GetDeviceStatus in response")

        return status

    # ------------------------------------------------------------------
    # Read operations (compatible with Modbus/SaveConnect interface)
    # ------------------------------------------------------------------

    async def read_params(
        self, params: list[Any]
    ) -> dict[str, Any]:
        """Read register values from the cloud API.

        This provides the same interface as ModbusAPI.read_params() and
        SaveConnectAPI.read_params(). It translates Modbus register numbers
        to cloud data item IDs, fetches them via GetDataItems, and returns
        values keyed by the parameter's short name.

        Args:
            params: List of ModbusParam objects to read.

        Returns:
            Dict mapping param.short -> scaled value.
        """
        await self._ensure_mapping()

        # Collect data item IDs for the requested registers
        ids_to_fetch: list[int] = []
        # Multiple params may map to the same data_item_id, so use a list
        params_by_data_item: dict[int, list[Any]] = {}

        for param in params:
            data_item_id = self._get_data_item_id(param.register)
            if data_item_id is not None:
                if data_item_id not in params_by_data_item:
                    ids_to_fetch.append(data_item_id)
                    params_by_data_item[data_item_id] = []
                params_by_data_item[data_item_id].append(param)

        if not ids_to_fetch:
            _LOGGER.debug(
                "No cloud data item IDs found for requested registers"
            )
            return {}

        # Fetch via GetDataItems
        data = await self._remote_request(
            GET_DATA_ITEMS_QUERY,
            variables={"input": ids_to_fetch},
        )

        if data.get("errors"):
            raise CloudAPIError(
                "GetDataItems failed: "
                f"{data['errors'][0].get('message', 'Unknown')}"
            )

        items = data.get("data", {}).get("GetDataItems")
        if items is None:
            return {}

        # GetDataItems returns SerializedDataItemOutputType (scalar)
        # which may be a JSON string or already a list
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except (json.JSONDecodeError, TypeError):
                _LOGGER.warning("Could not parse GetDataItems response")
                return {}

        if not isinstance(items, list):
            return {}

        # Parse results
        result: dict[str, Any] = {}
        for item in items:
            item_id = item.get("id")
            value = item.get("value")
            if item_id is None or value is None:
                continue

            matched_params = params_by_data_item.get(item_id)
            if not matched_params:
                continue

            # Apply the value to all params that share this data_item_id
            for param in matched_params:
                # Convert value based on parameter type
                try:
                    if param.is_boolean:
                        if isinstance(value, bool):
                            result[param.short] = value
                        elif isinstance(value, (int, float)):
                            result[param.short] = bool(value)
                        elif isinstance(value, str):
                            result[param.short] = value.lower() in (
                                "true", "1", "on"
                            )
                        else:
                            result[param.short] = bool(value)
                    elif param.scale_factor != 1:
                        # Cloud returns raw register values (same as Modbus)
                        raw = float(value) if not isinstance(value, (int, float)) else value
                        result[param.short] = raw / param.scale_factor
                    else:
                        if isinstance(value, (int, float)):
                            result[param.short] = value
                        elif isinstance(value, str) and value.lstrip("-").isdigit():
                            result[param.short] = int(value)
                        elif isinstance(value, bool):
                            result[param.short] = int(value)
                        else:
                            result[param.short] = value
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Error converting value for %s (id=%d): %s",
                        param.short, item_id, err,
                    )

        return result

    async def read_data_items(
        self, data_item_ids: list[int]
    ) -> list[dict[str, Any]]:
        """Read specific data items by their IDs.

        Lower-level method that returns raw data item objects.

        Args:
            data_item_ids: List of data item IDs to fetch.

        Returns:
            List of data item dicts from the API.
        """
        data = await self._remote_request(
            GET_DATA_ITEMS_QUERY,
            variables={"input": data_item_ids},
        )

        if data.get("errors"):
            raise CloudAPIError(
                "GetDataItems failed: "
                f"{data['errors'][0].get('message', 'Unknown')}"
            )

        items = data.get("data", {}).get("GetDataItems")
        if items is None:
            return []

        if isinstance(items, str):
            try:
                items = json.loads(items)
            except (json.JSONDecodeError, TypeError):
                return []

        return items if isinstance(items, list) else []

    # ------------------------------------------------------------------
    # Write operations (compatible with Modbus/SaveConnect interface)
    # ------------------------------------------------------------------

    @staticmethod
    def _scale_value(param: Any, value: Any) -> str:
        """Scale and convert a value for writing via the cloud API.

        Args:
            param: ModbusParam with is_boolean, scale_factor attributes.
            value: The raw value to convert.

        Returns:
            String representation suitable for WriteDataItems.
        """
        if param.is_boolean:
            return "true" if value else "false"
        if param.scale_factor != 1:
            return str(int(float(value) * param.scale_factor))
        try:
            return str(int(value))
        except (ValueError, TypeError):
            return str(value)

    async def write_param(self, param: Any, value: Any) -> None:
        """Write a single register value via the cloud API.

        This provides the same interface as ModbusAPI.write_param() and
        SaveConnectAPI.write_param().

        Args:
            param: ModbusParam object defining the register.
            value: The value to write (will be scaled and converted).

        Raises:
            CloudAPIError: On failure.
        """
        await self._ensure_mapping()

        data_item_id = self._get_data_item_id(param.register)
        if data_item_id is None:
            raise CloudAPIError(
                f"No cloud data item ID found for register {param.register} "
                f"({param.short})"
            )

        raw_value = self._scale_value(param, value)

        await self._write_data_items([
            {"id": data_item_id, "value": raw_value}
        ])

    async def write_params(
        self, params: list[Any], values: list[Any]
    ) -> None:
        """Write multiple register values in a single request.

        Args:
            params: List of ModbusParam objects.
            values: List of values (same order as params).

        Raises:
            CloudAPIError: On failure.
        """
        await self._ensure_mapping()

        data_points: list[dict[str, Any]] = []
        for param, value in zip(params, values):
            data_item_id = self._get_data_item_id(param.register)
            if data_item_id is None:
                _LOGGER.warning(
                    "No cloud data item ID for register %d (%s), skipping",
                    param.register, param.short,
                )
                continue

            raw_value = self._scale_value(param, value)
            data_points.append({"id": data_item_id, "value": raw_value})

        if data_points:
            await self._write_data_items(data_points)

    async def _write_data_items(
        self, data_points: list[dict[str, Any]]
    ) -> None:
        """Write data items via the WriteDataItems mutation.

        Args:
            data_points: List of {id: int, value: str} dicts.

        Raises:
            CloudAPIError: If write fails after retries.
        """
        import asyncio

        variables = {
            "input": {
                "dataPoints": data_points,
            }
        }

        # Retry logic for SERVER_BUSY errors (common with Systemair cloud)
        max_retries = 3
        retry_delay = 0.5  # Start with 500ms

        for attempt in range(max_retries):
            data = await self._remote_request(
                WRITE_DATA_ITEMS_MUTATION,
                variables=variables,
            )

            if data.get("errors"):
                error_msg = data['errors'][0].get('message', 'Unknown')
                
                # Retry on SERVER_BUSY errors
                if "SERVER_BUSY" in error_msg and attempt < max_retries - 1:
                    _LOGGER.debug(
                        "Write failed with SERVER_BUSY (attempt %d/%d), retrying in %.1fs...",
                        attempt + 1, max_retries, retry_delay
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                
                # Non-retryable error or max retries exceeded
                raise CloudAPIError(f"WriteDataItems failed: {error_msg}")

            # Success
            _LOGGER.debug(
                "Cloud write successful: %d data points", len(data_points)
            )
            return

        # Should not reach here, but just in case
        raise CloudAPIError("WriteDataItems failed after max retries")

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------

    async def get_active_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms from the device.

        Returns:
            List of alarm dicts with title, description, timestamp, etc.
        """
        data = await self._remote_request(GET_ACTIVE_ALARMS_QUERY)

        if data.get("errors"):
            raise CloudAPIError(
                "GetActiveAlarms failed: "
                f"{data['errors'][0].get('message', 'Unknown')}"
            )

        result = data.get("data", {}).get("GetActiveAlarms", {})
        return result.get("alarms", [])

    async def get_filter_information(self) -> dict[str, Any]:
        """Get filter information from the device.

        Returns:
            Dict with selectedFilter and itemNumber.
        """
        data = await self._remote_request(GET_FILTER_INFO_QUERY)

        if data.get("errors"):
            raise CloudAPIError(
                "GetFilterInformation failed: "
                f"{data['errors'][0].get('message', 'Unknown')}"
            )

        result = data.get("data", {}).get("GetFilterInformation")
        if result is None:
            raise CloudAPIError("No GetFilterInformation in response")

        return result

    # ------------------------------------------------------------------
    # Diagnostics data collection
    # ------------------------------------------------------------------

    async def collect_diagnostics_data(self) -> dict[str, Any]:
        """Collect comprehensive raw data from the cloud for diagnostics.

        Calls all available GraphQL queries and returns their raw responses.
        Each query is independent — partial failures are captured as error
        strings rather than aborting the entire collection.

        This is intended for diagnostics download so developers can
        implement support for other Systemair device types/models.

        Returns:
            Dict with keys for each data source. Each value is either
            the raw response data or an error string.
        """
        result: dict[str, Any] = {
            "device_id": self._device_id,
            "device_name": self._device_name,
            "device_type": self._device_type,
        }

        # 1. GetAccountDevices (raw gateway response)
        try:
            gw_data = await self._gateway_request(GET_ACCOUNT_DEVICES_QUERY)
            result["account_devices"] = gw_data.get("data", {}).get(
                "GetAccountDevices"
            )
        except Exception as err:
            result["account_devices"] = f"Error: {err}"

        # 2. ExportDataItems (full mapping dump)
        export_data_items: list[dict[str, Any]] | None = None
        try:
            data = await self._remote_request(EXPORT_DATA_ITEMS_QUERY)
            export = data.get("data", {}).get("ExportDataItems")
            if export:
                items = export.get("dataItems")
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except (json.JSONDecodeError, TypeError):
                        pass
                result["export_data_items"] = {
                    "version": export.get("version"),
                    "type": export.get("type"),
                    "data_item_count": len(items) if isinstance(items, list) else None,
                    "data_items": items,
                }
                if isinstance(items, list):
                    export_data_items = items
            else:
                result["export_data_items"] = "Error: No ExportDataItems in response"
        except Exception as err:
            result["export_data_items"] = f"Error: {err}"

        # 3. GetDeviceStatus (raw)
        try:
            status_data = await self._remote_request(GET_DEVICE_STATUS_QUERY)
            if status_data.get("errors"):
                # Try basic fallback
                status_data = await self._remote_request(
                    GET_DEVICE_STATUS_QUERY_BASIC
                )
            result["device_status"] = status_data.get("data", {}).get(
                "GetDeviceStatus"
            )
        except Exception as err:
            result["device_status"] = f"Error: {err}"

        # 4. GetActiveAlarms (raw)
        try:
            alarms_data = await self._remote_request(GET_ACTIVE_ALARMS_QUERY)
            result["active_alarms"] = (
                alarms_data.get("data", {})
                .get("GetActiveAlarms", {})
                .get("alarms", [])
            )
        except Exception as err:
            result["active_alarms"] = f"Error: {err}"

        # 5. GetFilterInformation (raw)
        try:
            filter_data = await self._remote_request(GET_FILTER_INFO_QUERY)
            result["filter_information"] = filter_data.get("data", {}).get(
                "GetFilterInformation"
            )
        except Exception as err:
            result["filter_information"] = f"Error: {err}"

        # 6. Read ALL data item values from ExportDataItems
        if export_data_items:
            all_ids = [
                item["id"]
                for item in export_data_items
                if isinstance(item.get("id"), int)
            ]
            if all_ids:
                try:
                    # Read in batches to avoid oversized requests
                    batch_size = 100
                    all_values: list[dict[str, Any]] = []
                    for i in range(0, len(all_ids), batch_size):
                        batch = all_ids[i : i + batch_size]
                        batch_result = await self.read_data_items(batch)
                        all_values.extend(batch_result)
                    result["all_data_item_values"] = {
                        "requested_count": len(all_ids),
                        "received_count": len(all_values),
                        "items": all_values,
                    }
                except Exception as err:
                    result["all_data_item_values"] = f"Error: {err}"
            else:
                result["all_data_item_values"] = "No valid IDs found"
        else:
            result["all_data_item_values"] = "Skipped (ExportDataItems failed)"

        # 7. Read CLOUD_SENSOR_DATA_ITEMS (INPUT register items)
        try:
            from .const import CLOUD_SENSOR_DATA_ITEMS

            sensor_ids = list(CLOUD_SENSOR_DATA_ITEMS.values())
            if sensor_ids:
                sensor_values = await self.read_data_items(sensor_ids)
                result["sensor_data_item_values"] = {
                    "mapping": {
                        str(reg): did
                        for reg, did in CLOUD_SENSOR_DATA_ITEMS.items()
                    },
                    "requested_count": len(sensor_ids),
                    "received_count": len(sensor_values),
                    "items": sensor_values,
                }
            else:
                result["sensor_data_item_values"] = "No sensor data items defined"
        except Exception as err:
            result["sensor_data_item_values"] = f"Error: {err}"

        return result

    # ------------------------------------------------------------------
    # WebSocket (push events)
    # ------------------------------------------------------------------

    async def broadcast_device_statuses(self) -> None:
        """Trigger devices to send status updates via WebSocket.

        Call this after connecting to the WebSocket to receive
        DEVICE_STATUS_UPDATE events.
        """
        device_ids = [self._device_id] if self._device_id else []
        await self._gateway_request(
            BROADCAST_DEVICE_STATUSES_QUERY,
            variables={"deviceIds": device_ids},
        )

    async def connect_websocket(
        self,
        callback: Any = None,
    ) -> aiohttp.ClientWebSocketResponse | None:
        """Connect to the WebSocket for push events.

        The WebSocket uses subprotocol-based authentication:
        protocols=("accessToken", <token>)

        Args:
            callback: Optional async callback(message_data: dict) for
                incoming messages.

        Returns:
            The WebSocket connection, or None on failure.
        """
        await self._ensure_token()
        session = self._get_session()

        try:
            ws = await session.ws_connect(
                self._ws_url,
                protocols=[
                    "accessToken",
                    self._access_token,
                ],
                timeout=aiohttp.ClientTimeout(total=30),
            )
            _LOGGER.debug("WebSocket connected to %s", self._ws_url)

            # Trigger status broadcast (best-effort; WS still works without it)
            try:
                await self.broadcast_device_statuses()
            except (CloudAPIError, Exception) as bcast_err:
                _LOGGER.warning(
                    "BroadcastDeviceStatuses failed (WS still active): %s",
                    bcast_err,
                )

            if callback:
                self._ws_listener_task = asyncio.create_task(
                    self._ws_listener(ws, callback)
                )

            return ws

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("WebSocket connection failed: %s", err)
            return None

    async def _ws_listener(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        callback: Any,
    ) -> None:
        """Listen for WebSocket messages and dispatch to callback."""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await callback(data)
                    except (json.JSONDecodeError, TypeError) as err:
                        _LOGGER.warning("WS message parse error: %s", err)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.debug("WebSocket closed/error: %s", msg.type)
                    break
        except asyncio.CancelledError:
            _LOGGER.debug("WebSocket listener cancelled")
        except Exception:
            _LOGGER.exception("WebSocket listener error")
        finally:
            if not ws.closed:
                await ws.close()

    # ------------------------------------------------------------------
    # Convenience: backward-compatible write() method
    # ------------------------------------------------------------------

    async def write(self, values: dict[str, Any]) -> None:
        """Write parameter values using cloud-style key-value pairs.

        This is a backward-compatible convenience wrapper. It maps
        known cloud parameter names to Modbus register numbers, then
        writes via the data item ID mapping.

        Args:
            values: Dict mapping parameter name to value.
        """
        await self._ensure_mapping()

        data_points: list[dict[str, Any]] = []
        for param_name, val in values.items():
            reg_info = _CLOUD_PARAM_TO_REGISTER.get(param_name)
            if reg_info:
                modbus_reg, scale = reg_info
                data_item_id = self._get_data_item_id(modbus_reg)
                if data_item_id is not None:
                    raw_val = int(float(val) * scale)
                    data_points.append({
                        "id": data_item_id,
                        "value": str(raw_val),
                    })
                else:
                    _LOGGER.warning(
                        "No data item ID for register %d (%s)",
                        modbus_reg, param_name,
                    )
            else:
                _LOGGER.warning(
                    "Unknown cloud write parameter: %s", param_name
                )

        if data_points:
            await self._write_data_items(data_points)

    # ------------------------------------------------------------------
    # Connection testing
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Test if we can authenticate and list devices.

        Returns:
            True if login and device listing succeed.
        """
        try:
            await self.login()
            devices = await self.get_devices()
            return len(devices) > 0
        except CloudAPIError:
            return False


# Cloud parameter name -> (modbus_register, scale_factor) mapping
# Used by the backward-compatible write() method
_CLOUD_PARAM_TO_REGISTER: dict[str, tuple[int, float]] = {
    "main_temperature_offset": (2001, 1.0),  # REG_TC_SP, already x10
    "main_airflow": (1131, 1.0),  # REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF
    "eco_mode": (2505, 1.0),  # REG_ECO_MODE_ON_OFF
    "mode_change_request": (1162, 1.0),  # REG_USERMODE_HMI_CHANGE_REQUEST
    "user_mode_away_duration": (1102, 1.0),
    "user_mode_crowded_duration": (1105, 1.0),
    "user_mode_fireplace_duration": (1103, 1.0),
    "user_mode_holiday_duration": (1101, 1.0),
    "user_mode_refresh_duration": (1104, 1.0),
}
