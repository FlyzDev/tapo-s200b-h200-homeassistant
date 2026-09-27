"""Minimal non-Home-Assistant example.

This intentionally prints no account value, token, Thing ID, or raw headers.
It is a protocol demonstration, not a long-running production daemon.
"""

from __future__ import annotations

import asyncio
import getpass
import importlib.util
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
CLOUD_PATH = ROOT / "custom_components" / "tapo_s200b_cloud" / "cloud.py"

spec = importlib.util.spec_from_file_location("tapo_public_cloud", CLOUD_PATH)
cloud = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(cloud)


async def main() -> None:
    account = input("Tapo account email: ").strip()
    account_secret = getpass.getpass("Tapo account password: ")

    async with aiohttp.ClientSession() as session:
        client = cloud.TapoCloudClient(session, account, account_secret)
        await client.login_thing_api()
        buttons = await client.discover_buttons()

        print(f"Found {len(buttons)} supported button(s).")
        for index, button in enumerate(buttons, start=1):
            model = str(button.get("model") or "unknown")
            events = await client.thing_events(button, fetch_size=10)
            names = sorted(
                {
                    str(event.get("name"))
                    for event in events
                    if event.get("name")
                }
            )
            print(f"Button {index}: model={model}, event_names={names}")


if __name__ == "__main__":
    asyncio.run(main())
