"""Tests for the Cloud API client (Keycloak OIDC + GraphQL)."""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.cloud_api import (
    AuthenticationError,
    CloudAPIError,
    SystemairCloudAPI,
    DEFAULT_GATEWAY_API_URL,
    DEFAULT_REMOTE_API_URL,
    DEFAULT_AUTH_URL,
    DEFAULT_TOKEN_URL,
    DEFAULT_WS_URL,
    _CLOUD_PARAM_TO_REGISTER,
)


# ---------------------------------------------------------------------------
# Mock aiohttp helpers
# ---------------------------------------------------------------------------


class MockResponse:
    """Minimal mock for aiohttp ClientResponse."""

    def __init__(
        self,
        status: int = 200,
        json_data=None,
        text_data: str | None = None,
        headers: dict | None = None,
        url: str | None = None,
    ):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {}
        self.url = _FakeURL(url) if url else _FakeURL("")

    async def json(self):
        return self._json_data

    async def text(self):
        if self._text_data is not None:
            return self._text_data
        return json.dumps(self._json_data) if self._json_data else ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeURL:
    """Minimal stand-in for yarl.URL so str(resp.url) works in tests."""

    def __init__(self, url: str):
        self._url = url

    def __str__(self) -> str:
        return self._url


# The Keycloak login form HTML returned by the auth endpoint
KEYCLOAK_LOGIN_HTML = """
<html>
<body>
<form id="kc-form-login" action="https://sso.systemair.com/auth/realms/iot/login-actions/authenticate?session_code=abc123&amp;execution=def456" method="post">
  <input name="username" type="text"/>
  <input name="password" type="password"/>
  <input type="submit" value="Sign In"/>
</form>
</body>
</html>
"""

REDIRECT_WITH_CODE = "https://homesolutions.systemair.com?code=auth_code_xyz"
REDIRECT_WITH_ERROR = "https://homesolutions.systemair.com?error=access_denied&error_description=Account+disabled"

TOKEN_RESPONSE = {
    "access_token": "oidc_access_token_123",
    "refresh_token": "oidc_refresh_token_456",
    "expires_in": 300,
    "token_type": "Bearer",
}

