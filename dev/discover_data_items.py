"""Discover data item IDs from the Systemair cloud API.

Runs ExportDataItems, GetView, and GetDeviceStatus to map out
all available registers and their IDs.
"""
import asyncio
import json
import os
import importlib.util

import aiohttp

spec = importlib.util.spec_from_file_location(
    "cloud_api",
    os.path.join(os.path.dirname(__file__), "custom_components", "systemair", "cloud_api.py")
)
cloud_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_api_mod)
SystemairCloudAPI = cloud_api_mod.SystemairCloudAPI

DEVICE_ID = os.environ["SYSTEMAIR_DEVICE_ID"]
GATEWAY_API_URL = "https://homesolutions.systemair.com/gateway/api"
REMOTE_API_URL = "https://homesolutions.systemair.com/gateway/remote-api"


async def gql(session, headers, url, query, variables=None):
    """Execute a GraphQL query."""
    payload = {"query": query, "variables": variables or {}}
    async with session.post(
        url, json=payload, headers=headers,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as resp:
        text = await resp.text()
        return resp.status, text


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]

    api = SystemairCloudAPI(email=email, password=password)

    try:
        await api.login()
        print("Login OK")
        session = api._get_session()

        base_headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }

        remote_headers = {
            **base_headers,
            "device-id": DEVICE_ID,
            "device-type": "LEGACY",
        }

        # ─── 1. ExportDataItems (remote-api) ───
        print("\n" + "=" * 60)
        print("1. ExportDataItems")
        print("=" * 60)
        # ExportOutput has fields: version, type, dataItems
        # dataItems might be a scalar (serialized JSON)
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          ExportDataItems {
            version
            type
            dataItems
          }
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {json.dumps(data['errors'], indent=2)}")
            export = data.get("data", {}).get("ExportDataItems")
            if export:
                print(f"  version: {export.get('version')}")
                print(f"  type: {export.get('type')}")
                data_items = export.get("dataItems")
                if isinstance(data_items, str):
                    try:
                        parsed = json.loads(data_items)
                        print(f"  dataItems: {len(parsed)} items (parsed from JSON string)")
                        # Save full export to file
                        with open("export_data_items.json", "w") as f:
                            json.dump(parsed, f, indent=2)
                        print("  Saved to export_data_items.json")
                        # Show first 20 items
                        for i, item in enumerate(parsed[:20]):
                            print(f"    [{i}] {item}")
                        if len(parsed) > 20:
                            print(f"    ... and {len(parsed) - 20} more")
                    except json.JSONDecodeError:
                        print(f"  dataItems (raw string, first 3000 chars): {data_items[:3000]}")
                        with open("export_data_items_raw.txt", "w") as f:
                            f.write(data_items)
                        print("  Saved raw to export_data_items_raw.txt")
                elif isinstance(data_items, list):
                    print(f"  dataItems: {len(data_items)} items (list)")
                    with open("export_data_items.json", "w") as f:
                        json.dump(data_items, f, indent=2)
                    print("  Saved to export_data_items.json")
                    for i, item in enumerate(data_items[:20]):
                        print(f"    [{i}] {item}")
                else:
                    print(f"  dataItems type={type(data_items)}: {str(data_items)[:2000]}")
            else:
                print(f"  No ExportDataItems in response")
                print(body[:3000])
        except json.JSONDecodeError:
            print(f"Not JSON: {body[:3000]}")

        # ─── 2. ExportDataItems without subfields (maybe it's just a scalar) ───
        print("\n" + "=" * 60)
        print("2. ExportDataItems (as scalar, no subfields)")
        print("=" * 60)
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          ExportDataItems
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                # If it says subfields required, then it's not a scalar
                print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
            else:
                result = data.get("data", {}).get("ExportDataItems")
                print(f"Result type: {type(result)}")
                print(f"Result: {str(result)[:3000]}")
        except json.JSONDecodeError:
            print(f"Not JSON: {body[:3000]}")

        # ─── 3. GetDataItems with some common register IDs ───
        print("\n" + "=" * 60)
        print("3. GetDataItems with various IDs")
        print("=" * 60)
        # Try small IDs (1-10), since we know 2000 doesn't work
        for test_ids in [[1, 2, 3, 4, 5], [10, 20, 50, 100], [200, 300, 400, 500]]:
            status, body = await gql(session, remote_headers, REMOTE_API_URL, """
            query ($input: [Int]) {
              GetDataItems(input: $input)
            }
            """, variables={"input": test_ids})
            print(f"\n  IDs {test_ids}: HTTP {status}")
            try:
                data = json.loads(body)
                if data.get("errors"):
                    print(f"  Error: {data['errors'][0].get('message', '')[:200]}")
                else:
                    result = data.get("data", {}).get("GetDataItems")
                    if result:
                        if isinstance(result, str):
                            try:
                                parsed = json.loads(result)
                                print(f"  Result (parsed): {json.dumps(parsed, indent=2)[:500]}")
                            except:
                                print(f"  Result (raw): {result[:500]}")
                        else:
                            print(f"  Result: {str(result)[:500]}")
                    else:
                        print(f"  Result: None/empty")
            except json.JSONDecodeError:
                print(f"  Not JSON: {body[:500]}")

        # ─── 4. GetDeviceStatus ───
        print("\n" + "=" * 60)
        print("4. GetDeviceStatus")
        print("=" * 60)
        # From introspection: GraphqlProxyDeviceStatusOutput fields
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
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
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {json.dumps(data['errors'], indent=2)}")
            result = data.get("data", {}).get("GetDeviceStatus")
            if result:
                print(json.dumps(result, indent=2))
        except json.JSONDecodeError:
            print(f"Not JSON: {body[:2000]}")

        # ─── 5. GetView for various routes ───
        print("\n" + "=" * 60)
        print("5. GetView for various routes")
        print("=" * 60)
        
        # First, introspect GraphqlProxyView to know available fields
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          __type(name: "GraphqlProxyView") {
            name kind
            fields {
              name
              type { name kind ofType { name kind ofType { name kind } } }
            }
          }
        }
        """)
        print(f"GraphqlProxyView type info: HTTP {status}")
        try:
            data = json.loads(body)
            t = data.get("data", {}).get("__type")
            if t:
                for f in (t.get("fields") or []):
                    ft = f["type"]
                    type_name = ft.get("name") or f"{ft.get('kind')}({ft.get('ofType', {}).get('name')})"
                    print(f"  {f['name']}: {type_name}")
        except:
            print(body[:1000])

        # Now try GetView with the fields we know
        for route in ["/device/home", "/device/home/changeMode", "/device/home/temperature"]:
            status, body = await gql(session, remote_headers, REMOTE_API_URL, """
            query ($input: GetViewInputType!) {
              GetView(input: $input) {
                id
                title
                route
                customComponentName
                protection
                children
                translationVariables
                error
              }
            }
            """, variables={"input": {"route": route}})
            print(f"\n  Route '{route}': HTTP {status}")
            try:
                data = json.loads(body)
                if data.get("errors"):
                    print(f"  Errors: {json.dumps(data['errors'][:2], indent=2)[:500]}")
                view = data.get("data", {}).get("GetView")
                if view:
                    print(f"  id: {view.get('id')}")
                    print(f"  title: {view.get('title')}")
                    print(f"  route: {view.get('route')}")
                    print(f"  customComponentName: {view.get('customComponentName')}")
                    print(f"  protection: {view.get('protection')}")
                    print(f"  error: {view.get('error')}")
                    
                    children = view.get("children")
                    if isinstance(children, str):
                        try:
                            parsed = json.loads(children)
                            # Save to file for analysis
                            safe_route = route.replace("/", "_").strip("_")
                            with open(f"view_{safe_route}.json", "w") as f:
                                json.dump(parsed, f, indent=2)
                            print(f"  children: {len(parsed)} items (saved to view_{safe_route}.json)")
                            # Show structure of first few items
                            for i, child in enumerate(parsed[:5]):
                                print(f"    [{i}] {json.dumps(child)[:200]}")
                            if len(parsed) > 5:
                                print(f"    ... and {len(parsed) - 5} more")
                        except json.JSONDecodeError:
                            print(f"  children (raw): {children[:1000]}")
                    elif children is not None:
                        print(f"  children type={type(children)}: {str(children)[:1000]}")
                    
                    tv = view.get("translationVariables")
                    if tv:
                        if isinstance(tv, str):
                            print(f"  translationVariables: {tv[:500]}")
                        else:
                            print(f"  translationVariables: {str(tv)[:500]}")
            except json.JSONDecodeError:
                print(f"  Not JSON: {body[:1000]}")

        # ─── 6. GetAccountDevices (gateway-api) ───
        print("\n" + "=" * 60)
        print("6. GetAccountDevices (gateway-api)")
        print("=" * 60)
        status, body = await gql(session, base_headers, GATEWAY_API_URL, """
        {
          GetAccountDevices {
            identifier
            name
            street
            zipcode
            city
            country
            deviceType {
              entry
              module
              scope
              type
            }
            status {
              connectionStatus
              serialNumber
              model
              startupWizardRequired
              updateInProgress
              filterLocked
              weekScheduleLocked
              serviceLocked
              hasAlarms
              units
            }
          }
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {json.dumps(data['errors'], indent=2)}")
            devices = data.get("data", {}).get("GetAccountDevices")
            if devices:
                print(json.dumps(devices, indent=2))
        except json.JSONDecodeError:
            print(f"Not JSON: {body[:2000]}")

        # ─── 7. GetFilterInformation (remote-api) ───
        print("\n" + "=" * 60)
        print("7. GetFilterInformation")
        print("=" * 60)
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          GetFilterInformation {
            selectedFilter
            itemNumber
          }
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {json.dumps(data['errors'], indent=2)}")
            result = data.get("data", {}).get("GetFilterInformation")
            if result:
                print(json.dumps(result, indent=2))
        except:
            print(body[:1000])

        # ─── 8. GetActiveAlarms (remote-api) ───
        print("\n" + "=" * 60)
        print("8. GetActiveAlarms")
        print("=" * 60)
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          GetActiveAlarms {
            alarms
          }
        }
        """)
        print(f"HTTP {status}")
        try:
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {json.dumps(data['errors'], indent=2)}")
            result = data.get("data", {}).get("GetActiveAlarms")
            if result:
                print(json.dumps(result, indent=2))
        except:
            print(body[:1000])

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
