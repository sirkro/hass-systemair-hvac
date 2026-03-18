#!/usr/bin/env python3
"""Mock Systemair HVAC server for local development and testing.

Simulates all three connection types:
  - Modbus TCP on port 10502 (use 502 with --privileged or port mapping)
  - SaveConnect HTTP on port 8899
  - Cloud GraphQL + WebSocket on port 8443

All three share the same underlying register state, so changes via one
protocol are visible from the others.

Usage:
    python mock_server.py                  # start all servers (localhost only)
    python mock_server.py --bind 0.0.0.0   # bind to all interfaces (Docker)
    python mock_server.py --modbus-only    # start only Modbus TCP
    python mock_server.py --http-only      # start only SaveConnect HTTP
    python mock_server.py --cloud-only     # start only Cloud WS

Security: By default the server binds to 127.0.0.1 (localhost only).
Use --bind 0.0.0.0 only when you need to expose the server to Docker
containers or VMs on the same host.

The mock simulates a SAVE VTR 300 unit with realistic sensor values that
drift slowly over time to make the dashboard more interesting.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import struct
import time
from typing import Any
from urllib.parse import unquote

from aiohttp import web, WSMsgType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
_LOG = logging.getLogger("mock")

# ---------------------------------------------------------------------------
# Shared register state
# ---------------------------------------------------------------------------

_start_time = time.time()


class HVACState:
    """Shared state for the simulated HVAC unit.

    Register values are stored as raw unsigned 16-bit integers, matching
    what a real Modbus device would return. Temperature registers use
    scale factor 10 (value 210 = 21.0 C).
    """

    def __init__(self) -> None:
        # Holding registers (writable) -- keyed by 1-based register address
        self._holdings: dict[int, int] = {
            # Temperature setpoint  (21.0 C)
            2001: 210,
            # Fan mode manual SAF: 3=Normal
            1131: 3,
            # Active user mode: 0=Auto
            1161: 0,
            # HMI change request
            1162: 0,
            # ECO mode on/off
            2505: 0,
            # Mode time settings
            1101: 7,    # Holiday time (days)
            1102: 24,   # Away time (hours)
            1103: 30,   # Fireplace time (min)
            1104: 60,   # Refresh time (min)
            1105: 4,    # Crowded time (hours)
            # Airflow levels for modes
            1135: 4, 1136: 4,  # Crowded SAF/EAF
            1137: 4, 1138: 4,  # Refresh SAF/EAF
            1139: 4, 1140: 2,  # Fireplace SAF/EAF
            1141: 2, 1142: 2,  # Away SAF/EAF
            1143: 1, 1144: 1,  # Holiday SAF/EAF
            1145: 3, 1146: 3,  # CookerHood SAF/EAF
            1147: 3, 1148: 3,  # VacuumCleaner SAF/EAF
            1177: 3, 1178: 3,  # PressureGuard SAF/EAF
            # Temperature sensors (scale 10)
            12102: 50,    # OAT  5.0 C
            12103: 215,   # SAT  21.5 C
            12105: 223,   # EAT  22.3 C
            12108: 250,   # OHT  25.0 C
            # Humidity
            12109: 42,    # RHS 42%
            12544: 221,   # PDM EAT 22.1 C
            12136: 45,    # PDM RHS 45%
        }

        # Input registers (read-only) -- keyed by 1-based register address
        self._inputs: dict[int, int] = {
            # Demand control
            1001: 42,
            # Active user mode (mirrors holding 1161)
            1161: 0,
            # Remaining time
            1111: 0, 1112: 0,
            # Fan RPM
            12401: 1450,  # SAF RPM
            12402: 1380,  # EAF RPM
            # Fan speed %
            14001: 65,    # SAF speed
            14002: 60,    # EAF speed
            # Cooler/Heater outputs
            14201: 0, 14202: 0,
            14101: 35, 14102: 0,
            # Filter remaining time (30 days = 2592000 seconds)
            # Low 16 bits: 2592000 & 0xFFFF = 38400
            # High 16 bits: 2592000 >> 16 = 39
            7005: 38400,
            7006: 39,
            # Alarms (all clear = 0)
            15016: 0, 15023: 0, 15030: 0, 15037: 0,
            15072: 0, 15086: 0, 15121: 0, 15142: 0,
            15170: 0, 15177: 0, 15530: 0, 15537: 0,
            15544: 0, 15901: 0, 15902: 0, 15903: 0,
            # Functions (all inactive)
            3113: 0, 3114: 0, 3115: 0, 3116: 0, 3117: 0,
            # Digital inputs
            12306: 0, 12307: 0,
        }

    def get_register(self, address_1based: int) -> int:
        """Get a register value (holding or input).

        Returns 0 for unknown registers.
        """
        if address_1based in self._holdings:
            return self._holdings[address_1based]
        if address_1based in self._inputs:
            return self._inputs[address_1based]
        return 0

    def set_register(self, address_1based: int, value: int) -> None:
        """Set a holding register value."""
        value = max(0, min(65535, value))
        self._holdings[address_1based] = value
        _LOG.info(
            "Register %d set to %d (0x%04X)", address_1based, value, value
        )

        # Handle HMI mode change request -> update active mode
        if address_1based == 1162 and value > 0:
            new_mode = value - 1
            self._holdings[1161] = new_mode
            self._inputs[1161] = new_mode
            _LOG.info("User mode changed to %d via HMI request", new_mode)

    def apply_drift(self) -> None:
        """Apply slow sinusoidal drift to sensor values for realism."""
        t = time.time() - _start_time

        # Outdoor temperature: 5 C +/- 3 C over 10 min cycle
        oat = int(50 + 30 * math.sin(t / 300))
        self._holdings[12102] = max(0, oat) if oat >= 0 else (65536 + oat)

        # Supply air temp: tracks setpoint closely
        sp = self._holdings[2001]
        sat_drift = int(5 * math.sin(t / 120))
        self._holdings[12103] = sp + sat_drift

        # Extract air temp: 22 +/- 0.5 C
        eat = int(220 + 5 * math.sin(t / 180))
        self._holdings[12105] = eat
        self._holdings[12544] = eat - 2  # PDM EAT slightly lower

        # Humidity: 42% +/- 5%
        rh = int(42 + 5 * math.sin(t / 240))
        self._holdings[12109] = max(0, min(100, rh))
        self._holdings[12136] = max(0, min(100, rh + 3))

        # Fan RPM: slight variation
        self._inputs[12401] = 1450 + int(50 * math.sin(t / 60))
        self._inputs[12402] = 1380 + int(40 * math.sin(t / 75))

    def to_cloud_params(self) -> dict[str, Any]:
        """Export current state as cloud API parameter dict."""

        def _signed(reg: int) -> int:
            v = self.get_register(reg)
            if v > 32767:
                return v - 65536
            return v

        return {
            "main_temperature_offset": _signed(2001),
            "supply_air_temp": _signed(12103),
            "outdoor_air_temp": _signed(12102),
            "pdm_input_temp_value": _signed(12544),
            "overheat_temp": _signed(12108),
            "pdm_input_rh_value": self.get_register(12136),
            "rh_sensor": self.get_register(12109),
            "speed_indication_app": self.get_register(1131),
            "main_user_mode": self.get_register(1161),
            "main_airflow": self.get_register(1131),
            "eco_mode": self.get_register(2505),
            "control_regulation_temp_unit": 0,
            "demand_control_fan_speed": 3,
            "control_regulation_speed_after_free_cooling_saf": self.get_register(14001),
            "control_regulation_speed_after_free_cooling_eaf": self.get_register(14002),
            "digital_input_tacho_saf_value": self.get_register(12401),
            "digital_input_tacho_eaf_value": self.get_register(12402),
            "digital_input_type1": 0,
            "digital_input_type2": 0,
            "digital_input_value1": 0,
            "digital_input_value2": 0,
            "components_filter_time_left": (
                self.get_register(7005)
                + self.get_register(7006) * 65536
            ),
            "user_mode_remaining_time": (
                self.get_register(1111)
                + self.get_register(1112) * 65536
            ),
            # Alarms (all inactive)
            "alarm_co2_state": "inactive",
            "alarm_defrosting_state": "inactive",
            "alarm_eaf_rpm_state": "inactive",
            "alarm_eat_state": "inactive",
            "alarm_emt_state": "inactive",
            "alarm_filter_state": "inactive",
            "alarm_filter_warning_state": "inactive",
            "alarm_fire_alarm_state": "inactive",
            "alarm_frost_prot_state": "inactive",
            "alarm_low_sat_state": "inactive",
            "alarm_manual_mode_state": "inactive",
            "alarm_overheat_temperature_state": "inactive",
            "alarm_pdm_rhs_state": "inactive",
            "alarm_rgs_state": "inactive",
            "alarm_rh_state": "inactive",
            "alarm_rotor_motor_feedback_state": "inactive",
            "alarm_saf_rpm_state": "inactive",
            "alarm_sat_state": "inactive",
            # Functions (all inactive)
            "function_active_configurable_di1": False,
            "function_active_configurable_di2": False,
            "function_active_configurable_di3": False,
            "function_active_cooker_hood": False,
            "function_active_cooling_recovery": False,
            "function_active_cooling": False,
            "function_active_defrosting": False,
            "function_active_free_cooling": False,
            "function_active_heat_recovery": True,
            "function_active_heater_cooldown": False,
            "function_active_heating": True,
            "function_active_moisture_transfer": False,
            "function_active_pressure_guard": False,
            "function_active_secondary_air": False,
            "function_active_service_user_lock": False,
            "function_active_vacuum_cleaner": False,
        }


# Single shared state instance
STATE = HVACState()


# ---------------------------------------------------------------------------
# Modbus TCP Server
# ---------------------------------------------------------------------------

FUNCTION_READ_HOLDING = 0x03
FUNCTION_READ_INPUT = 0x04
FUNCTION_WRITE_SINGLE = 0x06


async def handle_modbus_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Handle a single Modbus TCP client connection."""
    addr = writer.get_extra_info("peername")
    _LOG.info("[Modbus] Client connected: %s", addr)

    try:
        while True:
            # Read MBAP header (7 bytes)
            header = await asyncio.wait_for(reader.readexactly(7), timeout=300)
            tx_id, proto_id, length, unit_id = struct.unpack("!HHHB", header)

            # Read PDU (length - 1 for unit_id already read)
            pdu = await reader.readexactly(length - 1)
            func_code = pdu[0]

            if func_code in (FUNCTION_READ_HOLDING, FUNCTION_READ_INPUT):
                start_addr, quantity = struct.unpack("!HH", pdu[1:5])
                reg_1based = start_addr + 1

                # Build response data
                values = []
                for i in range(quantity):
                    values.append(STATE.get_register(reg_1based + i))

                byte_count = quantity * 2
                resp_pdu = bytes([func_code, byte_count])
                for v in values:
                    resp_pdu += struct.pack("!H", v)

                _LOG.debug(
                    "[Modbus] READ reg=%d qty=%d -> %s",
                    reg_1based, quantity, values,
                )

            elif func_code == FUNCTION_WRITE_SINGLE:
                address, value = struct.unpack("!HH", pdu[1:5])
                reg_1based = address + 1
                STATE.set_register(reg_1based, value)
                # Echo request as response
                resp_pdu = pdu

                _LOG.info(
                    "[Modbus] WRITE reg=%d value=%d", reg_1based, value,
                )

            else:
                # Unsupported function -- return error
                resp_pdu = bytes([func_code | 0x80, 0x01])
                _LOG.warning("[Modbus] Unsupported function: 0x%02X", func_code)

            # Send response
            resp_length = len(resp_pdu) + 1  # +1 for unit_id
            resp_header = struct.pack("!HHHB", tx_id, proto_id, resp_length, unit_id)
            writer.write(resp_header + resp_pdu)
            await writer.drain()

    except (asyncio.IncompleteReadError, ConnectionError, asyncio.TimeoutError):
        _LOG.info("[Modbus] Client disconnected: %s", addr)
    finally:
        writer.close()
        await writer.wait_closed()