REFRESHED_TOKEN_RESPONSE = {
    "access_token": "refreshed_access_token_789",
    "refresh_token": "refreshed_refresh_token_012",
    "expires_in": 300,
    "token_type": "Bearer",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSystemairCloudAPIInit:
    """Tests for initialization and properties."""

    def test_init_defaults(self):
        api = SystemairCloudAPI("user@example.com", "password123")
        assert api._email == "user@example.com"
        assert api._password == "password123"
        assert api._access_token is None
        assert api._refresh_token is None
        assert api._device_id is None
        assert api._device_name is None
        assert api._gateway_api_url == DEFAULT_GATEWAY_API_URL
        assert api._auth_url == DEFAULT_AUTH_URL
        assert api._token_url == DEFAULT_TOKEN_URL
        assert api._ws_url == DEFAULT_WS_URL
        assert api._owns_session is True

    def test_init_with_session(self):
        session = MagicMock()
        api = SystemairCloudAPI("a@b.com", "pw", session=session)
        assert api._session is session
        assert api._owns_session is False

    def test_init_custom_urls(self):
        api = SystemairCloudAPI(
            "a@b.com", "pw",
            api_url="http://local/gateway/api",
            ws_url="ws://local/ws",
            auth_url="http://local/auth",
            token_url="http://local/token",
        )
        assert api._gateway_api_url == "http://local/gateway/api"
        assert api._remote_api_url == "http://local/gateway/remote-api"
        assert api._ws_url == "ws://local/ws"
        assert api._auth_url == "http://local/auth"
        assert api._token_url == "http://local/token"

    def test_init_custom_api_url_derives_remote_api(self):
        """Non-standard URL gets /remote-api appended."""
        api = SystemairCloudAPI(
            "a@b.com", "pw",
            api_url="http://custom-host/api",
        )
        assert api._remote_api_url == "http://custom-host/api/remote-api"

    def test_set_machine(self):
        api = SystemairCloudAPI("a@b.com", "pw")
        api.set_machine("device_1", "My Unit", device_type="LEGACY")
        assert api.device_id == "device_1"
        assert api.device_name == "My Unit"
        assert api.machine_id == "device_1"  # backward-compat alias
        assert api.machine_name == "My Unit"  # backward-compat alias
        assert api._device_type == "LEGACY"

    def test_set_machine_resets_mapping(self):
        api = SystemairCloudAPI("a@b.com", "pw")
        api._mapping_initialized = True
        api._modbus_to_data_item = {2001: 32}
        api.set_machine("new_device", "New")
        assert api._mapping_initialized is False
        assert api._modbus_to_data_item == {}


class TestSystemairCloudAPILogin:
    """Tests for the OIDC login flow."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        return SystemairCloudAPI("user@example.com", "password123", session=mock_session)

    @pytest.mark.asyncio
    async def test_login_success(self, api, mock_session):
        """Test full 3-step OIDC login flow."""
        # Step 1: GET auth page returns HTML with form
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        # Step 2: POST credentials follows redirects to redirect_uri?code=...
        form_response = MockResponse(200, url=REDIRECT_WITH_CODE)
        # Step 3: POST token exchange returns tokens
        token_response = MockResponse(200, json_data=TOKEN_RESPONSE)

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(side_effect=[form_response, token_response])

        token = await api.login()
        assert token == "oidc_access_token_123"
        assert api._access_token == "oidc_access_token_123"
        assert api._refresh_token == "oidc_refresh_token_456"
        assert api._consecutive_login_failures == 0

    @pytest.mark.asyncio
    async def test_login_auth_page_failure(self, api, mock_session):
        """Test login when Keycloak auth page returns HTTP error."""
        mock_session.get = MagicMock(return_value=MockResponse(503))

        with pytest.raises(CloudAPIError, match="Failed to get login page: HTTP 503"):
            await api.login()
        assert api._consecutive_login_failures == 1

    @pytest.mark.asyncio
    async def test_login_no_form_action(self, api, mock_session):
        """Test login when auth page has no form action."""
        mock_session.get = MagicMock(
            return_value=MockResponse(200, text_data="<html><body>No form here</body></html>", url="https://sso.systemair.com/auth/page")
        )

        with pytest.raises(CloudAPIError, match="Could not find login form"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_bad_credentials(self, api, mock_session):
        """Test login with wrong password (final URL stays on Keycloak SSO)."""
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        # Bad creds: follow_redirects=True but final URL stays on sso.systemair.com
        form_response = MockResponse(200, url="https://sso.systemair.com/auth/realms/iot/login-actions/authenticate?session_code=abc")

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(return_value=form_response)

        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            await api.login()
        assert api._consecutive_login_failures == 1

    @pytest.mark.asyncio
    async def test_login_redirect_with_error(self, api, mock_session):
        """Test login when redirect contains an error."""
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_response = MockResponse(200, url=REDIRECT_WITH_ERROR)

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(return_value=form_response)

        with pytest.raises(AuthenticationError, match="access_denied"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_redirect_no_code(self, api, mock_session):
        """Test login when redirect has no code and no error."""
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_response = MockResponse(200, url="https://homesolutions.systemair.com")

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(return_value=form_response)

        with pytest.raises(CloudAPIError, match="No authorization code"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_token_exchange_failure(self, api, mock_session):
        """Test login when token exchange fails."""
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_response = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_response = MockResponse(400)

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(side_effect=[form_response, token_response])

        with pytest.raises(CloudAPIError, match="Token exchange failed"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_no_access_token_in_response(self, api, mock_session):
        """Test login when token response has no access_token."""
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_response = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_response = MockResponse(200, json_data={"token_type": "Bearer"})

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(side_effect=[form_response, token_response])

        with pytest.raises(CloudAPIError, match="No access_token"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_form_post_network_error(self, api, mock_session):
        """Test login when form POST results in a network/connection error."""
        import aiohttp as _aiohttp
        auth_response = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(side_effect=_aiohttp.ClientError("Connection refused"))

        with pytest.raises(CloudAPIError, match="Login request failed"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_amp_entity_in_form_action(self, api, mock_session):
        """Test that &amp; in form action URL is properly decoded."""
        html = '<form action="http://example.com/login?a=1&amp;b=2" method="post"></form>'
        auth_response = MockResponse(200, text_data=html, url="https://sso.systemair.com/auth/page")
        form_response = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_response = MockResponse(200, json_data=TOKEN_RESPONSE)

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(side_effect=[form_response, token_response])

        await api.login()

        # Verify the form POST was made to the correct URL (decoded &amp; -> &)
        form_post_call = mock_session.post.call_args_list[0]
        assert "a=1&b=2" in form_post_call[0][0]

    @pytest.mark.asyncio
    async def test_login_already_authenticated(self, api, mock_session):
        """Test login when Keycloak redirects with code (session cookie valid).

        When a valid Keycloak session cookie exists, the initial GET to the
        auth endpoint auto-redirects to the redirect_uri with a code parameter.
        The login method should skip the form POST and go directly to token
        exchange.
        """
        # Step 1: GET auth page auto-redirects to redirect_uri?code=...
        already_auth_url = (
            "https://homesolutions.systemair.com"
            "?session_state=abc-123"
            "&iss=https://sso.systemair.com/auth/realms/iot"
            "&code=auto_code_from_session"
        )
        auth_response = MockResponse(
            200,
            text_data="<html><body>Redirected content</body></html>",
            url=already_auth_url,
        )
        # Only ONE POST: token exchange (no form POST needed)
        token_response = MockResponse(200, json_data=TOKEN_RESPONSE)

        mock_session.get = MagicMock(return_value=auth_response)
        mock_session.post = MagicMock(return_value=token_response)

        token = await api.login()

        assert token == "oidc_access_token_123"
        assert api._access_token == "oidc_access_token_123"
        assert api._consecutive_login_failures == 0

        # Verify only one POST was made (token exchange, no form POST)
        assert mock_session.post.call_count == 1
        # The token exchange POST should contain the auto code
        token_call = mock_session.post.call_args_list[0]
        assert token_call[1]["data"]["code"] == "auto_code_from_session"
        assert token_call[1]["data"]["grant_type"] == "authorization_code"


class TestSystemairCloudAPITokenRefresh:
    """Tests for token refresh logic."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "old_token"
        api._refresh_token = "old_refresh"
        api._token_expiry = 0  # expired
        return api

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, api, mock_session):
        """Test successful token refresh."""
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=REFRESHED_TOKEN_RESPONSE)
        )

        await api._refresh_access_token()
        assert api._access_token == "refreshed_access_token_789"
        assert api._refresh_token == "refreshed_refresh_token_012"

    @pytest.mark.asyncio
    async def test_refresh_token_falls_back_to_login(self, api, mock_session):
        """Test that refresh falls back to full login on failure."""
        # First call: refresh fails (400)
        # Then login calls: GET auth, POST form (follow redirects), POST token
        refresh_fail = MockResponse(400)
        auth_page = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_redirect = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_ok = MockResponse(200, json_data=TOKEN_RESPONSE)

        mock_session.post = MagicMock(
            side_effect=[refresh_fail, form_redirect, token_ok]
        )
        mock_session.get = MagicMock(return_value=auth_page)

        await api._refresh_access_token()
        assert api._access_token == "oidc_access_token_123"

    @pytest.mark.asyncio
    async def test_refresh_no_refresh_token_does_full_login(self, api, mock_session):
        """Test that missing refresh_token triggers full login."""
        api._refresh_token = None

        auth_page = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_redirect = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_ok = MockResponse(200, json_data=TOKEN_RESPONSE)

        mock_session.get = MagicMock(return_value=auth_page)
        mock_session.post = MagicMock(side_effect=[form_redirect, token_ok])

        await api._refresh_access_token()
        assert api._access_token == "oidc_access_token_123"

    @pytest.mark.asyncio
    async def test_ensure_token_skips_when_valid(self, api, mock_session):
        """Test that _ensure_token does nothing when token is still valid."""
        api._token_expiry = time.time() + 600  # far future

        mock_session.post = MagicMock()
        mock_session.get = MagicMock()

        await api._ensure_token()
        mock_session.post.assert_not_called()
        mock_session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_token_backoff(self, api, mock_session):
        """Test that _ensure_token enforces backoff after failures."""
        api._access_token = None
        api._refresh_token = None
        api._consecutive_login_failures = 5
        api._last_login_attempt = time.time()  # just now

        with pytest.raises(CloudAPIError, match="Login backoff"):
            await api._ensure_token()

    @pytest.mark.asyncio
    async def test_ensure_token_double_check_after_lock(self, api, mock_session):
        """After acquiring lock, re-check token validity (another coroutine may have refreshed)."""
        import asyncio

        # Start with expired token
        api._access_token = None
        api._refresh_token = None

        calls = []

        async def _fake_login():
            """Simulate login that takes time and sets the token."""
            calls.append("login")
            api._access_token = "fresh_token"
            api._token_expiry = time.time() + 600

        api.login = _fake_login

        # Call _ensure_token twice concurrently
        await asyncio.gather(
            api._ensure_token(),
            api._ensure_token(),
        )

        # Only one login call should have been made: the second coroutine
        # should see the freshly-set token after acquiring the lock
        assert len(calls) == 1
        assert api._access_token == "fresh_token"

    @pytest.mark.asyncio
    async def test_ensure_token_uses_refresh_when_available(self, api, mock_session):
        """_ensure_token should call _refresh_access_token when refresh_token is set."""
        api._access_token = None  # expired
        api._token_expiry = 0
        api._refresh_token = "valid_refresh"

        async def _fake_refresh():
            api._access_token = "refreshed_token"
            api._token_expiry = time.time() + 600

        api._refresh_access_token = _fake_refresh

        await api._ensure_token()
        assert api._access_token == "refreshed_token"

    @pytest.mark.asyncio
    async def test_ensure_token_falls_back_to_login(self, api, mock_session):
        """_ensure_token should call login when no refresh_token."""
        api._access_token = None
        api._token_expiry = 0
        api._refresh_token = None

        async def _fake_login():
            api._access_token = "login_token"
            api._token_expiry = time.time() + 600

        api.login = _fake_login

        await api._ensure_token()
        assert api._access_token == "login_token"

    @pytest.mark.asyncio
    async def test_ensure_token_serializes_concurrent_coroutines(self, api, mock_session):
        """Concurrent _ensure_token calls should be serialized by the lock."""
        import asyncio

        api._access_token = None
        api._refresh_token = None

        login_order: list[int] = []
        login_event = asyncio.Event()

        async def _slow_login():
            """Simulate slow login - first call blocks until released."""
            call_num = len(login_order) + 1
            login_order.append(call_num)
            if call_num == 1:
                # First caller sets token
                api._access_token = "token_from_first"
                api._token_expiry = time.time() + 600

        api.login = _slow_login

        await asyncio.gather(
            api._ensure_token(),
            api._ensure_token(),
            api._ensure_token(),
        )

        # Only one login should have happened; others see the token after lock
        assert len(login_order) == 1


