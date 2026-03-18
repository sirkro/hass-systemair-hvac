"""Comprehensive investigation of GetUnitMonitoringDataItems and GetView.

Goals:
1. Try GetUnitMonitoringDataItems with /service route
2. Get /home view and parse children properties as JSON to find register mappings
3. Get /service view and try monitoring on its sub-routes
4. Try GetDataItems with high IDs (300-600 range) to find sensor register mappings
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

VIEW_QUERY = """
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

        # ─── 1. GetView for /home — parse children properties ───
        print("=" * 70)
        print("1. GetView /home — parse children properties as JSON")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY,
                                 variables={"input": {"route": "/home"}})
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:2], indent=2)}")
        view = data.get("data", {}).get("GetView")
        if view:
            children = view.get("children", [])
            print(f"View: id={view.get('id')}, title={view.get('title')}, children={len(children)}")
            for i, child in enumerate(children):
                props = child.get("properties")
                props_parsed = None
                if isinstance(props, str):
                    try:
                        props_parsed = json.loads(props)
                    except:
                        props_parsed = props
                elif props is not None:
                    props_parsed = props
                
                sub_children = child.get("children", [])
                print(f"\n  [{i}] type={child.get('type')}, feature={child.get('feature')}")
                if props_parsed:
                    if isinstance(props_parsed, dict):
                        # Print all keys and values
                        for k, v in props_parsed.items():
                            val_str = json.dumps(v) if not isinstance(v, str) else v
                            if len(val_str) > 150:
                                val_str = val_str[:150] + "..."
                            print(f"       {k}: {val_str}")
                    else:
                        print(f"       props: {json.dumps(props_parsed)[:300]}")
                elif props is not None:
                    print(f"       raw props: {str(props)[:300]}")
                else:
                    print(f"       props: None")
                
                # Also print sub-children properties
                for j, sub in enumerate(sub_children or []):
                    sub_props = sub.get("properties")
                    if isinstance(sub_props, str):
                        try:
                            sub_props = json.loads(sub_props)
                        except:
                            pass
                    sub_sub = sub.get("children", [])
                    print(f"    [{i}.{j}] type={sub.get('type')}, feature={sub.get('feature')}, sub_children={len(sub_sub or [])}")
                    if sub_props:
                        if isinstance(sub_props, dict):
                            for k, v in sub_props.items():
                                val_str = json.dumps(v) if not isinstance(v, str) else v
                                if len(val_str) > 150:
                                    val_str = val_str[:150] + "..."
                                print(f"           {k}: {val_str}")
                        else:
                            print(f"           props: {json.dumps(sub_props)[:300]}")
            
            # Save full view for analysis
            with open("view_home_full.json", "w") as f:
                json.dump(view, f, indent=2)
            print("\nSaved full view to view_home_full.json")

        # ─── 2. GetView for /service ───
        print("\n" + "=" * 70)
        print("2. GetView /service")
        print("=" * 70)
        status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY,
                                 variables={"input": {"route": "/service"}})
        print(f"HTTP {status}")
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
                sub_children = child.get("children", [])
                print(f"  [{i}] type={child.get('type')}, feature={child.get('feature')}, sub_children={len(sub_children or [])}")
                if isinstance(props, dict):
                    for k, v in props.items():
                        val_str = json.dumps(v) if not isinstance(v, str) else v
                        if len(val_str) > 100:
                            val_str = val_str[:100] + "..."
                        print(f"       {k}: {val_str}")
                elif props:
                    print(f"       props: {str(props)[:200]}")
            
            with open("view_service_full.json", "w") as f:
                json.dump(view, f, indent=2)
            print("Saved to view_service_full.json")

        # ─── 3. GetUnitMonitoringDataItems with various routes ───
        print("\n" + "=" * 70)
        print("3. GetUnitMonitoringDataItems with various routes")
        print("=" * 70)
        routes_to_test = [
            "/service",
            "/home",
            "/service/unit-status",
            "/service/input-output",
            "/service/sensors",
            "/service/fan",
            "/service/temperature",
            "/service/ventilation",
        ]
        for route in routes_to_test:
            status, body = await gql(session, headers, REMOTE_API_URL, MONITORING_QUERY,
                                     variables={"input": {"route": route}})
            data = json.loads(body)
            errors = data.get("errors")
            result = data.get("data", {}).get("GetUnitMonitoringDataItems")
            
            if result:
                non_null_regs = [item for item in result if item.get("register") is not None]
                print(f"\n  route={route!r}: {len(result)} items ({len(non_null_regs)} with register)")
                for item in result[:40]:
                    reg = item.get("register")
                    val = item.get("value")
                    if reg is not None:
                        print(f"    Register {reg}: {val}")
                    else:
                        print(f"    (positional) value={val}")
                if len(result) > 40:
                    print(f"    ... total {len(result)} items")
                    # Save to file
                    fname = f"monitoring_{route.replace('/', '_').strip('_')}.json"
                    with open(fname, "w") as f:
                        json.dump(result, f, indent=2)
                    print(f"    Saved to {fname}")
            elif errors:
                msg = errors[0].get("message", "")[:150]
                print(f"\n  route={route!r}: ERROR — {msg}")
            else:
                print(f"\n  route={route!r}: No results")

        # ─── 4. Get all top-level views to discover routes ───
        print("\n" + "=" * 70)
        print("4. Discover all available routes via GetView /")
        print("=" * 70)
        # Try root and other common routes
        for route in ["/", "/device", "/settings", "/alarms"]:
            status, body = await gql(session, headers, REMOTE_API_URL, VIEW_QUERY,
                                     variables={"input": {"route": route}})
            data = json.loads(body)
            errors = data.get("errors")
            view = data.get("data", {}).get("GetView")
            if view:
                children = view.get("children", [])
                print(f"\n  route={route!r}: title={view.get('title')}, children={len(children)}")
                for i, child in enumerate(children[:20]):
                    props = child.get("properties")
                    if isinstance(props, str):
                        try:
                            props = json.loads(props)
                        except:
                            pass
                    route_val = props.get("route", "") if isinstance(props, dict) else ""
                    title_val = props.get("title", "") if isinstance(props, dict) else ""
                    print(f"    [{i}] type={child.get('type')}, route={route_val}, title={title_val}")
            elif errors:
                msg = errors[0].get("message", "")[:150]
                print(f"\n  route={route!r}: ERROR — {msg}")
            else:
                print(f"\n  route={route!r}: No data")

        # ─── 5. Try GetDataItems with high IDs to find sensor mappings ───
        print("\n" + "=" * 70)
        print("5. GetDataItems — scan IDs 300-600 for sensor register mappings")
        print("=" * 70)
        for start in range(300, 601, 50):
            ids = list(range(start, start + 50))
            status, body = await gql(session, headers, REMOTE_API_URL, """
            query ($input: [Int]) { GetDataItems(input: $input) }
            """, variables={"input": ids})
            data = json.loads(body)
            if data.get("errors"):
                print(f"  IDs {start}-{start+49}: Error: {data['errors'][0].get('message', '')[:100]}")
                continue
            items = data.get("data", {}).get("GetDataItems")
            if items:
                if isinstance(items, str):
                    items = json.loads(items)
                # Filter to items with interesting registers
                for item in items:
                    ext = item.get("extension", {})
                    mb = ext.get("modbusRegister", 0)
                    if mb >= 12000 or mb >= 14000:
                        ro = 'RO' if item.get('readOnly') else 'RW'
                        print(f"    ID {item['id']:4d} -> Modbus {mb:>6d} = {str(item.get('value')):>10s} [{ro}] decimals={item.get('decimals')}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