async def start_modbus_server(
    port: int = 10502, bind: str = "127.0.0.1"
) -> asyncio.Server:
    """Start the Modbus TCP server."""
    server = await asyncio.start_server(handle_modbus_client, bind, port)
    _LOG.info("[Modbus] Listening on %s:%d", bind, port)
    return server


# ---------------------------------------------------------------------------
# SaveConnect HTTP Server
# ---------------------------------------------------------------------------


async def handle_mread(request: web.Request) -> web.Response:
    """Handle GET /mread?{json} -- read registers."""
    query_string = unquote(request.query_string)
    if not query_string:
        return web.json_response({})

    try:
        requested = json.loads(query_string)
    except json.JSONDecodeError:
        return web.Response(text="Invalid JSON", status=400)

    result = {}
    for key_str in requested:
        reg_0based = int(key_str)
        reg_1based = reg_0based + 1
        result[key_str] = STATE.get_register(reg_1based)

    _LOG.debug("[HTTP] mread: %d registers", len(result))
    return web.json_response(result)


async def handle_mwrite(request: web.Request) -> web.Response:
    """Handle GET /mwrite?{json} -- write registers."""
    query_string = unquote(request.query_string)
    if not query_string:
        return web.Response(text="OK")

    try:
        to_write = json.loads(query_string)
    except json.JSONDecodeError:
        return web.Response(text="Invalid JSON", status=400)

    for key_str, value in to_write.items():
        reg_0based = int(key_str)
        reg_1based = reg_0based + 1
        STATE.set_register(reg_1based, int(value))

    _LOG.info("[HTTP] mwrite: %d registers", len(to_write))
    return web.Response(text="OK")


