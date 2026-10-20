"""Regression tests for the HACS authentication review.

Home Assistant is not installed on the standalone unit-test runner. The cloud
client and polling functions are exercised with small dependency stubs.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "tapo_s200b_cloud"

fake_aiohttp = types.ModuleType("aiohttp")
fake_aiohttp.ClientError = type("ClientError", (Exception,), {})
fake_aiohttp.ClientTimeout = lambda *, total: total

with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
    spec = importlib.util.spec_from_file_location(
        "tapo_cloud_lifecycle_test", INTEGRATION / "cloud.py"
    )
    cloud = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cloud)


def load_poll_functions():
    tree = ast.parse((INTEGRATION / "__init__.py").read_text())
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in {"_retry_delay", "_poll_loop"}
    ]
    assert len(functions) == 2
    namespace = {
        "Any": object,
        "HomeAssistant": object,
        "ConfigEntry": object,
        "TapoCloudClient": object,
        "TapoAuthenticationError": cloud.TapoAuthenticationError,
        "TapoTokenExpired": cloud.TapoTokenExpired,
        "POLL_SECONDS": 1,
        "FETCH_SIZE": 50,
        "_LOGGER": logging.getLogger("tapo-lifecycle-test"),
        "asyncio": asyncio,
        "event_log_id": lambda event: event.get("logId"),
        "_process_button_events": AsyncMock(),
        "_connect": AsyncMock(),
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(INTEGRATION / "__init__.py"), "exec"),
        namespace,
    )
    return namespace


class FakeResponse:
    def __init__(self, status: int, data: dict):
        self.status = status
        self.data = data

    async def text(self):
        return json.dumps(self.data)


class FakeResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return False


class CloudAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, status=200, data=None):
        session = types.SimpleNamespace(
            post=lambda *_args, **_kwargs: FakeResponseContext(
                FakeResponse(status, data if data is not None else {"result": {"token": "TEST"}})
            )
        )
        return cloud.TapoCloudClient(
            session, "user@example.com", "NOT_A_REAL_PASSWORD", ssl_context=object()
        )

    async def test_rejected_login_error_code_requests_reauth(self):
        client = self.make_client(data={"error_code": -20651})
        with self.assertRaises(cloud.TapoAuthenticationError):
            await client._legacy_login("https://example.invalid")

    async def test_rejected_login_http_status_requests_reauth(self):
        client = self.make_client(status=403)
        with self.assertRaises(cloud.TapoAuthenticationError):
            await client._legacy_login("https://example.invalid")

    async def test_network_timeout_does_not_look_like_invalid_password(self):
        client = self.make_client()
        client._legacy_login = AsyncMock(side_effect=TimeoutError)
        with self.assertRaises(cloud.TapoCloudError) as context:
            await client.login_thing_api()
        self.assertNotIsInstance(context.exception, cloud.TapoAuthenticationError)
        self.assertEqual(client._legacy_login.await_count, len(cloud.THING_LOGIN_URLS))

    async def test_failed_login_stops_after_one_endpoint_pass(self):
        client = self.make_client()
        client._legacy_login = AsyncMock(
            side_effect=cloud.TapoAuthenticationError("rejected")
        )
        with self.assertRaises(cloud.TapoAuthenticationError):
            await client.login_thing_api()
        self.assertEqual(client._legacy_login.await_count, len(cloud.THING_LOGIN_URLS))


class PollingAuthLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = load_poll_functions()
        self.hass = object()
        self.entry = types.SimpleNamespace(async_start_reauth=MagicMock())
        self.runtime = {
            "client": types.SimpleNamespace(thing_events=AsyncMock()),
            "buttons": {},
            "errors": 0,
            "token_expirations": 0,
        }

    def test_exponential_backoff_is_capped(self):
        delay = self.ns["_retry_delay"]
        self.assertEqual(
            [delay(i) for i in (1, 2, 3, 4, 5, 6, 7, 100)],
            [5, 10, 20, 40, 80, 160, 300, 300],
        )

    async def test_explicit_login_rejection_requests_reauth_and_stops(self):
        self.ns["_connect"].side_effect = cloud.TapoAuthenticationError("rejected")
        await self.ns["_poll_loop"](self.hass, self.entry, self.runtime)
        self.entry.async_start_reauth.assert_called_once_with(self.hass)
        self.assertEqual(self.ns["_connect"].await_count, 1)

    async def test_rejected_new_token_requests_reauth_after_one_relogin(self):
        async def connect(_hass, _entry, runtime):
            runtime["buttons"] = {"button": {"thingName": "fake"}}
        self.ns["_connect"].side_effect = connect
        self.runtime["client"].thing_events.side_effect = cloud.TapoTokenExpired()
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await self.ns["_poll_loop"](self.hass, self.entry, self.runtime)
        self.entry.async_start_reauth.assert_called_once_with(self.hass)
        self.assertEqual(self.ns["_connect"].await_count, 2)

    async def test_transient_errors_back_off_without_force_relogin(self):
        count = 0
        delays = []

        async def fail_then_stop(_hass, _entry, _runtime):
            nonlocal count
            count += 1
            if count > 3:
                raise asyncio.CancelledError
            raise ConnectionError("network down")

        async def fake_sleep(delay):
            delays.append(delay)

        self.ns["_connect"].side_effect = fail_then_stop
        with patch.object(asyncio, "sleep", fake_sleep):
            with self.assertRaises(asyncio.CancelledError):
                await self.ns["_poll_loop"](self.hass, self.entry, self.runtime)
        self.assertEqual(delays, [5, 10, 20])
        self.entry.async_start_reauth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