class TestSystemairCloudAPIGraphQL:
    """Tests for GraphQL request handling."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._refresh_token = "valid_refresh_token"
        api._token_expiry = time.time() + 600
        return api

    @pytest.mark.asyncio
    async def test_graphql_request_success(self, api, mock_session):
        """Test a successful GraphQL request."""
        response_data = {"data": {"SomeQuery": {"result": "ok"}}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response_data)
        )

        result = await api._graphql_request(
            api._gateway_api_url, "{ SomeQuery { result } }"
        )
        assert result == response_data

    @pytest.mark.asyncio
    async def test_graphql_request_401_retries(self, api, mock_session):
        """Test that 401 triggers token refresh and retry."""
        response_data = {"data": {"SomeQuery": {"result": "ok"}}}

        # First call: 401, then refresh + retry succeeds
        first_call = MockResponse(401)
        # Refresh token call
        refresh_resp = MockResponse(200, json_data=REFRESHED_TOKEN_RESPONSE)
        # Retry call
        retry_call = MockResponse(200, json_data=response_data)

        mock_session.post = MagicMock(
            side_effect=[first_call, refresh_resp, retry_call]
        )

        result = await api._graphql_request(
            api._gateway_api_url, "{ SomeQuery { result } }"
        )
        assert result == response_data

    @pytest.mark.asyncio
    async def test_graphql_request_http_error(self, api, mock_session):
        """Test GraphQL request with non-200 response."""
        mock_session.post = MagicMock(
            return_value=MockResponse(500)
        )

        with pytest.raises(CloudAPIError, match="GraphQL request failed: HTTP 500"):
            await api._graphql_request(
                api._gateway_api_url, "{ SomeQuery { result } }"
            )

    @pytest.mark.asyncio
    async def test_graphql_request_with_extra_headers(self, api, mock_session):
        """Test that extra headers are passed through."""
        response_data = {"data": {"GetDeviceStatus": {"id": "test"}}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response_data)
        )

        await api._graphql_request(
            api._remote_api_url,
            "{ GetDeviceStatus { id } }",
            extra_headers={"device-id": "dev1", "device-type": "LEGACY"},
        )

        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["headers"]["device-id"] == "dev1"
        assert call_kwargs["headers"]["device-type"] == "LEGACY"


class TestSystemairCloudAPIDevices:
    """Tests for device-related operations."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        return api

    @pytest.mark.asyncio
    async def test_get_devices(self, api, mock_session):
        """Test getting device list via GetAccountDevices."""
        account_response = {
            "data": {
                "GetAccountDevices": [
                    {
                        "identifier": "device_001",
                        "name": "Unit 1",
                        "deviceType": {"type": "LEGACY"},
                        "status": {
                            "connectionStatus": "ONLINE",
                            "serialNumber": "SN001",
                            "model": "VTR300",
                            "hasAlarms": False,
                            "units": {"temperature": "C", "pressure": "Pa", "flow": "l/s"},
                        },
                    },
                    {
                        "identifier": "device_002",
                        "name": "Unit 2",
                        "deviceType": {"type": "LEGACY"},
                        "status": {
                            "connectionStatus": "OFFLINE",
                            "serialNumber": "",
                            "model": "0",
                            "hasAlarms": False,
                            "units": {"temperature": "C", "pressure": "Pa", "flow": "l/s"},
                        },
                    },
                ]
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=account_response)
        )

        devices = await api.get_devices()
        assert len(devices) == 2
        assert devices[0]["machine_id"] == "device_001"
        assert devices[0]["name"] == "Unit 1"
        assert devices[0]["connection_status"] == "ONLINE"
        assert devices[0]["device_type"] == "LEGACY"
        assert devices[0]["model"] == "VTR300"
        assert devices[0]["serial_number"] == "SN001"
        assert devices[1]["machine_id"] == "device_002"
        assert devices[1]["connection_status"] == "OFFLINE"

    @pytest.mark.asyncio
    async def test_get_devices_graphql_error(self, api, mock_session):
        """Test get_devices when GraphQL returns errors."""
        error_response = {
            "errors": [{"message": "Unauthorized"}],
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=error_response)
        )

        with pytest.raises(CloudAPIError, match="GetAccountDevices failed.*Unauthorized"):
            await api.get_devices()

    @pytest.mark.asyncio
    async def test_get_devices_no_device_data(self, api, mock_session):
        """Test get_devices when no device data returned."""
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data={"data": {}})
        )

        with pytest.raises(CloudAPIError, match="No device data"):
            await api.get_devices()

    @pytest.mark.asyncio
    async def test_get_devices_empty(self, api, mock_session):
        """Test get_devices with no devices."""
        account_response = {
            "data": {
                "GetAccountDevices": []
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=account_response)
        )

        devices = await api.get_devices()
        assert devices == []


