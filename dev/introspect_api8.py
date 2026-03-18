"""Fetch the SPA shell and find JS bundle URLs, then search for API endpoints."""
import asyncio
import json
import os
import re
import importlib.util

import aiohttp

spec = importlib.util.spec_from_file_location(
    "cloud_api",
    os.path.join(os.path.dirname(__file__), "custom_components", "systemair", "cloud_api.py")
)
cloud_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_api_mod)
SystemairCloudAPI = cloud_api_mod.SystemairCloudAPI


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        
        # 1. Get the SPA shell HTML
        async with session.get(
            "https://homesolutions.systemair.com/",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            html = await resp.text()
            print(f"SPA HTML: {len(html)} bytes")
            
            # Find all script src URLs
            scripts = re.findall(r'src="([^"]+\.js[^"]*)"', html)
            print(f"Scripts found: {scripts}")
            
            # Find all link href for CSS
            links = re.findall(r'href="([^"]+\.css[^"]*)"', html)
            print(f"CSS found: {links}")
        
        # 2. Fetch the main JS bundle(s) and look for API endpoints
        for script_url in scripts[:5]:  # limit to first 5
            if not script_url.startswith("http"):
                script_url = f"https://homesolutions.systemair.com{script_url}"
            
            try:
                async with session.get(
                    script_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        js = await resp.text()
                        print(f"\n=== {script_url} ({len(js)} bytes) ===")
                        
                        # Search for API-related patterns
                        patterns = [
                            r'["\']/(gateway|api|device|westcontrol|graphql)[^"\']*["\']',
                            r'https?://[^\s"\']+(?:api|gateway|device|graphql)[^\s"\']*',
                            r'GetDeviceView|WriteDeviceValues|WriteDevice|DeviceControl|SetDevice',
                            r'mutation\s+\w+',
                            r'/streaming',
                            r'register[Vv]alues|registerValues',
                            r'WriteRegister|ReadRegister|SetRegister',
                            r'deviceId.*route|route.*deviceId',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, js)
                            if matches:
                                unique = list(set(matches))[:10]
                                print(f"  Pattern '{pattern}': {unique}")
                    else:
                        print(f"\n{script_url}: HTTP {resp.status}")
            except Exception as e:
                print(f"\n{script_url}: {type(e).__name__}: {e}")
        
        # 3. Also look for module federation remoteEntry
        # The device type info said entry="remoteEntry.js", module="./ApplicationRoot", scope="westcontrol_ui"
        # Module federation loads from a specific host. Let's look for the container init
        
        # The SPA loads westcontrol_ui microfrontend. Let's find where from.
        # Typically it's defined in the webpack config or as a window.__remotes__ config
        for script_url in scripts[:5]:
            if not script_url.startswith("http"):
                script_url = f"https://homesolutions.systemair.com{script_url}"
            
            try:
                async with session.get(
                    script_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        js = await resp.text()
                        
                        # Look for module federation remotes
                        remote_patterns = [
                            r'westcontrol[^"\']*remoteEntry',
                            r'remoteEntry\.js',
                            r'westcontrol_ui[^"\']*',
                            r'scope.*westcontrol|westcontrol.*scope',
                            r'__remotes__|remotes\s*:',
                            r'ModuleFederation|module_federation',
                        ]
                        
                        found_anything = False
                        for pattern in remote_patterns:
                            matches = re.findall(pattern, js[:200000])  # first 200k chars
                            if matches:
                                unique = list(set(matches))[:5]
                                if not found_anything:
                                    print(f"\n  Module Federation patterns in {script_url}:")
                                    found_anything = True
                                print(f"    '{pattern}': {unique}")
                                
                                # Get context around matches
                                for m in re.finditer(pattern, js[:200000]):
                                    start = max(0, m.start() - 100)
                                    end = min(len(js), m.end() + 100)
                                    print(f"    Context: ...{js[start:end]}...")
                                    break  # just first context
            except:
                pass
                
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
