# Development Scripts

This directory contains utility scripts and data files used during development and API exploration. These are not required for the integration to function.

## Scripts

### API Introspection
- `introspect_api*.py` - Scripts for exploring the Systemair cloud API structure and capabilities
- `discover_data_items*.py` - Scripts for discovering data item ID to Modbus register mappings
- `find_sensor_ids*.py` - Scripts for identifying sensor register IDs

### Testing
- `test_monitoring_query*.py` - Scripts for testing WebSocket monitoring and GraphQL queries
- `mock_server.py` - Mock server for local testing without cloud access
- `scan_all_ids.py` - Script to scan all possible data item IDs

## Data Files

- `export_data_items.json` - Sample ExportDataItems response from the cloud API
- `all_known_data_items.json` - Comprehensive list of discovered data items
- `all_valid_data_items_scan.json` - Results from scanning all data item IDs
- `view_*.json` - Sample responses from various cloud API queries

## Usage

These scripts require environment variables to be set:

```bash
export SYSTEMAIR_EMAIL="your@email.com"
export SYSTEMAIR_PASSWORD="your_password"
export SYSTEMAIR_DEVICE_ID="IAM_XXXXXXXXXXXX"
```

Then run any script:

```bash
python dev/introspect_api.py
```

## Note

These files are kept for future development and troubleshooting purposes. They may become outdated as the cloud API evolves.
