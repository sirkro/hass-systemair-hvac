"""Round 3: Now that we know data item IDs contain sensor registers, find the exact IDs for our missing sensors."""
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


async def gql(session, headers, url, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(url, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60)) as resp:
        return resp.status, await resp.text()


# Target registers (0-indexed) we're looking for
TARGET_REGISTERS = {
    12101: "REG_SENSOR_OAT",
    12102: "REG_SENSOR_SAT", 
    12107: "REG_SENSOR_OHT",
    12108: "REG_SENSOR_OHT (1-indexed match)",
    12135: "REG_SENSOR_RHS_PDM",
    12400: "REG_SENSOR_RPM_SAF",
    12401: "REG_SENSOR_RPM_EAF",
    12543: "REG_SENSOR_PDM_EAT_VALUE",
    12544: "REG_SENSOR_PDM_EAT_VALUE (1-indexed match)",
    14000: "REG_OUTPUT_SAF",
    14001: "REG_OUTPUT_EAF",
    14100: "REG_OUTPUT_Y1_ANALOG",
    14101: "REG_OUTPUT_Y1_DIGITAL",
    14200: "REG_OUTPUT_Y3_ANALOG",
    14201: "REG_OUTPUT_Y3_DIGITAL",
}


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]

    api = SystemairCloudAPI(email=email, password=password)
    try:
        await api.login()
        print("Login OK\n")
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
            "device-id": DEVICE_ID,
            "device-type": "LEGACY",
        }

        # ─── 1. We know data item ID 54 -> Modbus 12101. Get its full details ───
        print("=" * 70)
        print("1. Get data item ID 54 (OAT sensor) details")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, """
        query ($input: [Int]) { GetDataItems(input: $input) }
        """, variables={"input": [54]})
        data = json.loads(body)
        items = data.get("data", {}).get("GetDataItems")
        if items:
            if isinstance(items, str):
                items = json.loads(items)
            print(json.dumps(items, indent=2))

        # ─── 2. Try GetDataItems with IDs around 54 (50-70) to find nearby sensor IDs ───
        print("\n" + "=" * 70)
        print("2. GetDataItems IDs 40-80 (near ID 54 OAT sensor)")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, """
        query ($input: [Int]) { GetDataItems(input: $input) }
        """, variables={"input": list(range(40, 80))})
        data = json.loads(body)
        items = data.get("data", {}).get("GetDataItems")
        if items:
            if isinstance(items, str):
                items = json.loads(items)
            for item in items:
                ext = item.get("extension", {})
                mb = ext.get("modbusRegister", 0)
                ro = 'RO' if item.get('readOnly') else 'RW'
                name = TARGET_REGISTERS.get(mb, "")
                marker = " <<<" if name else ""
                print(f"  ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}] dec={item.get('decimals')} unit={item.get('unit')}{marker} {name}")

        # ─── 3. Comprehensive scan: ALL data items 0-1200, find ALL sensor registers ───
        print("\n" + "=" * 70)
        print("3. Full scan of data items 0-1200 for sensor/output registers")
        print("=" * 70)
        
        all_sensor_items = []
        for start in range(0, 1201, 100):
            status, body = await gql(session, headers, REMOTE_API_URL, """
            query ($input: [Int]) { GetDataItems(input: $input) }
            """, variables={"input": list(range(start, start + 100))})
            data = json.loads(body)
            if data.get("errors"):
                continue
            items = data.get("data", {}).get("GetDataItems")
            if items:
                if isinstance(items, str):
                    items = json.loads(items)
                for item in items:
                    ext = item.get("extension", {})
                    mb = ext.get("modbusRegister", 0)
                    # Collect items with registers in sensor ranges
                    if mb in TARGET_REGISTERS:
                        all_sensor_items.append(item)
                        ro = 'RO' if item.get('readOnly') else 'RW'
                        print(f"  FOUND: ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}] dec={item.get('decimals')} {TARGET_REGISTERS[mb]}")
        
        if not all_sensor_items:
            print("  No data items found for target registers in 0-1200 range")
        else:
            print(f"\n  Total found: {len(all_sensor_items)} items mapping to target registers")

        # ─── 4. Get service sub-views to find more data items ───
        print("\n" + "=" * 70)
        print("4. GetView service/input and service/output")
        print("=" * 70)
        
        view_query = """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            id title route error
            children { type feature properties }
          }
        }
        """
        
        for route in ["service/input", "service/output"]:
            status, body = await gql(session, headers, REMOTE_API_URL, view_query,
                                     variables={"input": {"route": route}})
            data = json.loads(body)
            if data.get("errors"):
                print(f"\n  route={route}: ERROR — {data['errors'][0].get('message', '')[:150]}")
                continue
            view = data.get("data", {}).get("GetView")
            if view:
                children = view.get("children", [])
                print(f"\n  route={route}: title={view.get('title')}, children={len(children)}")
                for i, child in enumerate(children):
                    props = child.get("properties")
                    if isinstance(props, str):
                        try:
                            props = json.loads(props)
                        except:
                            pass
                    if isinstance(props, dict):
                        di = props.get("dataItem", {})
                        if isinstance(di, dict):
                            mb = di.get("extension", {}).get("modbusRegister", 0)
                            name = TARGET_REGISTERS.get(mb, "")
                            marker = " <<<" if name else ""
                            print(f"    [{i}] ID {di.get('id', '?')} -> Modbus {mb} = {di.get('value')}{marker} {name}")
                        else:
                            # Maybe a group/section?
                            title = props.get("title", props.get("key", ""))
                            print(f"    [{i}] {title} (no dataItem)")

                with open(f"view_{route.replace('/', '_')}.json", "w") as f:
                    json.dump(view, f, indent=2)

        # ─── 5. Try GetUnitMonitoringDataItems on service/input and service/output ───
        print("\n" + "=" * 70)
        print("5. GetUnitMonitoringDataItems on service sub-views")
        print("=" * 70)
        
        monitoring_query = """
        query ($input: UnitMonitoringDataItemsInput) {
          GetUnitMonitoringDataItems(input: $input) { register value }
        }
        """
        
        for route in ["service/input", "service/output", "/service/input", "/service/output"]:
            status, body = await gql(session, headers, REMOTE_API_URL, monitoring_query,
                                     variables={"input": {"route": route}})
            data = json.loads(body)
            errors = data.get("errors")
            result = data.get("data", {}).get("GetUnitMonitoringDataItems")
            if result:
                non_null = [i for i in result if i.get("register") is not None]
                print(f"\n  route={route!r}: {len(result)} items ({len(non_null)} with register)")
                for item in result[:20]:
                    print(f"    reg={item.get('register')}, val={item.get('value')}")
            elif errors:
                print(f"  route={route!r}: ERROR — {errors[0].get('message', '')[:100]}")
            else:
                print(f"  route={route!r}: No results")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