class TestSystemairCloudAPIReadWrite:
    """Tests for read and write operations using the new register-based interface."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        api._device_id = "device_001"
        api._device_name = "Test Unit"
        api._device_type = "LEGACY"
        # Pre-populate the mapping so _ensure_mapping is a no-op
        api._mapping_initialized = True
        api._modbus_to_data_item = {
            2001: 32,   # REG_TC_SP
            2505: 34,   # REG_ECO_MODE_ON_OFF
            1131: 38,   # REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF
            1162: 40,   # REG_USERMODE_HMI_CHANGE_REQUEST
        }
        return api

    def _make_param(self, register, short, scale_factor=1, is_boolean=False, min_val=None, max_val=None):
        """Create a minimal ModbusParam-like object for testing."""
        p = MagicMock()
        p.register = register
        p.short = short
        p.scale_factor = scale_factor
        p.is_boolean = is_boolean
        p.min_val = min_val
        p.max_val = max_val
        return p

    @pytest.mark.asyncio
    async def test_read_params(self, api, mock_session):
        """Test read_params translates registers to data item IDs and reads values."""
        # GetDataItems returns a list of data item objects
        data_items_response = {
            "data": {
                "GetDataItems": [
                    {"id": 32, "value": 210},
                    {"id": 34, "value": True},
                ]
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=data_items_response)
        )

        param_temp = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        param_eco = self._make_param(2505, "REG_ECO_MODE_ON_OFF", is_boolean=True)

        result = await api.read_params([param_temp, param_eco])
        assert result["REG_TC_SP"] == 21.0  # 210 / 10
        assert result["REG_ECO_MODE_ON_OFF"] is True

    @pytest.mark.asyncio
    async def test_read_params_string_values(self, api, mock_session):
        """Test read_params handles string values from GetDataItems."""
        data_items_response = {
            "data": {
                "GetDataItems": [
                    {"id": 38, "value": "3"},
                ]
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=data_items_response)
        )

        param_fan = self._make_param(1131, "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF")
        result = await api.read_params([param_fan])
        assert result["REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF"] == 3

    @pytest.mark.asyncio
    async def test_read_params_json_string_response(self, api, mock_session):
        """Test read_params when GetDataItems returns a JSON string."""
        items = [{"id": 32, "value": 180}]
        data_items_response = {
            "data": {
                "GetDataItems": json.dumps(items)
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=data_items_response)
        )

        param_temp = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        result = await api.read_params([param_temp])
        assert result["REG_TC_SP"] == 18.0

    @pytest.mark.asyncio
    async def test_read_params_no_device_selected(self, api, mock_session):
        """Test read_params raises when no device is set."""
        api._device_id = None

        param = self._make_param(2001, "REG_TC_SP")
        with pytest.raises(CloudAPIError, match="No device selected"):
            await api.read_params([param])

    @pytest.mark.asyncio
    async def test_read_params_empty_result(self, api, mock_session):
        """Test read_params when GetDataItems returns None."""
        data_items_response = {
            "data": {
                "GetDataItems": None
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=data_items_response)
        )

        param = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        result = await api.read_params([param])
        assert result == {}

    @pytest.mark.asyncio
    async def test_read_params_unmapped_registers_skipped(self, api, mock_session):
        """Test read_params skips params with no data item ID mapping."""
        # Register 99999 is not in the mapping
        param_unknown = self._make_param(99999, "REG_UNKNOWN")
        result = await api.read_params([param_unknown])
        assert result == {}
        # No GraphQL call should have been made
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_param(self, api, mock_session):
        """Test write_param sends correct WriteDataItems mutation."""
        write_response = {
            "data": {
                "WriteDataItems": True
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        param = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        await api.write_param(param, 22.0)

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        assert "WriteDataItems" in payload["query"]
        variables = payload["variables"]
        data_points = variables["input"]["dataPoints"]
        assert len(data_points) == 1
        assert data_points[0]["id"] == 32  # data item ID for register 2001
        assert data_points[0]["value"] == "220"  # 22.0 * 10

    @pytest.mark.asyncio
    async def test_write_param_boolean(self, api, mock_session):
        """Test write_param with a boolean parameter."""
        write_response = {"data": {"WriteDataItems": True}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        param = self._make_param(2505, "REG_ECO_MODE_ON_OFF", is_boolean=True)
        await api.write_param(param, True)

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        data_points = payload["variables"]["input"]["dataPoints"]
        assert data_points[0]["id"] == 34
        assert data_points[0]["value"] == "true"

    @pytest.mark.asyncio
    async def test_write_param_no_device(self, api, mock_session):
        """Test write_param raises when no device is set."""
        api._device_id = None

        param = self._make_param(2001, "REG_TC_SP")
        with pytest.raises(CloudAPIError, match="No device selected"):
            await api.write_param(param, 22.0)

    @pytest.mark.asyncio
    async def test_write_param_unmapped_register(self, api, mock_session):
        """Test write_param raises when register has no data item mapping."""
        param = self._make_param(99999, "REG_UNKNOWN")
        with pytest.raises(CloudAPIError, match="No cloud data item ID found"):
            await api.write_param(param, 42)

    @pytest.mark.asyncio
    async def test_write_params_batch(self, api, mock_session):
        """Test write_params sends multiple data points in one request."""
        write_response = {"data": {"WriteDataItems": True}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        param1 = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        param2 = self._make_param(1131, "REG_USERMODE_MANUAL_AIRFLOW_LEVEL_SAF")
        await api.write_params([param1, param2], [22.0, 4])

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        data_points = payload["variables"]["input"]["dataPoints"]
        assert len(data_points) == 2
        # First: temp setpoint
        assert data_points[0]["id"] == 32
        assert data_points[0]["value"] == "220"
        # Second: fan level
        assert data_points[1]["id"] == 38
        assert data_points[1]["value"] == "4"

    @pytest.mark.asyncio
    async def test_write_params_skips_unmapped(self, api, mock_session):
        """Test write_params skips params without data item mapping."""
        write_response = {"data": {"WriteDataItems": True}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        param_known = self._make_param(2001, "REG_TC_SP", scale_factor=10)
        param_unknown = self._make_param(99999, "REG_UNKNOWN")
        await api.write_params([param_known, param_unknown], [22.0, 42])

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        data_points = payload["variables"]["input"]["dataPoints"]
        assert len(data_points) == 1
        assert data_points[0]["id"] == 32

    @pytest.mark.asyncio
    async def test_write_params_all_unmapped_no_call(self, api, mock_session):
        """Test write_params with all unmapped params makes no API call."""
        param = self._make_param(99999, "REG_UNKNOWN")
        await api.write_params([param], [42])
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_data_items_low_level(self, api, mock_session):
        """Test the low-level read_data_items method."""
        items = [{"id": 32, "value": 210}, {"id": 34, "value": "true"}]
        response = {"data": {"GetDataItems": items}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response)
        )

        result = await api.read_data_items([32, 34])
        assert len(result) == 2
        assert result[0]["id"] == 32

    @pytest.mark.asyncio
    async def test_get_device_status(self, api, mock_session):
        """Test get_device_status returns parsed status."""
        status_response = {
            "data": {
                "GetDeviceStatus": {
                    "id": "device_001",
                    "connectivity": "ONLINE",
                    "activeAlarms": 0,
                    "temperature": 21.5,
                    "airflow": 3,
                    "filterExpiration": "2026-06-15",
                    "serialNumber": "SN001",
                    "model": "VTR300",
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=status_response)
        )

        status = await api.get_device_status()
        assert status["id"] == "device_001"
        assert status["temperature"] == 21.5
        assert status["airflow"] == 3

    @pytest.mark.asyncio
    async def test_get_active_alarms(self, api, mock_session):
        """Test get_active_alarms returns alarm list."""
        alarm_response = {
            "data": {
                "GetActiveAlarms": {
                    "alarms": [
                        {"title": "Filter alarm", "description": "Replace filter", "timestamp": "2026-01-01", "stopping": False, "acknowledged": False},
                    ]
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=alarm_response)
        )

        alarms = await api.get_active_alarms()
        assert len(alarms) == 1
        assert alarms[0]["title"] == "Filter alarm"

    @pytest.mark.asyncio
    async def test_get_active_alarms_empty(self, api, mock_session):
        """Test get_active_alarms with no alarms."""
        alarm_response = {
            "data": {
                "GetActiveAlarms": {
                    "alarms": []
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=alarm_response)
        )

        alarms = await api.get_active_alarms()
        assert alarms == []


class TestSystemairCloudAPIEnsureMapping:
    """Tests for the ExportDataItems mapping initialization."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        api._device_id = "device_001"
        api._device_name = "Test Unit"
        api._device_type = "LEGACY"
        return api

    @pytest.mark.asyncio
    async def test_ensure_mapping_initializes(self, api, mock_session):
        """Test _ensure_mapping populates modbus-to-data-item mapping."""
        export_response = {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "config",
                    "dataItems": [
                        {
                            "id": 32,
                            "extension": {"modbusRegister": 2000},
                        },
                        {
                            "id": 34,
                            "extension": {"modbusRegister": 2504},
                        },
                        {
                            "id": 38,
                            "extension": {"modbusRegister": 1130},
                        },
                    ],
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=export_response)
        )

        await api._ensure_mapping()

        assert api._mapping_initialized is True
        # Keys are modbusRegister + 1 (0-indexed -> 1-indexed)
        assert api._modbus_to_data_item[2001] == 32
        assert api._modbus_to_data_item[2505] == 34
        assert api._modbus_to_data_item[1131] == 38

    @pytest.mark.asyncio
    async def test_ensure_mapping_json_string(self, api, mock_session):
        """Test _ensure_mapping when dataItems is a JSON string."""
        items = [
            {"id": 32, "extension": {"modbusRegister": 2000}},
        ]
        export_response = {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "config",
                    "dataItems": json.dumps(items),
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=export_response)
        )

        await api._ensure_mapping()
        assert api._modbus_to_data_item[2001] == 32

    @pytest.mark.asyncio
    async def test_ensure_mapping_skips_when_initialized(self, api, mock_session):
        """Test _ensure_mapping is a no-op when already initialized."""
        api._mapping_initialized = True
        await api._ensure_mapping()
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_mapping_error(self, api, mock_session):
        """Test _ensure_mapping raises on error response."""
        error_response = {
            "errors": [{"message": "Device offline"}],
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=error_response)
        )

        with pytest.raises(CloudAPIError, match="ExportDataItems failed"):
            await api._ensure_mapping()

    @pytest.mark.asyncio
    async def test_ensure_mapping_injects_sensor_data_items(self, api, mock_session):
        """Test _ensure_mapping injects CLOUD_SENSOR_DATA_ITEMS for INPUT registers."""
        from custom_components.systemair.const import CLOUD_SENSOR_DATA_ITEMS

        export_response = {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "config",
                    "dataItems": [
                        {"id": 32, "extension": {"modbusRegister": 2000}},
                    ],
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=export_response)
        )

        await api._ensure_mapping()

        # Verify export item is there
        assert api._modbus_to_data_item[2001] == 32

        # Verify all sensor data items are injected
        for modbus_reg, data_item_id in CLOUD_SENSOR_DATA_ITEMS.items():
            assert api._modbus_to_data_item[modbus_reg] == data_item_id, (
                f"Missing sensor mapping: register {modbus_reg} -> data item {data_item_id}"
            )

    @pytest.mark.asyncio
    async def test_ensure_mapping_does_not_overwrite_export_items(self, api, mock_session):
        """Sensor data items should not overwrite existing export mappings."""
        export_response = {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "config",
                    "dataItems": [
                        # Use a register that conflicts with CLOUD_SENSOR_DATA_ITEMS
                        # (12102 maps to data item 54 in CLOUD_SENSOR_DATA_ITEMS)
                        {"id": 999, "extension": {"modbusRegister": 12101}},
                    ],
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=export_response)
        )

        await api._ensure_mapping()

        # The export item (12101+1=12102) should keep its export-assigned ID, not be
        # overwritten by CLOUD_SENSOR_DATA_ITEMS[12102]=54
        assert api._modbus_to_data_item[12102] == 999


