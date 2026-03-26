# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.3] - 2026-03-26

### Added

- Lovelace card (`lovelace/systemair-card.js`) with entity registry-based lookups (language-independent)
- Lovelace card screenshot and usage documentation (`lovelace/README.md`)

### Fixed

- Lovelace card: entity lookups now use `hass.entities` registry (translation_key + device_id) instead of English slug guessing
- Lovelace card: timed-mode services (e.g. `set_away_mode`) now send correct `entity_id` and `duration` parameters
- Lovelace card: replaced `none` preset chip with Auto/Manual HVAC mode chips
- Lovelace card: function/alarm friendly name stripping correctly handles device name prefix added by `_attr_has_entity_name = True`

## [0.9.2] - 2026-03-18

### Added

- GitHub Actions workflows for automated testing (pytest on Python 3.11 & 3.12) and HACS/Hassfest validation
- Official Systemair brand assets (icon.png, logo.png) for HACS integration

### Fixed

- Test suite compatibility with GitHub Actions CI environment
- MockCoordinator test helpers now include last_update_success attribute

### Changed

- Prepared integration for HACS default repository inclusion
- Updated hacs.json to remove invalid keys (domains, iot_class belong in manifest.json only)

## [0.9.1] - 2026-03-18

### Fixed

- User Mode entity now displays correctly on all cloud API versions by reading from data item 29 instead of relying on enhanced GetDeviceStatus query

## [0.9.0] - 2026-03-18

### Initial Beta Release

Custom Home Assistant integration for Systemair HVAC ventilation units via the Systemair Cloud (WebSocket + GraphQL).

#### Features

- **Climate entity** with temperature control, fan speed control (low/medium/high), HVAC mode (auto/fan_only), and preset modes (away, boost, comfort, fireplace, holiday)
- **21 sensor entities** covering temperatures, humidity, CO2, air quality, fan RPM/speed, filter life, and mode information
- **39 binary sensors** for alarm states (18), active functions (19), and heater/cooler status (2)
- **21 number entities** for per-mode fan level configuration (16) and timed mode durations (5)
- **2 switches** for ECO mode and moisture transfer control
- **1 select entity** for user mode switching (Auto/Manual)
- **5 timed mode services** to activate Away, Crowded, Fireplace, Holiday, or Refresh modes
- **Real-time WebSocket updates** between polling intervals
- **Config flow** with connection testing
- **Options flow** for reconfiguring poll interval
- **Diagnostics support** with automatic credential redaction
- **Developer diagnostics** with comprehensive cloud API raw data
- **Translations** in English and Norwegian Bokmål

#### Supported Hardware

- Systemair SAVE ventilation units registered in the Systemair Home Solutions cloud portal
- Tested with SAVE VTR series units
- Requires Systemair Home Solutions account (https://homesolutions.systemair.com)

#### Technical Details

- **541 test cases** with comprehensive coverage
- Cloud-only connection mode via GraphQL + WebSocket
- Auto-discovery of 312+ data item IDs with Modbus register mapping
- Exponential backoff for authentication retries
- Automatic token refresh
- WebSocket reconnection with connection state tracking
- Boolean values for cloud writes use `"true"`/`"false"` format (matches official Systemair web UI)

#### Known Limitations

- Cloud-only (Modbus TCP and Save Connect not implemented)
- Heater/cooler output sensors unavailable via cloud API
- Fan level configuration number entities are read-only on cloud connections

#### Acknowledgements

Based on the [Systemair Homey app](https://github.com/balmli/com.systemair) by [balmli](https://github.com/balmli), licensed under GPL-3.0.

[0.9.3]: https://github.com/sirkro/hass-systemair-hvac/releases/tag/v0.9.3
[0.9.2]: https://github.com/sirkro/hass-systemair-hvac/releases/tag/v0.9.2
[0.9.1]: https://github.com/sirkro/hass-systemair-hvac/releases/tag/v0.9.1
[0.9.0]: https://github.com/sirkro/hass-systemair-hvac/releases/tag/v0.9.0