async def handle_root(request: web.Request) -> web.Response:
    """Handle GET / -- health check."""
    return web.Response(text="Mock Systemair SaveConnect")


async def start_http_server(
    port: int = 8899, bind: str = "127.0.0.1"
) -> web.AppRunner:
    """Start the SaveConnect HTTP server."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/mread", handle_mread)
    app.router.add_get("/mwrite", handle_mwrite)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind, port)
    await site.start()
    _LOG.info("[HTTP] SaveConnect listening on %s:%d", bind, port)
    return runner


# ---------------------------------------------------------------------------
# Cloud Keycloak OIDC + GraphQL Gateway Server
# ---------------------------------------------------------------------------

MOCK_ACCESS_TOKEN = "mock-access-token-systemair-12345"
MOCK_REFRESH_TOKEN = "mock-refresh-token-systemair-67890"
MOCK_AUTH_CODE = "mock-auth-code-abc123"
MOCK_MACHINE_ID = "mock-machine-001"
MOCK_MACHINE_NAME = "SAVE VTR 300 (Mock)"

# Cloud parameter -> register mapping for writes
CLOUD_WRITE_MAP: dict[str, tuple[int, float]] = {
    # param_name -> (register_1based, scale_factor)
    "main_temperature_offset": (2001, 1.0),  # already x10 from client
    "main_airflow": (1131, 1.0),
    "eco_mode": (2505, 1.0),
    "mode_change_request": (1162, 1.0),
    "user_mode_away_duration": (1102, 1.0),
    "user_mode_crowded_duration": (1105, 1.0),
    "user_mode_fireplace_duration": (1103, 1.0),
    "user_mode_holiday_duration": (1101, 1.0),
    "user_mode_refresh_duration": (1104, 1.0),
}


async def handle_keycloak_auth(request: web.Request) -> web.Response:
    """Handle GET /auth/realms/iot/protocol/openid-connect/auth -- Keycloak login page.

    Returns an HTML page with a login form whose action URL points to our
    mock credential handler.
    """
    client_id = request.query.get("client_id", "")
    redirect_uri = request.query.get("redirect_uri", "")
    _LOG.info("[Cloud] Keycloak auth page requested (client_id=%s)", client_id)

    # Build a mock Keycloak login form
    # The form action URL points to our mock credential handler
    base_url = f"http://{request.host}"
    form_action = f"{base_url}/auth/realms/iot/login-actions/authenticate?redirect_uri={redirect_uri}"

    html = f"""<!DOCTYPE html>