class TestSystemairCloudAPIWriteConvenience:
    """Tests for the backward-compatible write() convenience method."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        api._device_id = "device_001"
        api._device_name = "Test Unit"
        api._device_type = "LEGACY"
        # Pre-populate mapping
        api._mapping_initialized = True
        api._modbus_to_data_item = {
            2001: 32,
            2505: 34,
            1131: 38,
            1162: 40,
        }
        return api

    @pytest.mark.asyncio
    async def test_write_convenience_method(self, api, mock_session):
        """Test the convenience write() method maps params to registers."""
        write_response = {"data": {"WriteDataItems": True}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        await api.write({"main_temperature_offset": 220, "eco_mode": 1})

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        data_points = payload["variables"]["input"]["dataPoints"]
        assert len(data_points) == 2

        # Verify data item IDs and values
        dp_map = {dp["id"]: dp["value"] for dp in data_points}
        assert dp_map[32] == "220"  # main_temperature_offset -> data item 32
        assert dp_map[34] == "1"    # eco_mode -> data item 34 (legacy write() doesn't handle booleans)

    @pytest.mark.asyncio
    async def test_write_unknown_param_skipped(self, api, mock_session):
        """Test that unknown params are skipped (not written)."""
        write_response = {"data": {"WriteDataItems": True}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=write_response)
        )

        await api.write({"unknown_param": 42, "eco_mode": 1})

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        data_points = payload["variables"]["input"]["dataPoints"]
        assert len(data_points) == 1
        assert data_points[0]["id"] == 34

    @pytest.mark.asyncio
    async def test_write_all_unknown_params_no_call(self, api, mock_session):
        """Test that write() with all unknown params makes no API call."""
        await api.write({"totally_unknown": 42})
        mock_session.post.assert_not_called()


class TestSystemairCloudAPIClose:
    """Tests for connection cleanup."""

    @pytest.mark.asyncio
    async def test_close_external_session_not_closed(self):
        """Test that an external session is not closed."""
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        api = SystemairCloudAPI("a@b.com", "pw", session=session)

        await api.close()
        session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_owned_session(self):
        """Test that an owned session is closed."""
        api = SystemairCloudAPI("a@b.com", "pw")
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        api._session = mock_session
        api._owns_session = True

        await api.close()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_already_closed_session(self):
        """Test that close is safe when session is already closed."""
        api = SystemairCloudAPI("a@b.com", "pw")
        mock_session = MagicMock()
        mock_session.closed = True
        mock_session.close = AsyncMock()
        api._session = mock_session
        api._owns_session = True

        await api.close()
        mock_session.close.assert_not_called()


class TestSystemairCloudAPITestConnection:
    """Tests for test_connection."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        return SystemairCloudAPI("user@example.com", "password123", session=mock_session)

    @pytest.mark.asyncio
    async def test_connection_success(self, api, mock_session):
        """Test test_connection returns True on successful login + devices."""
        # Login: GET auth, POST form (follow redirects), POST token
        auth_page = MockResponse(200, text_data=KEYCLOAK_LOGIN_HTML, url="https://sso.systemair.com/auth/realms/iot/login")
        form_redirect = MockResponse(200, url=REDIRECT_WITH_CODE)
        token_ok = MockResponse(200, json_data=TOKEN_RESPONSE)

        # GetAccountDevices
        account_response = {
            "data": {
                "GetAccountDevices": [
                    {
                        "identifier": "d1",
                        "name": "Unit",
                        "deviceType": {"type": "LEGACY"},
                        "status": {
                            "connectionStatus": "ONLINE",
                            "serialNumber": "",
                            "model": "0",
                            "hasAlarms": False,
                            "units": {"temperature": "C", "pressure": "Pa", "flow": "l/s"},
                        },
                    },
                ]
            }
        }
        graphql_response = MockResponse(200, json_data=account_response)

        mock_session.get = MagicMock(return_value=auth_page)
        mock_session.post = MagicMock(
            side_effect=[form_redirect, token_ok, graphql_response]
        )

        result = await api.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_failure(self, api, mock_session):
        """Test test_connection returns False on login failure."""
        mock_session.get = MagicMock(return_value=MockResponse(503))

        result = await api.test_connection()
        assert result is False


