"""Second round investigation — fix view query, wider data item scan, try /service sub-views."""
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


MONITORING_QUERY = """
query ($input: UnitMonitoringDataItemsInput) {
  GetUnitMonitoringDataItems(input: $input) {
    register
    value
  }
}
"""

# View query without nested children (GraphqlProxyViewElement doesn't support nesting)
VIEW_QUERY_FLAT = """
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
    }
  }
}
"""


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

        # ─── 1. Introspect GraphqlProxyViewElement to see actual fields ───
        print("=" * 70)
        print("1. Introspect GraphqlProxyViewElement and GraphqlProxyView")
        print("=" * 70)
        for type_name in ["GraphqlProxyViewElement", "GraphqlProxyView", "GraphqlProxyViewOutput"]:
            status, body = await gql(session, headers, REMOTE_API_URL, """
            {
              __type(name: "%s") {
                name kind
                fields { name type { name kind ofType { name kind ofType { name kind ofType { name kind } } } } }
              }
            }
            """ % type_name)
            data = json.loads(body)
            t = data.get("data", {}).get("__type")
            if t:
                print(f"\n  {t['name']} ({t.get('kind')}):")
                for f in (t.get("fields") or []):
                    ft = f["type"]
                    tn = ft.get("name") or f"{ft.get('kind')}({ft.get('ofType', {}).get('name') or ft.get('ofType', {}).get('kind', '')})"
                    print(f"    {f['name']}: {tn}")
            else:
                print(f"\n  {type_name}: not found")

        # ─── 2. GetView /home (flat — no nested children) ───
        print("\n" + "=" * 70)
        print("2. GetView /home (flat children)")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY_FLAT,
                                 variables={"input": {"route": "/home"}})
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
        view = data.get("data", {}).get("GetView")
        if view:
            children = view.get("children", [])
            print(f"View: id={view.get('id')}, title={view.get('title')}, children={len(children)}")
            for i, child in enumerate(children):
                props = child.get("properties")
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        pass
                print(f"\n  [{i}] type={child.get('type')}, feature={child.get('feature')}")
                if isinstance(props, dict):
                    for k, v in sorted(props.items()):
                        val_str = json.dumps(v) if not isinstance(v, str) else v
                        if len(val_str) > 200:
                            val_str = val_str[:200] + "..."
                        print(f"       {k}: {val_str}")
                elif props:
                    print(f"       props: {str(props)[:300]}")
            
            with open("view_home_flat.json", "w") as f:
                json.dump(view, f, indent=2)
            print("\n\nSaved to view_home_flat.json")

        # ─── 3. GetView /service (flat) ───
        print("\n" + "=" * 70)
        print("3. GetView /service (flat children)")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY_FLAT,
                                 variables={"input": {"route": "/service"}})
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
        view = data.get("data", {}).get("GetView")
        if view:
            children = view.get("children", [])
            print(f"View: id={view.get('id')}, title={view.get('title')}, children={len(children)}")
            
            # Collect routes from children for monitoring test
            service_routes = []
            for i, child in enumerate(children):
                props = child.get("properties")
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        pass
                route_val = ""
                if isinstance(props, dict):
                    route_val = props.get("route", "")
                print(f"  [{i}] type={child.get('type')}, feature={child.get('feature')}, route={route_val}")
                if isinstance(props, dict):
                    for k, v in sorted(props.items()):
                        if k != "route":
                            val_str = json.dumps(v) if not isinstance(v, str) else v
                            if len(val_str) > 100:
                                val_str = val_str[:100] + "..."
                            print(f"       {k}: {val_str}")
                if route_val:
                    service_routes.append(route_val)
            
            with open("view_service_flat.json", "w") as f:
                json.dump(view, f, indent=2)
            print(f"\nSaved to view_service_flat.json")
            
            # ─── 3b. Try monitoring on discovered service sub-routes ───
            if service_routes:
                print(f"\nTrying GetUnitMonitoringDataItems on {len(service_routes)} service routes...")
                for route in service_routes:
                    status, body = await gql(session, headers, REMOTE_API_URL, MONITORING_QUERY,
                                             variables={"input": {"route": route}})
                    data = json.loads(body)
                    errors = data.get("errors")
                    result = data.get("data", {}).get("GetUnitMonitoringDataItems")
                    if result:
                        non_null = [item for item in result if item.get("register") is not None]
                        print(f"  route={route!r}: {len(result)} items ({len(non_null)} with register)")
                        for item in result[:10]:
                            print(f"    reg={item.get('register')}, val={item.get('value')}")
                        if len(result) > 10:
                            print(f"    ... {len(result)} total")
                    elif errors:
                        print(f"  route={route!r}: ERROR — {errors[0].get('message', '')[:100]}")
                    else:
                        print(f"  route={route!r}: No results")

        # ─── 4. Correlate /home monitoring values with view children ───
        print("\n" + "=" * 70)
        print("4. Correlate /home monitoring data with view children")
        print("=" * 70)
        
        # Get monitoring data
        status, body = await gql(session, headers, REMOTE_API_URL, MONITORING_QUERY,
                                 variables={"input": {"route": "/home"}})
        mon_data = json.loads(body)
        mon_items = mon_data.get("data", {}).get("GetUnitMonitoringDataItems", [])
        
        # Get view
        status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY_FLAT,
                                 variables={"input": {"route": "/home"}})
        view_data = json.loads(body)
        view_children = view_data.get("data", {}).get("GetView", {}).get("children", [])
        
        print(f"Monitoring items: {len(mon_items)}, View children: {len(view_children)}")
        max_items = max(len(mon_items), len(view_children))
        for i in range(max_items):
            mon_val = mon_items[i]["value"] if i < len(mon_items) else "N/A"
            if i < len(view_children):
                child = view_children[i]
                props = child.get("properties")
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        pass
                # Extract key identifier from props
                label = ""
                data_item_id = ""
                if isinstance(props, dict):
                    label = props.get("label", props.get("title", props.get("name", "")))
                    data_item_id = props.get("dataItemId", props.get("id", props.get("dataItem", "")))
                    if not label and not data_item_id:
                        label = str(list(props.keys())[:5])
                child_info = f"type={child.get('type')}, feature={child.get('feature')}, label={label}, dataItemId={data_item_id}"
            else:
                child_info = "N/A (no matching view child)"
            print(f"  [{i:2d}] value={str(mon_val):>10s}  |  {child_info}")

        # ─── 5. Scan ALL data item IDs 0-800 to find any sensor registers ───
        print("\n" + "=" * 70)
        print("5. GetDataItems — comprehensive scan for 12000-14999 register range")
        print("=" * 70)
        sensor_items = []
        for start in range(0, 801, 100):
            ids = list(range(start, start + 100))
            status, body = await gql(session, headers, REMOTE_API_URL, """
            query ($input: [Int]) { GetDataItems(input: $input) }
            """, variables={"input": ids})
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
                    if 12000 <= mb <= 14999:
                        sensor_items.append(item)
                        ro = 'RO' if item.get('readOnly') else 'RW'
                        print(f"  ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}]")
        
        if not sensor_items:
            print("  No data items found mapping to 12000-14999 register range")
            
            # Also try very high IDs
            print("\n  Trying IDs 800-1200...")
            for start in range(800, 1201, 100):
                ids = list(range(start, start + 100))
                status, body = await gql(session, headers, REMOTE_API_URL, """
                query ($input: [Int]) { GetDataItems(input: $input) }
                """, variables={"input": ids})
                data = json.loads(body)
                if data.get("errors"):
                    print(f"  IDs {start}-{start+99}: Error")
                    continue
                items = data.get("data", {}).get("GetDataItems")
                if items:
                    if isinstance(items, str):
                        items = json.loads(items)
                    for item in items:
                        ext = item.get("extension", {})
                        mb = ext.get("modbusRegister", 0)
                        if 12000 <= mb <= 14999:
                            print(f"  ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