<html>
<head><title>Mock Keycloak Login</title></head>
<body>
<form id="kc-form-login" action="{form_action}" method="post">
<input type="text" name="username" />
<input type="password" name="password" />
<input type="submit" value="Log In" />
</form>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_keycloak_login_action(request: web.Request) -> web.Response:
    """Handle POST /auth/realms/iot/login-actions/authenticate -- form credential submission.

    On success, redirects to redirect_uri with ?code=... parameter.
    On failure, returns 200 with the login form again (Keycloak behavior).
    """
    form = await request.post()
    username = form.get("username", "")
    password = form.get("password", "")
    redirect_uri = request.query.get("redirect_uri", "https://homesolutions.systemair.com")

    _LOG.info("[Cloud] Keycloak login attempt: %s", username)

    if username and password:
        # Successful login -- redirect with auth code
        location = f"{redirect_uri}?code={MOCK_AUTH_CODE}"
        return web.Response(status=302, headers={"Location": location})
    else:
        # Failed login -- return 200 with form (Keycloak behavior)
        return web.Response(
            text="<html><body>Invalid credentials</body></html>",
            content_type="text/html",
        )


async def handle_keycloak_token(request: web.Request) -> web.Response:
    """Handle POST /auth/realms/iot/protocol/openid-connect/token -- token exchange.

    Supports both authorization_code and refresh_token grant types.
    """
    form = await request.post()
    grant_type = form.get("grant_type", "")

    if grant_type == "authorization_code":
        code = form.get("code", "")
        _LOG.info("[Cloud] Token exchange (auth code=%s...)", code[:20] if code else "")
        if code == MOCK_AUTH_CODE:
            return web.json_response({
                "access_token": MOCK_ACCESS_TOKEN,
                "refresh_token": MOCK_REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid email profile",
            })
        else:
            return web.json_response(
                {"error": "invalid_grant"}, status=400
            )

    elif grant_type == "refresh_token":
        refresh_token = form.get("refresh_token", "")
        _LOG.info("[Cloud] Token refresh")
        if refresh_token == MOCK_REFRESH_TOKEN:
            return web.json_response({
                "access_token": MOCK_ACCESS_TOKEN,
                "refresh_token": MOCK_REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid email profile",
            })
        else:
            return web.json_response(
                {"error": "invalid_grant"}, status=400
            )

    return web.json_response(
        {"error": "unsupported_grant_type"}, status=400
    )