class TestCloudParamToRegister:
    """Test the _CLOUD_PARAM_TO_REGISTER mapping."""

    def test_known_params_present(self):
        """Verify key parameters are in the mapping."""
        assert "main_temperature_offset" in _CLOUD_PARAM_TO_REGISTER
        assert "main_airflow" in _CLOUD_PARAM_TO_REGISTER
        assert "eco_mode" in _CLOUD_PARAM_TO_REGISTER
        assert "mode_change_request" in _CLOUD_PARAM_TO_REGISTER

    def test_duration_params_present(self):
        """Verify all timed mode duration params are mapped."""
        for key in (
            "user_mode_away_duration",
            "user_mode_crowded_duration",
            "user_mode_fireplace_duration",
            "user_mode_holiday_duration",
            "user_mode_refresh_duration",
        ):
            assert key in _CLOUD_PARAM_TO_REGISTER

    def test_register_numbers(self):
        """Verify specific register number mappings."""
        assert _CLOUD_PARAM_TO_REGISTER["main_temperature_offset"] == (2001, 1.0)
        assert _CLOUD_PARAM_TO_REGISTER["main_airflow"] == (1131, 1.0)
        assert _CLOUD_PARAM_TO_REGISTER["eco_mode"] == (2505, 1.0)
        assert _CLOUD_PARAM_TO_REGISTER["mode_change_request"] == (1162, 1.0)


