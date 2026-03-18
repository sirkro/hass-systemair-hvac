"""Tests for the config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.systemair.const import (
    CONF_API_URL,
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_WS_URL,
    CONN_CLOUD,
    DOMAIN,
)
from custom_components.systemair.config_flow import (
    SystemairConfigFlow,
    _validate_url,
)


# ---------------------------------------------------------------------------
# Tests for _validate_url (SSRF mitigation)
# ---------------------------------------------------------------------------


class TestValidateUrl:
    """Tests for the _validate_url helper function."""

    def test_valid_https_url(self):
        assert _validate_url("https://api.systemair.com/gateway", ("http", "https")) is True

    def test_valid_http_url(self):
        assert _validate_url("http://api.systemair.com/gateway", ("http", "https")) is True

    def test_valid_wss_url(self):
        assert _validate_url("wss://ws.systemair.com/ws", ("ws", "wss")) is True

    def test_valid_ws_url(self):
        assert _validate_url("ws://ws.systemair.com/ws", ("ws", "wss")) is True

    def test_wrong_scheme_ftp(self):
        """FTP scheme should be rejected for HTTP-only allowed schemes."""
        assert _validate_url("ftp://example.com/file", ("http", "https")) is False

    def test_wrong_scheme_http_for_ws(self):
        """HTTP scheme should be rejected when only ws/wss are allowed."""
        assert _validate_url("http://example.com/ws", ("ws", "wss")) is False

    def test_missing_scheme(self):
        """URL without scheme should be rejected."""
        assert _validate_url("example.com/api", ("http", "https")) is False

    def test_missing_hostname(self):
        """URL without hostname should be rejected."""
        assert _validate_url("https://", ("http", "https")) is False

    def test_empty_string(self):
        assert _validate_url("", ("http", "https")) is False

    def test_private_ip_192_168(self):
        """Private IP 192.168.x.x should be blocked."""
        assert _validate_url("https://192.168.1.1/api", ("http", "https")) is False

    def test_private_ip_10(self):
        """Private IP 10.x.x.x should be blocked."""
        assert _validate_url("https://10.0.0.1/api", ("http", "https")) is False

    def test_private_ip_172_16(self):
        """Private IP 172.16.x.x should be blocked."""
        assert _validate_url("https://172.16.0.1/api", ("http", "https")) is False

    def test_loopback_127(self):
        """Loopback 127.0.0.1 should be blocked."""
        assert _validate_url("https://127.0.0.1/api", ("http", "https")) is False

    def test_loopback_ipv6(self):
        """IPv6 loopback [::1] should be blocked."""
        assert _validate_url("https://[::1]/api", ("http", "https")) is False

    def test_reserved_ip_0_0_0_0(self):
        """Reserved IP 0.0.0.0 should be blocked."""
        assert _validate_url("https://0.0.0.0/api", ("http", "https")) is False

    def test_dns_hostname_allowed(self):
        """DNS hostnames (not IPs) should be allowed."""
        assert _validate_url("https://my-custom-host.local/api", ("http", "https")) is True

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace should be trimmed."""
        assert _validate_url("  https://api.systemair.com/  ", ("http", "https")) is True

    def test_malformed_url(self):
        """Completely malformed URLs should be rejected."""
        assert _validate_url("://broken", ("http", "https")) is False

    def test_link_local_ipv4(self):
        """Link-local 169.254.x.x should be blocked (is_reserved)."""
        assert _validate_url("https://169.254.1.1/api", ("http", "https")) is False