async def handle_gateway_api(request: web.Request) -> web.Response:
    """Handle POST /gateway/api -- GraphQL endpoint (new API)."""
    # Check access token
    token = request.headers.get("x-access-token", "")
    body = await request.json()
    query = body.get("query", "")
    variables = body.get("variables", {})

    # GetAccount
    if "GetAccount" in query:
        _LOG.info("[Cloud] GetAccount")
        if token != MOCK_ACCESS_TOKEN:
            return web.json_response(
                {"errors": [{"message": "Unauthorized"}]}, status=401
            )
        return web.json_response({
            "data": {
                "GetAccount": {
                    "email": "mock@systemair.com",
                    "firstName": "Mock",
                    "lastName": "User",
                    "devices": [
                        {
                            "name": MOCK_MACHINE_NAME,
                            "identifier": MOCK_MACHINE_ID,
                            "connectionStatus": "online",
                            "latestSync": "2026-03-17T12:00:00Z",
                        }
                    ],
                }
            }
        })

    # GetDeviceView
    if "GetDeviceView" in query:
        inp = variables.get("input", {})
        device_id = inp.get("deviceId", "")
        route = inp.get("route", "")
        _LOG.info("[Cloud] GetDeviceView device=%s route=%s", device_id, route)

        if token != MOCK_ACCESS_TOKEN:
            return web.json_response(
                {"errors": [{"message": "Unauthorized"}]}, status=401
            )

        # Return current state as data items
        all_params = STATE.to_cloud_params()
        data_items = [
            {"key": k, "value": v} for k, v in all_params.items()
        ]

        return web.json_response({
            "data": {
                "GetDeviceView": {
                    "result": 0,
                    "dataItems": json.dumps(data_items),
                    "errorMessage": None,
                }
            }
        })

    # WriteDeviceValues
    if "WriteDeviceValues" in query:
        inp = variables.get("input", {})
        device_id = inp.get("deviceId", "")
        register_values_str = inp.get("registerValues", "[]")
        _LOG.info("[Cloud] WriteDeviceValues device=%s", device_id)

        if token != MOCK_ACCESS_TOKEN:
            return web.json_response(
                {"errors": [{"message": "Unauthorized"}]}, status=401
            )

        try:
            register_values = json.loads(register_values_str)
        except (json.JSONDecodeError, TypeError):
            register_values = []

        for rv in register_values:
            reg = rv.get("register")
            val = rv.get("value")
            if reg is not None and val is not None:
                STATE.set_register(int(reg), int(val))

        return web.json_response({
            "data": {
                "WriteDeviceValues": {
                    "result": 0,
                    "errorMessage": None,
                }
            }
        })

    return web.json_response({"errors": [{"message": "Unknown query"}]})