class TestGetFilterInformation:
    """Tests for get_filter_information()."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        api._device_id = "device_1"
        api._device_type = "LEGACY"
        return api

    @pytest.mark.asyncio
    async def test_get_filter_information_success(self, api, mock_session):
        """Test successful GetFilterInformation call."""
        response_data = {
            "data": {
                "GetFilterInformation": {
                    "selectedFilter": "F7",
                    "itemNumber": "123456",
                }
            }
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response_data)
        )

        result = await api.get_filter_information()
        assert result == {"selectedFilter": "F7", "itemNumber": "123456"}

    @pytest.mark.asyncio
    async def test_get_filter_information_error(self, api, mock_session):
        """Test GetFilterInformation with GraphQL error."""
        response_data = {
            "errors": [{"message": "Not supported"}]
        }
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response_data)
        )

        with pytest.raises(CloudAPIError, match="GetFilterInformation failed"):
            await api.get_filter_information()

    @pytest.mark.asyncio
    async def test_get_filter_information_no_data(self, api, mock_session):
        """Test GetFilterInformation with missing data."""
        response_data = {"data": {"GetFilterInformation": None}}
        mock_session.post = MagicMock(
            return_value=MockResponse(200, json_data=response_data)
        )

        with pytest.raises(CloudAPIError, match="No GetFilterInformation"):
            await api.get_filter_information()


class TestCollectDiagnosticsData:
    """Tests for collect_diagnostics_data()."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api(self, mock_session):
        api = SystemairCloudAPI("user@example.com", "password123", session=mock_session)
        api._access_token = "valid_token"
        api._token_expiry = time.time() + 600
        api._device_id = "device_1"
        api._device_name = "My Unit"
        api._device_type = "LEGACY"
        return api

    def _make_gateway_response(self):
        return {
            "data": {
                "GetAccountDevices": [
                    {
                        "identifier": "device_1",
                        "name": "My Unit",
                        "deviceType": {"type": "LEGACY"},
                        "status": {
                            "connectionStatus": "ONLINE",
                            "serialNumber": "SN123",
                            "model": "VTR300",
                        },
                    }
                ]
            }
        }

    def _make_export_response(self, as_json_string=False):
        items = [
            {"id": 10, "extension": {"modbusRegister": 100}},
            {"id": 20, "extension": {"modbusRegister": 200}},
        ]
        return {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "LEGACY",
                    "dataItems": json.dumps(items) if as_json_string else items,
                }
            }
        }

    def _make_status_response(self):
        return {
            "data": {
                "GetDeviceStatus": {
                    "id": "device_1",
                    "connectivity": "ONLINE",
                    "activeAlarms": 0,
                    "temperature": 21.5,
                    "serialNumber": "SN123",
                }
            }
        }

    def _make_alarms_response(self):
        return {
            "data": {
                "GetActiveAlarms": {
                    "alarms": [
                        {"title": "Filter", "description": "Replace filter"}
                    ]
                }
            }
        }

    def _make_filter_response(self):
        return {
            "data": {
                "GetFilterInformation": {
                    "selectedFilter": "F7",
                    "itemNumber": "123456",
                }
            }
        }

    def _make_data_items_response(self, items):
        return {
            "data": {
                "GetDataItems": items,
            }
        }

    @pytest.mark.asyncio
    async def test_collect_all_success(self, api, mock_session):
        """Test successful collection of all data sources."""
        # The method makes multiple sequential requests.
        # Order: gateway(GetAccountDevices), remote(ExportDataItems),
        #        remote(GetDeviceStatus), remote(GetActiveAlarms),
        #        remote(GetFilterInformation), remote(GetDataItems x batches),
        #        remote(GetDataItems for sensor items)
        data_item_values = [
            {"id": 10, "value": "100"},
            {"id": 20, "value": "200"},
        ]
        sensor_values = [{"id": 5001, "value": "22"}]

        mock_session.post = MagicMock(
            side_effect=[
                MockResponse(200, json_data=self._make_gateway_response()),
                MockResponse(200, json_data=self._make_export_response()),
                MockResponse(200, json_data=self._make_status_response()),
                MockResponse(200, json_data=self._make_alarms_response()),
                MockResponse(200, json_data=self._make_filter_response()),
                MockResponse(200, json_data=self._make_data_items_response(
                    data_item_values
                )),
                MockResponse(200, json_data=self._make_data_items_response(
                    sensor_values
                )),
            ]
        )

        result = await api.collect_diagnostics_data()

        assert result["device_id"] == "device_1"
        assert result["device_name"] == "My Unit"
        assert result["device_type"] == "LEGACY"

        # Account devices
        assert isinstance(result["account_devices"], list)
        assert result["account_devices"][0]["identifier"] == "device_1"

        # ExportDataItems
        export = result["export_data_items"]
        assert export["version"] == "1.0"
        assert export["data_item_count"] == 2

        # Device status
        assert result["device_status"]["connectivity"] == "ONLINE"

        # Alarms
        assert len(result["active_alarms"]) == 1

        # Filter info
        assert result["filter_information"]["selectedFilter"] == "F7"

        # All data item values
        all_vals = result["all_data_item_values"]
        assert all_vals["requested_count"] == 2
        assert all_vals["received_count"] == 2

        # Sensor data item values
        sensor_vals = result["sensor_data_item_values"]
        assert sensor_vals["received_count"] == 1

    @pytest.mark.asyncio
    async def test_collect_partial_failures(self, api, mock_session):
        """Test that partial failures don't abort the entire collection."""
        import aiohttp

        call_count = 0

        def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Gateway fails
                raise aiohttp.ClientError("Connection refused")
            elif call_count == 2:
                # ExportDataItems fails
                raise aiohttp.ClientError("Timeout")
            elif call_count == 3:
                # GetDeviceStatus succeeds
                return MockResponse(200, json_data=self._make_status_response())
            elif call_count == 4:
                # GetActiveAlarms succeeds
                return MockResponse(200, json_data=self._make_alarms_response())
            elif call_count == 5:
                # GetFilterInformation succeeds
                return MockResponse(200, json_data=self._make_filter_response())
            else:
                # Sensor data items
                return MockResponse(200, json_data=self._make_data_items_response([]))

        mock_session.post = MagicMock(side_effect=side_effect_fn)

        result = await api.collect_diagnostics_data()

        # Failed queries return error strings
        assert "Error:" in result["account_devices"]
        assert "Error:" in result["export_data_items"]

        # Successful queries still return data
        assert result["device_status"]["connectivity"] == "ONLINE"
        assert len(result["active_alarms"]) == 1
        assert result["filter_information"]["selectedFilter"] == "F7"

        # All data items skipped because ExportDataItems failed
        assert result["all_data_item_values"] == "Skipped (ExportDataItems failed)"

    @pytest.mark.asyncio
    async def test_collect_export_as_json_string(self, api, mock_session):
        """Test ExportDataItems returns dataItems as JSON string."""
        data_items_vals = [{"id": 10, "value": "100"}, {"id": 20, "value": "200"}]
        sensor_values = []

        mock_session.post = MagicMock(
            side_effect=[
                MockResponse(200, json_data=self._make_gateway_response()),
                MockResponse(200, json_data=self._make_export_response(
                    as_json_string=True
                )),
                MockResponse(200, json_data=self._make_status_response()),
                MockResponse(200, json_data=self._make_alarms_response()),
                MockResponse(200, json_data=self._make_filter_response()),
                MockResponse(200, json_data=self._make_data_items_response(
                    data_items_vals
                )),
                MockResponse(200, json_data=self._make_data_items_response(
                    sensor_values
                )),
            ]
        )

        result = await api.collect_diagnostics_data()

        export = result["export_data_items"]
        assert export["data_item_count"] == 2
        assert isinstance(export["data_items"], list)

    @pytest.mark.asyncio
    async def test_collect_device_metadata(self, api, mock_session):
        """Test that device metadata is always included."""
        # All queries fail
        mock_session.post = MagicMock(
            side_effect=Exception("total failure")
        )

        result = await api.collect_diagnostics_data()

        # Device metadata is always present (not from API calls)
        assert result["device_id"] == "device_1"
        assert result["device_name"] == "My Unit"
        assert result["device_type"] == "LEGACY"

        # All query results are error strings
        assert "Error:" in result["account_devices"]
        assert "Error:" in result["export_data_items"]
        assert "Error:" in result["device_status"]
        assert "Error:" in result["active_alarms"]
        assert "Error:" in result["filter_information"]

    @pytest.mark.asyncio
    async def test_collect_batches_large_data_items(self, api, mock_session):
        """Test that large data item sets are batched (100 per request)."""
        # Create 150 data items
        items = [
            {"id": i, "extension": {"modbusRegister": i * 10}}
            for i in range(150)
        ]
        export_resp = {
            "data": {
                "ExportDataItems": {
                    "version": "1.0",
                    "type": "LEGACY",
                    "dataItems": items,
                }
            }
        }

        batch1_values = [{"id": i, "value": str(i)} for i in range(100)]
        batch2_values = [{"id": i, "value": str(i)} for i in range(100, 150)]
        sensor_values = []

        mock_session.post = MagicMock(
            side_effect=[
                MockResponse(200, json_data=self._make_gateway_response()),
                MockResponse(200, json_data=export_resp),
                MockResponse(200, json_data=self._make_status_response()),
                MockResponse(200, json_data=self._make_alarms_response()),
                MockResponse(200, json_data=self._make_filter_response()),
                # Two batches for data items (100 + 50)
                MockResponse(200, json_data=self._make_data_items_response(
                    batch1_values
                )),
                MockResponse(200, json_data=self._make_data_items_response(
                    batch2_values
                )),
                # Sensor data items
                MockResponse(200, json_data=self._make_data_items_response(
                    sensor_values
                )),
            ]
        )

        result = await api.collect_diagnostics_data()

        all_vals = result["all_data_item_values"]
        assert all_vals["requested_count"] == 150
        assert all_vals["received_count"] == 150

    @pytest.mark.asyncio
    async def test_collect_status_falls_back_to_basic(self, api, mock_session):
        """Test that GetDeviceStatus falls back to basic query on error."""
        status_error = {
            "errors": [{"message": "Cannot query field 'humidity'"}]
        }
        basic_status = {
            "data": {
                "GetDeviceStatus": {
                    "id": "device_1",
                    "connectivity": "ONLINE",
                    "serialNumber": "SN123",
                }
            }
        }

        mock_session.post = MagicMock(
            side_effect=[
                MockResponse(200, json_data=self._make_gateway_response()),
                MockResponse(200, json_data=self._make_export_response()),
                # First status query fails with schema error
                MockResponse(200, json_data=status_error),
                # Fallback basic query succeeds
                MockResponse(200, json_data=basic_status),
                MockResponse(200, json_data=self._make_alarms_response()),
                MockResponse(200, json_data=self._make_filter_response()),
                MockResponse(200, json_data=self._make_data_items_response([])),
                MockResponse(200, json_data=self._make_data_items_response([])),
            ]
        )

        result = await api.collect_diagnostics_data()
        assert result["device_status"]["connectivity"] == "ONLINE"