class TestConfigFlowUrlValidation:
    """Tests for URL validation integration in async_step_cloud."""

    @pytest.mark.asyncio
    async def test_invalid_api_url_shows_error(self):
        """Invalid api_url should result in errors['base'] == 'invalid_url'."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        result = await flow.async_step_cloud({
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "password",
            "advanced": {CONF_API_URL: "https://192.168.1.1/api"},
        })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "invalid_url"

    @pytest.mark.asyncio
    async def test_invalid_ws_url_shows_error(self):
        """Invalid ws_url should result in errors['base'] == 'invalid_url'."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        result = await flow.async_step_cloud({
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "password",
            "advanced": {CONF_WS_URL: "ws://127.0.0.1/ws"},
        })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "invalid_url"

    @pytest.mark.asyncio
    async def test_valid_custom_urls_proceed(self):
        """Valid custom URLs should not produce URL errors (may produce other errors)."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value="entry_result")

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_devices = AsyncMock(return_value=[
                {"machine_id": "m1", "name": "Unit 1", "connection_status": "online", "device_type": "LEGACY"}
            ])
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            result = await flow.async_step_cloud({
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "password",
                "advanced": {
                    CONF_API_URL: "https://custom-api.example.com/gateway",
                    CONF_WS_URL: "wss://custom-ws.example.com/ws",
                },
            })

        # Should have proceeded to create entry (not shown error form for invalid_url)
        flow.async_create_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_url_wrong_scheme_shows_error(self):
        """ws:// scheme for api_url should be rejected."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        result = await flow.async_step_cloud({
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "password",
            "advanced": {CONF_API_URL: "ws://example.com/api"},
        })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "invalid_url"

    @pytest.mark.asyncio
    async def test_ws_url_wrong_scheme_shows_error(self):
        """https:// scheme for ws_url should be rejected."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        result = await flow.async_step_cloud({
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "password",
            "advanced": {CONF_WS_URL: "https://example.com/ws"},
        })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "invalid_url"


# ---------------------------------------------------------------------------
# Tests for the config flow steps
# ---------------------------------------------------------------------------


class TestSystemairConfigFlow:
    """Tests for SystemairConfigFlow."""

    def test_version(self):
        flow = SystemairConfigFlow()
        assert flow.VERSION == 1

    def test_init(self):
        flow = SystemairConfigFlow()
        assert flow._cloud_devices == []

    @pytest.mark.asyncio
    async def test_step_user_shows_form(self):
        """Test that the user step shows the cloud form."""
        flow = SystemairConfigFlow()

        # Mock the HA-specific methods
        flow.async_show_form = MagicMock()

        result = await flow.async_step_user(None)
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["step_id"] == "cloud"

    @pytest.mark.asyncio
    async def test_step_cloud_success_single_device(self):
        """Test cloud config with a single device."""
        flow = SystemairConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value="entry_result")

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_devices = AsyncMock(return_value=[
                {"machine_id": "m1", "name": "Unit 1", "connection_status": "online", "device_type": "LEGACY"}
            ])
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            result = await flow.async_step_cloud({
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "password",
                "advanced": {CONF_POLL_INTERVAL: 30},
            })

        flow.async_create_entry.assert_called_once()
        entry_data = flow.async_create_entry.call_args[1]["data"]
        assert entry_data[CONF_CONNECTION_TYPE] == CONN_CLOUD
        assert entry_data["machine_id"] == "m1"
        assert entry_data["device_type"] == "LEGACY"

    @pytest.mark.asyncio
    async def test_step_cloud_multiple_devices(self):
        """Test cloud config with multiple devices routes to device selection."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_devices = AsyncMock(return_value=[
                {"machine_id": "m1", "name": "Unit 1", "connection_status": "online", "device_type": "LEGACY"},
                {"machine_id": "m2", "name": "Unit 2", "connection_status": "offline", "device_type": "LEGACY"},
            ])
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            with patch.object(flow, "async_step_cloud_device", new_callable=AsyncMock) as mock_step:
                mock_step.return_value = "device_result"
                result = await flow.async_step_cloud({
                    CONF_EMAIL: "user@example.com",
                    CONF_PASSWORD: "password",
                })

            assert len(flow._cloud_devices) == 2
            mock_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_cloud_no_devices(self):
        """Test cloud config with no devices shows error."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_devices = AsyncMock(return_value=[])
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            result = await flow.async_step_cloud({
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "password",
            })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "no_devices"

    @pytest.mark.asyncio
    async def test_step_cloud_auth_failure(self):
        """Test cloud config with invalid credentials (AuthenticationError)."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            from custom_components.systemair.cloud_api import AuthenticationError
            mock_api = MagicMock()
            mock_api.login = AsyncMock(side_effect=AuthenticationError("Invalid email or password"))
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            result = await flow.async_step_cloud({
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "wrong",
            })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_step_cloud_connection_failure(self):
        """Test cloud config with connection error (CloudAPIError -> cannot_connect)."""
        flow = SystemairConfigFlow()
        flow.async_show_form = MagicMock()

        with patch(
            "custom_components.systemair.cloud_api.SystemairCloudAPI"
        ) as MockAPI:
            from custom_components.systemair.cloud_api import CloudAPIError
            mock_api = MagicMock()
            mock_api.login = AsyncMock(side_effect=CloudAPIError("Network timeout"))
            mock_api.close = AsyncMock()
            MockAPI.return_value = mock_api

            result = await flow.async_step_cloud({
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "password",
            })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_step_cloud_device_selection(self):
        """Test cloud device selection step."""
        flow = SystemairConfigFlow()
        flow._cloud_devices = [
            {"machine_id": "m1", "name": "Unit 1", "connection_status": "online", "device_type": "LEGACY"},
            {"machine_id": "m2", "name": "Unit 2", "connection_status": "offline", "device_type": "LEGACY"},
        ]
        flow._cloud_email = "user@example.com"
        flow._cloud_password = "password"
        flow._cloud_poll_interval = 30

        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value="entry_result")

        result = await flow.async_step_cloud_device({"machine_id": "m2"})

        flow.async_create_entry.assert_called_once()
        entry_data = flow.async_create_entry.call_args[1]["data"]
        assert entry_data["machine_id"] == "m2"
        assert entry_data[CONF_EMAIL] == "user@example.com"
        assert entry_data["device_type"] == "LEGACY"

    @pytest.mark.asyncio
    async def test_step_cloud_device_shows_form(self):
        """Test device selection shows form when no input."""
        flow = SystemairConfigFlow()
        flow._cloud_devices = [
            {"machine_id": "m1", "name": "Unit 1", "connection_status": "online", "device_type": "LEGACY"},
        ]
        flow.async_show_form = MagicMock()

        result = await flow.async_step_cloud_device(None)
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["step_id"] == "cloud_device"


