"""Round 4: Get /service/input and /service/output views to map positional values.
Also scan high data item IDs (1000-2000) for RPM and other missing sensors."""
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

TARGET_REGISTERS = {
    12101: "REG_SENSOR_OAT",
    12102: "REG_SENSOR_SAT",
    12107: "REG_SENSOR_OHT",
    12108: "OHT (1-idx)",
    12135: "REG_SENSOR_RHS_PDM",
    12400: "REG_SENSOR_RPM_SAF",
    12401: "REG_SENSOR_RPM_EAF",
    12543: "REG_SENSOR_PDM_EAT_VALUE",
    12544: "EAT (1-idx)",
    14000: "REG_OUTPUT_SAF",
    14001: "REG_OUTPUT_EAF",
    14100: "REG_OUTPUT_Y1_ANALOG",
    14101: "Y1_DIG",
    14200: "REG_OUTPUT_Y3_ANALOG",
    14201: "Y3_DIG",
}


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
        print("Login OK\n")
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
            "device-id": DEVICE_ID,
            "device-type": "LEGACY",
        }

        view_query = """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            id title route error
            children { type feature properties }
          }
        }
        """
        
        monitoring_query = """
        query ($input: UnitMonitoringDataItemsInput) {
          GetUnitMonitoringDataItems(input: $input) { register value }
        }
        """

        # ─── 1. Get /service/input view and correlate with monitoring data ───
        for view_route in ["/service/input", "/service/output"]:
            print("=" * 70)
            print(f"VIEW: {view_route}")
            print("=" * 70)
            
            # Get view
            status, body = await gql(session, headers, REMOTE_API_URL, view_query,
                                     variables={"input": {"route": view_route}})
            data = json.loads(body)
            if data.get("errors"):
                print(f"View Error: {data['errors'][0].get('message', '')[:200]}")
                continue
            view = data.get("data", {}).get("GetView")
            if not view:
                print("No view data")
                continue
            
            children = view.get("children", [])
            print(f"Title: {view.get('title')}, Children: {len(children)}")
            
            # Get monitoring data
            status, body = await gql(session, headers, REMOTE_API_URL, monitoring_query,
                                     variables={"input": {"route": view_route}})
            mon_data = json.loads(body)
            mon_items = mon_data.get("data", {}).get("GetUnitMonitoringDataItems", [])
            print(f"Monitoring items: {len(mon_items)}")
            
            # Correlate
            max_items = max(len(children), len(mon_items))
            for i in range(max_items):
                mon_val = mon_items[i]["value"] if i < len(mon_items) else "N/A"
                
                if i < len(children):
                    child = children[i]
                    props = child.get("properties")
                    if isinstance(props, str):
                        try:
                            props = json.loads(props)
                        except:
                            pass
                    
                    di = props.get("dataItem", {}) if isinstance(props, dict) else {}
                    if isinstance(di, dict):
                        item_id = di.get("id", "?")
                        ext = di.get("extension", {})
                        mb = ext.get("modbusRegister", 0)
                        dec = di.get("decimals")
                        unit = di.get("unit")
                        name = TARGET_REGISTERS.get(mb, "")
                        marker = " <<<" if name else ""
                        child_desc = f"ID={item_id:>4}, Modbus={mb:>6}, dec={dec}, unit={unit}{marker} {name}"
                    else:
                        # It might be a section/group
                        title = props.get("title", "") if isinstance(props, dict) else ""
                        route_val = props.get("route", "") if isinstance(props, dict) else ""
                        child_desc = f"[section] title={title}, route={route_val}"
                else:
                    child_desc = "(no view child)"
                
                print(f"  [{i:3d}] val={str(mon_val):>10s}  |  {child_desc}")
            
            # Save
            fname = f"view{view_route.replace('/', '_')}_correlated.json"
            with open(fname, "w") as f:
                json.dump({"view": view, "monitoring": mon_items}, f, indent=2)
            print(f"\nSaved to {fname}\n")

        # ─── 2. Scan data item IDs 1000-2000 for remaining sensor registers ───
        print("=" * 70)
        print("Scanning data item IDs 1000-2000 for sensor registers")
        print("=" * 70)
        found = []
        for start in range(1000, 2001, 100):
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
                    if mb in TARGET_REGISTERS or (12000 <= mb <= 14999):
                        ro = 'RO' if item.get('readOnly') else 'RW'
                        name = TARGET_REGISTERS.get(mb, f"(Modbus {mb})")
                        print(f"  ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}] dec={item.get('decimals')} {name}")
                        found.append(item)
        
        if not found:
            print("  No items found in 1000-2000 range for sensor registers")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