async def handle_ws_streaming(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections at /streaming/ (new push events endpoint)."""
    # Auth via subprotocol
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _LOG.info("[Cloud] WebSocket streaming client connected")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            _LOG.debug("[Cloud] WS streaming message: %s", msg.data[:200])
        elif msg.type == WSMsgType.ERROR:
            _LOG.error("[Cloud] WS streaming error: %s", ws.exception())

    _LOG.info("[Cloud] WebSocket streaming client disconnected")
    return ws


async def start_cloud_server(
    port: int = 8443, bind: str = "127.0.0.1"
) -> web.AppRunner:
    """Start the Cloud Keycloak + GraphQL server."""
    app = web.Application()
    # Keycloak OIDC endpoints
    app.router.add_get(
        "/auth/realms/iot/protocol/openid-connect/auth", handle_keycloak_auth
    )
    app.router.add_post(
        "/auth/realms/iot/login-actions/authenticate", handle_keycloak_login_action
    )
    app.router.add_post(
        "/auth/realms/iot/protocol/openid-connect/token", handle_keycloak_token
    )
    # GraphQL gateway API (new endpoint)
    app.router.add_post("/gateway/api", handle_gateway_api)
    # Legacy endpoint (redirect to new)
    app.router.add_post("/portal-gateway/api", handle_gateway_api)
    # WebSocket streaming (new endpoint)
    app.router.add_get("/streaming/", handle_ws_streaming)
    app.router.add_get("/streaming", handle_ws_streaming)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind, port)
    await site.start()
    _LOG.info("[Cloud] Keycloak+GraphQL listening on %s:%d", bind, port)
    return runner


# ---------------------------------------------------------------------------
# Sensor drift background task
# ---------------------------------------------------------------------------

async def drift_loop() -> None:
    """Periodically update sensor values for realism."""
    while True:
        STATE.apply_drift()
        await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(
    modbus: bool = True,
    http: bool = True,
    cloud: bool = True,
    modbus_port: int = 10502,
    http_port: int = 8888,
    cloud_port: int = 8443,
    bind: str = "127.0.0.1",
) -> None:
    """Start all mock servers."""
    if bind != "127.0.0.1":
        _LOG.warning(
            "Binding to %s — the mock server will be accessible from "
            "the network. Only use this for Docker or VM setups.",
            bind,
        )

    tasks: list[Any] = []
    runners: list[web.AppRunner] = []

    # Start sensor drift
    drift_task = asyncio.create_task(drift_loop())
    tasks.append(drift_task)

    if modbus:
        server = await start_modbus_server(modbus_port, bind)
        tasks.append(server)

    if http:
        runner = await start_http_server(http_port, bind)
        runners.append(runner)

    if cloud:
        runner = await start_cloud_server(cloud_port, bind)
        runners.append(runner)

    _LOG.info("")
    _LOG.info("=" * 60)
    _LOG.info("  Mock Systemair HVAC Server Running")
    _LOG.info("=" * 60)
    if modbus:
        _LOG.info("  Modbus TCP:     localhost:%d", modbus_port)
    if http:
        _LOG.info("  SaveConnect:    http://localhost:%d", http_port)
    if cloud:
        _LOG.info("  Cloud Keycloak: http://localhost:%d/auth/...", cloud_port)
        _LOG.info("  Cloud GraphQL:  http://localhost:%d/gateway/api", cloud_port)
        _LOG.info("  Cloud WS:       ws://localhost:%d/streaming/", cloud_port)
    _LOG.info("")
    _LOG.info("  Cloud credentials: any email / any password")
    _LOG.info("  Machine: %s (%s)", MOCK_MACHINE_NAME, MOCK_MACHINE_ID)
    _LOG.info("=" * 60)
    _LOG.info("")

    # Run forever
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        drift_task.cancel()
        for runner in runners:
            await runner.cleanup()


def cli() -> None:
    """Parse CLI arguments and start servers."""
    parser = argparse.ArgumentParser(
        description="Mock Systemair HVAC server for local development"
    )
    parser.add_argument(
        "--modbus-only", action="store_true",
        help="Start only the Modbus TCP server",
    )
    parser.add_argument(
        "--http-only", action="store_true",
        help="Start only the SaveConnect HTTP server",
    )
    parser.add_argument(
        "--cloud-only", action="store_true",
        help="Start only the Cloud GraphQL/WS server",
    )
    parser.add_argument(
        "--modbus-port", type=int, default=10502,
        help="Modbus TCP port (default: 10502)",
    )
    parser.add_argument(
        "--http-port", type=int, default=8899,
        help="SaveConnect HTTP port (default: 8899)",
    )
    parser.add_argument(
        "--cloud-port", type=int, default=8443,
        help="Cloud GraphQL/WS port (default: 8443)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--bind", type=str, default="127.0.0.1",
        help="Address to bind to (default: 127.0.0.1, use 0.0.0.0 for Docker)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine which servers to run
    any_only = args.modbus_only or args.http_only or args.cloud_only
    run_modbus = args.modbus_only or not any_only
    run_http = args.http_only or not any_only
    run_cloud = args.cloud_only or not any_only

    asyncio.run(main(
        modbus=run_modbus,
        http=run_http,
        cloud=run_cloud,
        modbus_port=args.modbus_port,
        http_port=args.http_port,
        cloud_port=args.cloud_port,
        bind=args.bind,
    ))


if __name__ == "__main__":
    cli()