# ---------------------------------------------------------------------------
# Phase 8 quality fix tests
# ---------------------------------------------------------------------------


class TestScaleValueHelper:
    """Tests for the _scale_value static method."""

    def _make_param(self, is_boolean=False, scale_factor=1):
        p = MagicMock()
        p.is_boolean = is_boolean
        p.scale_factor = scale_factor
        return p

    def test_boolean_true(self):
        assert SystemairCloudAPI._scale_value(self._make_param(is_boolean=True), True) == "true"

    def test_boolean_false(self):
        assert SystemairCloudAPI._scale_value(self._make_param(is_boolean=True), False) == "false"

    def test_boolean_zero(self):
        assert SystemairCloudAPI._scale_value(self._make_param(is_boolean=True), 0) == "false"

    def test_scale_factor(self):
        assert SystemairCloudAPI._scale_value(self._make_param(scale_factor=10), 21.5) == "215"

    def test_integer_no_scaling(self):
        assert SystemairCloudAPI._scale_value(self._make_param(), 42) == "42"

    def test_float_truncated(self):
        assert SystemairCloudAPI._scale_value(self._make_param(), 3.9) == "3"

    def test_non_numeric_fallback(self):
        assert SystemairCloudAPI._scale_value(self._make_param(), "abc") == "abc"


class TestDeviceTypeLegacyConstant:
    """Tests for DEVICE_TYPE_LEGACY constant usage."""

    def test_constant_exported(self):
        from custom_components.systemair.cloud_api import DEVICE_TYPE_LEGACY
        assert DEVICE_TYPE_LEGACY == "LEGACY"

    def test_default_device_type_uses_constant(self):
        api = SystemairCloudAPI("a@b.com", "pw")
        from custom_components.systemair.cloud_api import DEVICE_TYPE_LEGACY
        assert api._device_type == DEVICE_TYPE_LEGACY


class TestCloseMethodCancelsWsTask:
    """Tests for close() cancelling the WS listener task."""

    @pytest.mark.asyncio
    async def test_close_cancels_active_ws_task(self):
        """close() should cancel an active WS listener task."""
        api = SystemairCloudAPI("a@b.com", "pw")
        mock_task = MagicMock()
        mock_task.done.return_value = False
        api._ws_listener_task = mock_task
        api._session = None

        await api.close()
        mock_task.cancel.assert_called_once()
        assert api._ws_listener_task is None

    @pytest.mark.asyncio
    async def test_close_skips_done_ws_task(self):
        """close() should not cancel an already-done WS task."""
        api = SystemairCloudAPI("a@b.com", "pw")
        mock_task = MagicMock()
        mock_task.done.return_value = True
        api._ws_listener_task = mock_task
        api._session = None

        await api.close()
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_handles_no_ws_task(self):
        """close() should not crash when _ws_listener_task is None."""
        api = SystemairCloudAPI("a@b.com", "pw")
        api._ws_listener_task = None
        api._session = None
        await api.close()  # no exception


class TestRefreshTokenResetsFailureCounter:
    """Tests for _refresh_access_token resetting _consecutive_login_failures."""

    @pytest.mark.asyncio
    async def test_refresh_success_resets_failures(self):
        """Successful token refresh should reset the failure counter."""
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        api = SystemairCloudAPI("a@b.com", "pw", session=session)
        api._access_token = "old"
        api._refresh_token = "old_refresh"
        api._token_expiry = 0
        api._consecutive_login_failures = 3

        session.post = MagicMock(
            return_value=MockResponse(200, json_data=REFRESHED_TOKEN_RESPONSE)
        )

        await api._refresh_access_token()
        assert api._consecutive_login_failures == 0
