"""Final discovery: GetView with correct fields, GetUnitMonitoringDataItems, and GetAccountDevices."""
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
        base_headers = {"x-access-token": api._access_token, "content-type": "application/json"}
        remote_headers = {**base_headers, "device-id": DEVICE_ID, "device-type": "LEGACY"}

        # ─── 1. Introspect ViewElementProperties ───
        print("\n=== ViewElementProperties ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          __type(name: "ViewElementProperties") {
            name kind
            fields { name type { name kind ofType { name kind ofType { name kind } } } }
            inputFields { name type { name kind ofType { name kind ofType { name kind } } } }
          }
        }
        """)
        data = json.loads(body)
        t = data.get("data", {}).get("__type")
        if t:
            print(f"  {t['name']} ({t.get('kind')}):")
            for f in (t.get("fields") or t.get("inputFields") or []):
                ft = f["type"]
                tn = ft.get("name")
                if not tn:
                    inner = ft.get("ofType", {})
                    tn = f"{ft.get('kind')}({inner.get('name')})"
                print(f"    {f['name']}: {tn}")

        # ─── 2. GetView /device/home with correct element fields ───
        print("\n\n=== GetView /device/home ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            id
            title
            route
            customComponentName
            error
            translationVariables
            protection { type securityLevel }
            children {
              type
              feature
              properties
              children {
                type
                feature
                properties
                children {
                  type
                  feature
                  properties
                }
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
            with open("view_device_home_v2.json", "w") as f:
                json.dump(view, f, indent=2)
            print("Saved to view_device_home_v2.json")
            print(f"  id: {view.get('id')}")
            print(f"  title: {view.get('title')}")
            children = view.get("children", [])
            print(f"  children: {len(children)} items")
            for i, child in enumerate(children[:15]):
                props = child.get("properties")
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        pass
                print(f"    [{i}] type={child.get('type')}, feature={child.get('feature')}, props={json.dumps(props)[:200] if props else 'None'}")

        # ─── 3. GetUnitMonitoringDataItems with route ───
        print("\n\n=== GetUnitMonitoringDataItems ===")
        for route in ["/device/home", "/device/monitoring", "/monitoring", None, ""]:
            status, body = await gql(session, remote_headers, REMOTE_API_URL, """
            query ($input: UnitMonitoringDataItemsInput) {
              GetUnitMonitoringDataItems(input: $input) {
                register
                value
              }
            }
            """, variables={"input": {"route": route} if route else {}})
            print(f"\n  route={route!r}: HTTP {status}")
            data = json.loads(body)
            if data.get("errors"):
                print(f"    Error: {data['errors'][0].get('message', '')[:200]}")
            result = data.get("data", {}).get("GetUnitMonitoringDataItems")
            if result:
                print(f"    Got {len(result)} items:")
                for item in result[:30]:
                    print(f"      Register {item.get('register')}: {item.get('value')}")
                if len(result) > 30:
                    with open(f"monitoring_{(route or 'none').replace('/', '_').strip('_')}.json", "w") as f:
                        json.dump(result, f, indent=2)
                    print(f"    ... {len(result)} total, saved to file")

        # ─── 4. GetAccountDevices (fixed) ───
        print("\n\n=== GetAccountDevices ===")
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
              units { temperature pressure flow }
            }
          }
        }
        """)
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'], indent=2)}")
        devices = data.get("data", {}).get("GetAccountDevices")
        if devices:
            print(json.dumps(devices, indent=2))

        # ─── 5. GetActiveAlarms (fixed) ───
        print("\n\n=== GetActiveAlarms ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          GetActiveAlarms {
            alarms {
              title
              description
              timestamp
              stopping
              acknowledged
            }
          }
        }
        """)
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
        result = data.get("data", {}).get("GetActiveAlarms")
        if result:
            print(json.dumps(result, indent=2))

        # ─── 6. Test WriteDataItems (introspect input type first) ───
        print("\n\n=== WriteDataItems input type ===")
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          __type(name: "WriteDataItemsInput") {
            name kind
            inputFields { name type { name kind ofType { name kind ofType { name kind } } } }
          }
        }
        """)
        data = json.loads(body)
        t = data.get("data", {}).get("__type")
        if t:
            for f in (t.get("inputFields") or []):
                ft = f["type"]
                tn = ft.get("name")
                if not tn:
                    inner = ft.get("ofType", {})
                    inner2 = inner.get("ofType", {})
                    tn = f"{ft.get('kind')}({inner.get('name') or inner.get('kind') + '(' + str(inner2.get('name')) + ')'})"
                print(f"  {f['name']}: {tn}")

        # Introspect DataItemWriteInput
        status, body = await gql(session, remote_headers, REMOTE_API_URL, """
        {
          __type(name: "DataItemWriteInput") {
            name kind
            inputFields { name type { name kind ofType { name kind } } }
          }
        }
        """)
        data = json.loads(body)
        t = data.get("data", {}).get("__type")
        if t:
            print(f"\n  DataItemWriteInput:")
            for f in (t.get("inputFields") or []):
                ft = f["type"]
                tn = ft.get("name") or f"{ft.get('kind')}({ft.get('ofType', {}).get('name')})"
                print(f"    {f['name']}: {tn}")

        # ─── 7. Scan data items in smaller batches (500-800) ───
        print("\n\n=== Scanning data items 500-800 ===")
        for start in range(500, 800, 100):
            ids = list(range(start, start + 100))
            status, body = await gql(session, remote_headers, REMOTE_API_URL, """
            query ($input: [Int]) { GetDataItems(input: $input) }
            """, variables={"input": ids})
            data = json.loads(body)
            if data.get("errors"):
                print(f"  {start}-{start+99}: Error: {data['errors'][0].get('message', '')[:100]}")
                continue
            items = data.get("data", {}).get("GetDataItems")
            if items:
                if isinstance(items, str):
                    items = json.loads(items)
                # Show items with interesting modbus registers
                for item in items:
                    ext = item.get("extension", {})
                    mb = ext.get("modbusRegister", 0)
                    if mb >= 12000 or (1100 <= mb <= 1170) or (7000 <= mb <= 7200):
                        ro = 'RO' if item.get('readOnly') else 'RW'
                        print(f"    ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}]")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
