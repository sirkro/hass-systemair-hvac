"""Discover device data reading/writing API."""
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


async def introspect_type(session, api, type_name):
    query = """
    {
      __type(name: "%s") {
        name
        kind
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
          args {
            name
            type {
              name
              kind
              ofType { name kind }
            }
          }
        }
        inputFields {
          name
          type {
            name
            kind
            ofType { name kind }
          }
        }
        enumValues {
          name
        }
      }
    }
    """ % type_name

    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    
    async with session.post(
        api._api_url,
        json={"query": query, "variables": {}},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        body = await resp.text()
        if resp.status == 200:
            return json.loads(body)
        return {"error": f"HTTP {resp.status}: {body[:500]}"}


async def try_query(session, api, name, query, variables=None):
    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    
    async with session.post(
        api._api_url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        body = await resp.text()
        print(f"\n=== {name} (HTTP {resp.status}) ===")
        if len(body) > 5000:
            print(body[:5000] + "... (truncated)")
        else:
            print(body)
        return body


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()

        # 1. Get devices first (fixing the query - no latestSync)
        result = await try_query(session, api, "GetAccountDevices", """{
          GetAccountDevices {
            identifier
            name
            status {
              connectionStatus
              serialNumber
              model
              hasAlarms
            }
            deviceType {
              entry
              module
              scope
              type
            }
          }
        }""")
        
        # Parse to get device ID
        data = json.loads(result)
        devices = data.get("data", {}).get("GetAccountDevices", [])
        device_id = None
        if devices:
            device_id = devices[0]["identifier"]
            print(f"\nFound device: {device_id} ({devices[0].get('name', 'unnamed')})")
        
        # 2. Introspect GetDeviceDetails type
        for type_name in ["GetDeviceDetails", "GetDeviceDetailsInput", 
                          "DeviceMetricsHistory", "GetDeviceMetricsHistoryInput"]:
            r = await introspect_type(session, api, type_name)
            print(f"\n=== Type: {type_name} ===")
            print(json.dumps(r, indent=2))
        
        # 3. Try GetDeviceDetails query with actual device ID
        if device_id:
            await try_query(session, api, "GetDeviceDetails", """{
              GetDeviceDetails(deviceId: "%s") {
                __typename
              }
            }""" % device_id)
            
            # Introspect to see what fields are available
            r = await introspect_type(session, api, "GetDeviceDetails")
            print(f"\n=== GetDeviceDetails type (full) ===")
            print(json.dumps(r, indent=2))
        
        # 4. Check all subscription types too
        sub_query = """
        {
          __schema {
            subscriptionType {
              name
              fields {
                name
                args {
                  name
                  type { name kind ofType { name kind } }
                }
                type { name kind ofType { name kind ofType { name kind } } }
              }
            }
          }
        }
        """
        await try_query(session, api, "Subscriptions", sub_query)
        
        # 5. Look for device-specific API endpoint
        # The reference code uses /gateway/api for everything.
        # Maybe device read/write is on a different path?
        # Let's try the old portal-gateway path too
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }
        
        old_url = "https://homesolutions.systemair.com/portal-gateway/api"
        old_introspection = """
        {
          __schema {
            queryType {
              name
              fields { name }
            }
            mutationType {
              name
              fields { name }
            }
          }
        }
        """
        
        async with session.post(
            old_url,
            json={"query": old_introspection, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            body = await resp.text()
            print(f"\n=== Old portal-gateway/api (HTTP {resp.status}) ===")
            if len(body) > 3000:
                print(body[:3000] + "... (truncated)")
            else:
                print(body)

        # 6. Also try /device-gateway/api
        device_gw_url = "https://homesolutions.systemair.com/device-gateway/api"
        async with session.post(
            device_gw_url,
            json={"query": old_introspection, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            body = await resp.text()
            print(f"\n=== device-gateway/api (HTTP {resp.status}) ===")
            if len(body) > 3000:
                print(body[:3000] + "... (truncated)")
            else:
                print(body)

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
