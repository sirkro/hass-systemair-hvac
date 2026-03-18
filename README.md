# Systemair HVAC - Home Assistant Integration

[![Validate](https://github.com/sirkro/hass-systemair-hvac/actions/workflows/validate.yaml/badge.svg)](https://github.com/sirkro/hass-systemair-hvac/actions/workflows/validate.yaml)
[![Tests](https://github.com/sirkro/hass-systemair-hvac/actions/workflows/tests.yaml/badge.svg)](https://github.com/sirkro/hass-systemair-hvac/actions/workflows/tests.yaml)

A custom [Home Assistant](https://www.home-assistant.io/) integration for Systemair HVAC ventilation units via the **Systemair Cloud** (WebSocket + GraphQL).

This integration is based on the [Systemair Homey app](https://github.com/balmli/com.systemair) by [balmli](https://github.com/balmli), ported from TypeScript/JavaScript to Python for Home Assistant.

## Table of Contents

- [Features](#features)
- [Supported Hardware](#supported-hardware)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Services](#services)
- [Options](#options)
- [Diagnostics](#diagnostics)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements](#acknowledgements)
- [License](#license)

## Features

- **Climate entity** with target temperature, fan speed control (low/medium/high), HVAC mode (auto/fan only), and preset modes (away, boost, comfort, fireplace, holiday)
- **21 sensor entities** covering temperatures, humidity, CO2, air quality, fan RPM/speed, filter life, heater/cooler output, heat exchanger info, and current mode
- **39 binary sensors** for alarm states (18), active functions (19), and heater/cooler status (2)
- **21 number entities** for per-mode fan level configuration (16) and timed mode durations (5)
- **ECO mode switch** and **moisture transfer switch** for toggling energy-saving and moisture transfer settings
- **User mode select** to switch between Auto and Manual modes
- **Timed mode services** to activate Away, Crowded, Fireplace, Holiday, or Refresh modes with configurable durations
- **Preset modes** on the climate entity for quick access to timed ventilation modes
- **WebSocket push** for real-time updates between polling intervals
- **Options flow** to reconfigure poll interval after setup
- **Diagnostics** support for debugging with automatic credential redaction
- **Config flow** with connection testing -- validates connectivity before completing setup
- **Translations** in English and Norwegian Bokmal

## Supported Hardware

This integration works with Systemair SAVE ventilation units registered in the **Systemair Home Solutions** cloud portal.

**Requirements:**
- A Systemair Home Solutions account (https://homesolutions.systemair.com)
- At least one unit registered in the cloud portal
- Internet access from the Home Assistant host

Tested with SAVE VTR series units. Other Systemair SAVE models using the same cloud API should work.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click the three dots menu and select **Custom repositories**
4. Add `https://github.com/sirkro/hass-systemair-hvac` and select **Integration** as the category
5. Search for and install **Systemair HVAC**
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/systemair` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Systemair**
3. Enter your Systemair Cloud email and password
4. The integration tests the connection before completing setup
5. If your account has multiple devices, select which one to configure
6. On success, all entities are created automatically

**Advanced options** (collapsed by default in the config flow):
- **Poll interval**: How often to fetch data (default: 20 seconds, range: 10-300)
- **API URL**: Custom gateway API URL (leave empty for default)
- **WS URL**: Custom WebSocket URL (leave empty for default)

## Entities

All entities are grouped under a single device named after your config entry title (e.g. "Systemair Cloud (My Unit)").

### Climate

| Entity | Description |
|---|---|
| Climate | Main climate entity with temperature control, fan speed, and HVAC mode |

**Features:**
- **Current temperature**: Shows the supply air temperature
- **Target temperature**: Adjustable from 12 C to 30 C (1 C steps)
- **HVAC modes**: `auto` (Auto user mode) and `fan_only` (Manual user mode)
- **Fan modes**: `low`, `medium`, `high`
- **Preset modes**: `away`, `boost`, `comfort`, `fireplace`, `holiday`
- **HVAC action**: Shows `heating`, `cooling`, `fan`, or `idle` based on active functions

| Preset | Systemair Mode | Default Duration |
|---|---|---|
| away | Away | 8 hours |
| boost | Refresh | 60 minutes |
| comfort | Crowded | 4 hours |
| fireplace | Fireplace | 30 minutes |
| holiday | Holiday | 7 days |

**Extra state attributes:**
- `user_mode` -- current user mode name (Auto, Manual, Away, etc.)
- `user_mode_id` -- current user mode numeric value
- `outdoor_temperature` -- outdoor air temperature
- `extract_temperature` -- extract air temperature
- `eco_mode` -- whether ECO mode is active

### Sensors (21)

| Entity | Unit | Device Class | Description |
|---|---|---|---|
| Supply air temperature | C | temperature | Air temperature after the heat exchanger |
| Outdoor air temperature | C | temperature | Outside air temperature |
| Extract air temperature | C | temperature | Air temperature extracted from rooms |
| Overheat temperature | C | temperature | Overheat protection sensor |
| Humidity | % | humidity | Relative humidity |
| CO2 | ppm | carbon_dioxide | CO2 concentration |
| Supply air fan RPM | rpm | -- | Supply air fan revolutions per minute |
| Extract air fan RPM | rpm | -- | Extract air fan revolutions per minute |
| Supply air fan speed | % | -- | Supply air fan speed as percentage |
| Extract air fan speed | % | -- | Extract air fan speed as percentage |
| Filter days remaining | days | -- | Days until filter replacement is needed |
| User mode | -- | -- | Current user mode name |
| Fan mode | -- | -- | Current fan mode name |
| Heater output | % | -- | Heater output percentage (cloud: unavailable) |
| Cooler output | % | -- | Cooler output percentage (cloud: unavailable) |
| Timed mode remaining | min | duration | Minutes remaining for active timed mode (unavailable when no timed mode is active) |
| Air quality | -- | -- | Air quality index |
| Heat exchanger type | -- | -- | Type of heat exchanger (diagnostic) |
| Heat exchanger speed | % | -- | Heat exchanger rotation speed |
| Heater type | -- | -- | Type of heater installed (diagnostic) |
| Heater position | -- | -- | Heater position (diagnostic) |

### Binary Sensors (39)

**Alarm sensors** (18, device class: `problem`, disabled by default):

| Entity | Description |
|---|---|
| Alarm: CO2 | CO2 level alarm |
| Alarm: Defrosting | Defrosting alarm |
| Alarm: Extract air fan RPM | EAF RPM alarm |
| Alarm: Extract air temperature | EAT alarm |
| Alarm: Frost protection (EMT) | EMT frost protection alarm |
| Alarm: Filter | Filter replacement alarm |
| Alarm: Filter warning | Filter warning |
| Alarm: Fire alarm | Fire alarm state |
| Alarm: Frost protection | Frost protection alarm |
| Alarm: Low supply air temperature | Low SAT alarm |
| Alarm: Manual mode | Manual mode alarm |
| Alarm: Overheat temperature | Overheat alarm |
| Alarm: Rel. humidity sensor malfunction (PDM) | PDM RHS sensor malfunction |
| Alarm: Rotation guard (RGS) | Rotation guard alarm |
| Alarm: Rel. humidity sensor malfunction (RH) | RH sensor malfunction |
| Alarm: Rotor motor feedback | Rotor motor feedback alarm |
| Alarm: Supply air fan RPM | SAF RPM alarm |
| Alarm: Supply air temperature | SAT alarm |

**Function sensors** (19, device class: `running`, enabled by default):

| Entity | Description |
|---|---|
| Function: Cooling | Active cooling function |
| Function: Free cooling | Free cooling active |
| Function: Heating | Active heating function |
| Function: Defrosting | Defrosting active |
| Function: Heat recovery | Heat recovery active |
| Function: Cooling recovery | Cooling recovery active |
| Function: Moisture transfer | Moisture transfer active |
| Function: Secondary air | Secondary air mode active |
| Function: Vacuum cleaner | Vacuum cleaner mode active |
| Function: Cooker hood | Cooker hood mode active |
| Function: User lock | User lock active |
| Function: ECO mode active | ECO mode function active |
| Function: Heater cool down | Heater cool down active |
| Function: Pressure guard | Pressure guard active |
| Function: Configurable DI1 | Configurable digital input 1 |
| Function: Configurable DI2 | Configurable digital input 2 |
| Function: Configurable DI3 | Configurable digital input 3 |
| Function: Cooker hood (DI) | Cooker hood digital input sensor |
| Function: Vacuum cleaner (DI) | Vacuum cleaner digital input sensor |

**Heater/Cooler sensors** (2, device class: `running`, unavailable on cloud):

| Entity | Description |
|---|---|
| Heater active | Whether the heater is currently running |
| Cooler active | Whether the cooler is currently running |

### Number Entities (21)

#### Fan Level Sliders (16)

Per-mode fan level sliders for configuring airflow levels. All use slider mode with step 1. Disabled by default. On cloud connections, these are **read-only** (writes raise an error).

| Entity | Mode | Air | Min | Max |
|---|---|---|---|---|
| Crowded supply fan level | Crowded | Supply | 3 | 5 |
| Crowded extract fan level | Crowded | Extract | 3 | 5 |
| Refresh supply fan level | Refresh | Supply | 3 | 5 |
| Refresh extract fan level | Refresh | Extract | 3 | 5 |
| Fireplace supply fan level | Fireplace | Supply | 3 | 5 |
| Fireplace extract fan level | Fireplace | Extract | 1 | 3 |
| Away supply fan level | Away | Supply | 0 | 3 |
| Away extract fan level | Away | Extract | 0 | 3 |
| Holiday supply fan level | Holiday | Supply | 0 | 3 |
| Holiday extract fan level | Holiday | Extract | 0 | 3 |
| Cooker hood supply fan level | Cooker Hood | Supply | 1 | 5 |
| Cooker hood extract fan level | Cooker Hood | Extract | 1 | 5 |
| Vacuum cleaner supply fan level | Vacuum Cleaner | Supply | 1 | 5 |
| Vacuum cleaner extract fan level | Vacuum Cleaner | Extract | 1 | 5 |
| Pressure guard supply fan level | Pressure Guard | Supply | 0 | 5 |
| Pressure guard extract fan level | Pressure Guard | Extract | 0 | 5 |

#### Timed Mode Durations (5)

Number entities for configuring the default duration for each timed mode. Use box input mode with step 1. Disabled by default.

| Entity | Mode | Unit | Min | Max |
|---|---|---|---|---|
| Holiday mode duration | Holiday | days | 1 | 365 |
| Away mode duration | Away | hours | 1 | 72 |
| Fireplace mode duration | Fireplace | minutes | 1 | 60 |
| Refresh mode duration | Refresh | minutes | 1 | 240 |
| Crowded mode duration | Crowded | hours | 1 | 8 |

### Switches (2)

| Entity | Description |
|---|---|
| ECO mode | Toggle energy-saving ECO mode on/off |
| Moisture transfer | Toggle moisture transfer on/off (only relevant for rotating heat exchangers, disabled by default) |

### Select

| Entity | Options | Description |
|---|---|---|
| User mode | Auto, Manual | Switch between Auto and Manual user modes |

When a timed mode is active (Away, Crowded, etc.), the select shows no current option. Use [preset modes](#climate) on the climate entity or [services](#services) to activate timed modes.

## Services

The integration registers services for activating timed ventilation modes. Each service requires a target climate entity and a duration.

| Service | Duration Unit | Range | Description |
|---|---|---|---|
| `systemair.set_away_mode` | hours | 1--72 | Low ventilation while away |
| `systemair.set_crowded_mode` | hours | 1--8 | Increased ventilation for gatherings |
| `systemair.set_fireplace_mode` | minutes | 1--60 | Adjusted airflow for fireplace use |
| `systemair.set_holiday_mode` | days | 1--365 | Minimal ventilation during extended absence |
| `systemair.set_refresh_mode` | minutes | 1--240 | Maximum ventilation for quick air refresh |

### Service call example

```yaml
service: systemair.set_away_mode
data:
  entity_id: climate.systemair_cloud_my_unit
  duration: 24
```

### Automation example

```yaml
automation:
  - alias: "Activate away mode when nobody is home"
    trigger:
      - platform: state
        entity_id: group.family
        to: "not_home"
        for: "00:15:00"
    action:
      - service: systemair.set_away_mode
        data:
          entity_id: climate.systemair_cloud_my_unit
          duration: 48
```

## Options

After initial setup, you can reconfigure the poll interval:

1. Go to **Settings > Devices & Services**
2. Find the Systemair integration entry
3. Click **Configure**
4. Adjust the poll interval (10--300 seconds)
5. The new interval takes effect immediately without restart

## Diagnostics

The integration supports Home Assistant's diagnostics feature for troubleshooting.

1. Go to **Settings > Devices & Services**
2. Find the Systemair integration entry
3. Click the three dots menu and select **Download diagnostics**

The diagnostics file includes:
- Config entry data (with email and password **automatically redacted**)
- Connection type and poll count
- Last update success status
- All current sensor values (temperatures, humidity, fan speeds, mode, etc.)
- Heater/cooler output and status, heat exchanger info, moisture transfer setting
- Per-mode fan levels and timed mode durations
- Active alarms and functions

### Cloud raw data (developer diagnostics)

For cloud connections, the diagnostics download also includes a `cloud_raw_data` section containing comprehensive raw data from the Systemair cloud API. This is designed to help developers implement support for other Systemair device types and models.

The raw data section includes:
- **Account devices** — full `GetAccountDevices` response (identifier, name, deviceType, connection status, model, unit preferences)
- **Export data items** — full `ExportDataItems` dump (version, type, all data item IDs with their Modbus register mappings)
- **Device status** — raw `GetDeviceStatus` response (connectivity, alarms, temperature, airflow, humidity, CO2, filter expiration)
- **Active alarms** — raw `GetActiveAlarms` response
- **Filter information** — raw `GetFilterInformation` response (selected filter, item number)
- **All data item values** — values read for every data item ID discovered via ExportDataItems (batched in groups of 100)
- **Sensor data item values** — values for INPUT register items from `CLOUD_SENSOR_DATA_ITEMS`

Each data source is collected independently — if one query fails, the others still succeed. Failures are captured as error strings. Serial numbers are automatically redacted.

## Architecture

```
custom_components/systemair/
├── __init__.py          # Integration setup, service registration, options listener
├── config_flow.py       # Config flow + options flow
├── const.py             # Constants, register definitions, mode mappings
├── coordinator.py       # DataUpdateCoordinator with unified data model
├── cloud_api.py         # Cloud WebSocket + GraphQL client
├── climate.py           # Climate entity
├── sensor.py            # 21 sensor entities
├── binary_sensor.py     # 39 alarm & function binary sensors
├── switch.py            # ECO mode + moisture transfer switches
├── select.py            # User mode select
├── number.py            # 21 number entities (fan levels + timed mode durations)
├── diagnostics.py       # Diagnostic data export
├── manifest.json        # Integration metadata
├── hacs.json            # HACS metadata
├── services.yaml        # Service definitions
├── strings.json         # UI strings (translation source)
└── translations/
    ├── en.json          # English translations
    └── nb.json          # Norwegian Bokmal translations
```

### Data flow

```
[Systemair HVAC Unit]
        │
        └── Cloud WebSocket + GraphQL ──► cloud_api.py
                                              │
                                        coordinator.py
                                        (DataUpdateCoordinator)
                                        Polls every 20s (default)
                                        + WebSocket push updates
                                        Parses into SystemairData
                                              │
              ┌─────────┬───────────┬─────────┼──────────┬──────────┬──────────┐
          climate.py  sensor.py  binary_   switch.py  select.py  number.py
                                 sensor.py
```

### Key design decisions

- **Unified data model**: The `SystemairData` dataclass provides a connection-agnostic view for all entity platforms.
- **Cloud API**: Authenticates via GraphQL, reads/writes via data item IDs mapped to Modbus register numbers, and receives real-time updates via WebSocket.
- **Register-based interface**: The cloud API's data items map to Modbus register numbers, allowing the same register definitions to be used for both data reading and parsing.
- **Temperature scaling**: Register values use a scale factor of 10 (e.g., register value 210 = 21.0 C). The coordinator handles this conversion.
- **WebSocket push + polling**: WebSocket provides real-time updates for key fields (temperature, humidity, mode), while periodic polling ensures all data stays current.

## Development

### Prerequisites

- Python 3.12+
- A virtual environment (recommended)

### Setup

```bash
# Clone the repository
git clone https://github.com/sirkro/hass-systemair-hvac.git
cd hass-systemair-hvac

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install test dependencies
pip install pytest pytest-asyncio pytest-cov aiohttp voluptuous
```

### Running tests

The test suite has **541 tests** across 11 test files. Tests mock the `homeassistant` package via a root `conftest.py` so they can run without Home Assistant installed.

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=custom_components.systemair --cov-report=term-missing

# Run a specific test file
pytest tests/test_climate.py

# Run a specific test
pytest tests/test_climate.py::TestPresetModes::test_preset_mode_auto_returns_none
```

### Test structure

```
conftest.py              # Root conftest: mocks homeassistant package in sys.modules
tests/
├── conftest.py          # Shared fixtures (MockConfigEntry, mock API factories)
├── test_cloud_api.py    # 77 tests - Cloud WebSocket + GraphQL client
├── test_coordinator.py  # 155 tests - DataUpdateCoordinator
├── test_climate.py      # 52 tests - Climate entity
├── test_sensor.py       # 46 tests - Sensor entities
├── test_binary_sensor.py    # 40 tests - Binary sensor entities
├── test_number.py       # 41 tests - Number entities (fan levels + durations)
├── test_init.py         # 15 tests - Integration setup
├── test_config_flow.py  # 39 tests - Config flow + options flow
├── test_select.py       # 12 tests - User mode select
├── test_switch.py       # 14 tests - ECO mode + moisture transfer switches
└── test_diagnostics.py  # 14 tests - Diagnostics + cloud raw data
```

### Utility scripts

The repo root contains utility scripts for API exploration and testing. These require environment variables:

```bash
export SYSTEMAIR_EMAIL="your@email.com"
export SYSTEMAIR_PASSWORD="your_password"
export SYSTEMAIR_DEVICE_ID="IAM_XXXXXXXXXXXX"
```

### Testing with a real Home Assistant instance

Use Docker to run a Home Assistant instance with this integration:

```bash
# Run Home Assistant with the integration mounted
docker run -d \
  --name homeassistant \
  -p 8123:8123 \
  -v "$(pwd)/custom_components:/config/custom_components" \
  ghcr.io/home-assistant/home-assistant:stable

# View logs
docker logs -f homeassistant

# Stop and remove
docker stop homeassistant && docker rm homeassistant
```

Then open http://localhost:8123 and add the Systemair integration via the UI.

## Troubleshooting

### Connection issues

- Verify your credentials at https://homesolutions.systemair.com
- Check that the unit appears in the cloud portal's device list
- Cloud connections require internet access from the Home Assistant host
- If authentication fails repeatedly, the integration uses exponential backoff (up to 5 minutes between retries)

### Entity shows "unavailable"

- Check the Home Assistant logs for error messages from the `systemair` integration
- Download diagnostics to see the last known state and error information
- Try reloading the integration (Settings > Devices & Services > Systemair > three dots > Reload)
- Heater/cooler output sensors and heater/cooler active binary sensors are always unavailable on cloud connections (underlying registers not exposed by the cloud API)

### Temperature values seem wrong

- Verify the unit is reporting temperatures (check diagnostics output)
- Modbus temperature registers use a scale factor of 10 (value 210 = 21.0 C)
- Negative temperatures use signed 16-bit values (values > 32768 are negative)

### Filter days showing incorrect value

- Filter time is stored as seconds in two 16-bit registers (low/high)
- The integration converts this to days by dividing total seconds by 86400

### Debug Logging

To enable detailed debug logging for troubleshooting or feature requests:

1. Add to your `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.systemair: debug
   ```

2. Restart Home Assistant

3. Reproduce the issue

4. Check the Home Assistant logs (Settings > System > Logs) or view the log file at `config/home-assistant.log`

5. When reporting issues, please include:
   - Debug logs showing the issue
   - Diagnostics download (Settings > Devices & Services > Systemair > Download diagnostics)
   - Your device model and firmware version

## Acknowledgements

This integration is based on the [Systemair Homey app](https://github.com/balmli/com.systemair) by [balmli](https://github.com/balmli), licensed under GPL-3.0. The register definitions, cloud API protocol, and overall device communication logic were ported from that project.

Additional thanks to [python-systemair-savecair](https://github.com/perara/python-systemair-savecair) for early work on Systemair IAM communication.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) -- the same license as the original Homey app it is derived from.

## Disclaimer

Use at your own risk. The authors accept no responsibility for any damages caused by using this integration.
