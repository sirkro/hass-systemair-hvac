"""Find remaining data item IDs not in ExportDataItems, and fix queries that need subfields."""
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
REMOTE_API_URL = "https://homesolutions.systemair.com/gateway/remote-api"
GATEWAY_API_URL = "https://homesolutions.systemair.com/gateway/api"


async def gql(session, headers, url, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(url, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60)) as resp:
        return resp.status, await resp.text()


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
        remote_headers = {**base_headers, "device-id": DEVICE_ID, "device-type": "LEGACY"}

        # ─── 1. Introspect types we need subfields for ───
        print("\n=== Introspect needed types ===")
        for tn in ["GraphqlProxyViewElement", "GraphqlProxyViewProtection",
                    "ActiveAlarm", "DeviceStatusUnits",
                    "TranslationVariables", "UnitMonitoringDataItemsInput",
                    "UnitMonitoringDataItemsOutput"]:
            # Try both remote-api and gateway-api
            for label, url in [("remote", REMOTE_API_URL), ("gateway", GATEWAY_API_URL)]:
                status, body = await gql(session, base_headers if url == GATEWAY_API_URL else remote_headers, url, """
                {
                  __type(name: "%s") {
                    name kind
                    fields { name type { name kind ofType { name kind ofType { name kind } } } }
                    inputFields { name type { name kind ofType { name kind ofType { name kind } } } }
                  }
                }
                """ % tn)
                data = json.loads(body)
                t = data.get("data", {}).get("__type")
                if t:
                    print(f"\n  {tn} ({t.get('kind')}) on {label}:")
                    for f in (t.get("fields") or t.get("inputFields") or []):
                        ft = f["type"]
                        tn2 = ft.get("name")
                        if not tn2:
                            inner = ft.get("ofType", {})
                            inner2 = inner.get("ofType", {})
                            tn2 = f"{ft.get('kind')}({inner.get('name') or inner.get('kind') + '(' + str(inner2.get('name')) + ')'})"
                        print(f"    {f['name']}: {tn2}")
                    break  # found it

        # ─── 2. GetView with proper subfields ───
        print("\n\n=== GetView /device/home with children subfields ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            id
            title
            route
            customComponentName
            error
            protection { enabled type }
            translationVariables { key value }
            children {
              id
              type
              title
              dataItem
              icon
              visible
              route
              disabled
              children {
                id
                type
                title
                dataItem
                icon
                visible
                route
                disabled
              }
            }
          }
        }
        """, variables={"input": {"route": "/device/home"}})
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:3], indent=2)}")
        view = data.get("data", {}).get("GetView")
        if view:
            with open("view_device_home_full.json", "w") as f:
                json.dump(view, f, indent=2)
            print(f"Saved to view_device_home_full.json")
            print(f"  route: {view.get('route')}")
            print(f"  title: {view.get('title')}")
            children = view.get("children", [])
            print(f"  children: {len(children)} items")
            for i, child in enumerate(children[:10]):
                print(f"    [{i}] type={child.get('type')}, title={child.get('title')}, dataItem={child.get('dataItem')}, id={child.get('id')}")
                for j, subchild in enumerate((child.get("children") or [])[:5]):
                    print(f"      [{j}] type={subchild.get('type')}, title={subchild.get('title')}, dataItem={subchild.get('dataItem')}, id={subchild.get('id')}")

        # ─── 3. GetActiveAlarms with subfields ───
        print("\n\n=== GetActiveAlarms with subfields ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          GetActiveAlarms {
            alarms {
              id
              type
              date
              description
            }
          }
        }
        """)
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            # Try without subfields on alarms in case it's a scalar list
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
            # Try introspecting ActiveAlarm to find actual fields
        result = data.get("data", {}).get("GetActiveAlarms")
        if result:
            print(json.dumps(result, indent=2)[:2000])

        # ─── 4. GetAccountDevices without units ───
        print("\n\n=== GetAccountDevices (fixed) ===")
        status, body = await gql(session, base_headers, GATEWAY_API_URL, """
        {
          GetAccountDevices {
            identifier
            name
            street
            zipcode
            city
            country
            deviceType { entry module scope type }
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
              units { temperature airflow pressure }
            }
          }
        }
        """)
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
        devices = data.get("data", {}).get("GetAccountDevices")
        if devices:
            print(json.dumps(devices, indent=2))

        # ─── 5. Search for read-only sensor items via GetDataItems ───
        # The IDs from ExportDataItems only show exportable/writable items.
        # Read-only sensor items (SAT, OAT, etc.) have their own IDs.
        # From the IAM device type 2 items we saw (id 1-10), internalDeviceType 2 = IAM module
        # Let's scan a wider range to find sensor items
        print("\n\n=== Scanning for sensor data items (IDs 100-500) ===")
        # Batch request
        all_ids = list(range(100, 501))
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        query ($input: [Int]) {
          GetDataItems(input: $input)
        }
        """, variables={"input": all_ids})
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {data['errors'][0].get('message', '')[:200]}")
        items_result = data.get("data", {}).get("GetDataItems")
        if items_result:
            if isinstance(items_result, str):
                items_result = json.loads(items_result)
            if isinstance(items_result, list):
                # Find read-only items (sensors)
                sensors = [i for i in items_result if i.get("readOnly")]
                print(f"  Found {len(items_result)} items total, {len(sensors)} read-only")
                for s in sensors:
                    ext = s.get("extension", {})
                    mb = ext.get("modbusRegister", "?")
                    print(f"    ID {s['id']:4d} -> Modbus {str(mb):>6s} = {str(s.get('value')):>10s} [RO]")

        # ─── 6. Scan higher ranges for sensor registers ───
        print("\n\n=== Scanning for sensor data items (IDs 500-1200) ===")
        all_ids = list(range(500, 1201))
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        query ($input: [Int]) {
          GetDataItems(input: $input)
        }
        """, variables={"input": all_ids})
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {data['errors'][0].get('message', '')[:200]}")
        items_result = data.get("data", {}).get("GetDataItems")
        if items_result:
            if isinstance(items_result, str):
                items_result = json.loads(items_result)
            if isinstance(items_result, list):
                sensors = [i for i in items_result if i.get("readOnly")]
                print(f"  Found {len(items_result)} items total, {len(sensors)} read-only")
                for s in sensors:
                    ext = s.get("extension", {})
                    mb = ext.get("modbusRegister", "?")
                    print(f"    ID {s['id']:4d} -> Modbus {str(mb):>6s} = {str(s.get('value')):>10s} [RO]")

        # Also scan writable items with important modbus registers in this range
        print("\n  All items with interesting Modbus registers (1100-1200, 7100-7200, 12000+):")
        if isinstance(items_result, list):
            for i in items_result:
                ext = i.get("extension", {})
                mb = ext.get("modbusRegister")
                if mb and (1100 <= mb <= 1200 or 7000 <= mb <= 7200 or mb >= 12000):
                    print(f"    ID {i['id']:4d} -> Modbus {mb:>6d} = {str(i.get('value')):>10s} [{'RO' if i.get('readOnly') else 'RW'}]")

        # ─── 7. Try GetUnitMonitoringDataItems ───
        print("\n\n=== GetUnitMonitoringDataItems ===")
        # First introspect the input type
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          __type(name: "UnitMonitoringDataItemsInput") {
            name kind
            inputFields { name type { name kind ofType { name kind } } }
          }
        }
        """)
        data = json.loads(body)
        t = data.get("data", {}).get("__type")
        if t:
            print(f"  Input type fields:")
            for f in (t.get("inputFields") or []):
                ft = f["type"]
                print(f"    {f['name']}: {ft.get('name') or ft.get('kind')}")
        
        # Try calling it
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        query {
          GetUnitMonitoringDataItems(input: {register: [12101, 12102, 12543, 12135, 12400, 12401, 12350, 12351, 12544, 1160, 1162, 7100, 7101, 12300, 12301, 12302, 12303]}) {
            register
            value
          }
        }
        """)
        print(f"\n  GetUnitMonitoringDataItems HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"  Errors: {json.dumps(data['errors'][:2], indent=2)}")
        result = data.get("data", {}).get("GetUnitMonitoringDataItems")
        if result:
            print(f"  Got {len(result)} items:")
            for item in result:
                print(f"    Register {item['register']}: {item['value']}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