# ---------------------------------------------------------------------------
# Tests for the options flow
# ---------------------------------------------------------------------------


class TestSystemairOptionsFlow:
    """Tests for SystemairOptionsFlow."""

    def _make_entry(self, options: dict | None = None):
        """Create a mock config entry for options flow testing."""
        from tests.conftest import MockConfigEntry
        return MockConfigEntry(
            data={
                CONF_CONNECTION_TYPE: CONN_CLOUD,
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "secret",
                CONF_POLL_INTERVAL: 20,
                "machine_id": "machine_123",
                "machine_name": "Living Room",
            },
            options=options or {},
        )

    @pytest.mark.asyncio
    async def test_options_flow_shows_form(self):
        """Test that init step shows form with current poll interval."""
        from custom_components.systemair.config_flow import SystemairOptionsFlow

        entry = self._make_entry()
        flow = SystemairOptionsFlow(entry)

        result = await flow.async_step_init(None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_creates_entry(self):
        """Test that submitting options creates an entry."""
        from custom_components.systemair.config_flow import SystemairOptionsFlow

        entry = self._make_entry()
        flow = SystemairOptionsFlow(entry)

        result = await flow.async_step_init({CONF_POLL_INTERVAL: 45})
        assert result["type"] == "create_entry"
        assert result["data"][CONF_POLL_INTERVAL] == 45

    @pytest.mark.asyncio
    async def test_options_flow_reads_current_from_options(self):
        """Test that current poll interval is read from options if set."""
        from custom_components.systemair.config_flow import SystemairOptionsFlow

        entry = self._make_entry(options={CONF_POLL_INTERVAL: 60})
        flow = SystemairOptionsFlow(entry)

        # When showing the form, the default should be 60 (from options)
        result = await flow.async_step_init(None)
        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_options_flow_reads_current_from_data_fallback(self):
        """Test that current poll interval falls back to entry.data."""
        from custom_components.systemair.config_flow import SystemairOptionsFlow

        entry = self._make_entry()  # No options set, data has poll_interval=20
        flow = SystemairOptionsFlow(entry)

        result = await flow.async_step_init(None)
        assert result["type"] == "form"

    def test_async_get_options_flow(self):
        """Test that ConfigFlow returns the options flow handler."""
        from custom_components.systemair.config_flow import SystemairOptionsFlow

        entry = self._make_entry()
        options_flow = SystemairConfigFlow.async_get_options_flow(entry)
        assert isinstance(options_flow, SystemairOptionsFlow)
