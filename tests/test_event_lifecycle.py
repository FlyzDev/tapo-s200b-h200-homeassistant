"""Regression checks for out-of-order event logs and HA startup buffering."""
from __future__ import annotations

import ast
import asyncio
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components/tapo_s200b_cloud"
source = (BASE / "__init__.py").read_text()
tree = ast.parse(source)
names = {
    "_event_key", "_event_timestamp", "_remember_event",
    "_process_button_events", "_flush_clicks",
}
nodes = [
    node for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in names
]
assert len(nodes) == len(names)

import importlib.util
spec = importlib.util.spec_from_file_location("tapo_event_parser_test", BASE / "event_parser.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

namespace = {
    "Any": object,
    "HomeAssistant": object,
    "CoreState": SimpleNamespace(running="RUNNING"),
    "deque": deque,
    "asyncio": asyncio,
    "_LOGGER": SimpleNamespace(info=MagicMock(), warning=MagicMock()),
    "event_log_id": parser.event_log_id,
    "device_id": parser.device_id,
    "normalize_event": parser.normalize_event,
    "_queue_click": MagicMock(),
    "CLICK_WINDOW_SECONDS": 1.4,
    "RAW_EVENT_NAME": "tapo_s200b_event",
    "PRESS_EVENT_NAME": "tapo_s200b_pressed",
    "ROTATE_EVENT_NAME": "tapo_s200b_rotated",
}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(BASE / "__init__.py"), "exec"), namespace)


def runtime():
    return {
        "seeded": set(),
        "seen_event_keys": {},
        "seen_event_order": {},
        "pending_clicks": {},
        "flush_tasks": {},
    }


def event(log_id, timestamp, name="singleClick"):
    return {"logId": log_id, "timestamp": timestamp, "name": name, "params": {}}


class EventDedupTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.run = runtime()
        self.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=MagicMock()))
        namespace["_queue_click"].reset_mock()

    async def test_baseline_no_replay_and_smaller_new_logid(self):
        button = {"thingName": "TEST_A", "model": "S200B"}
        old = event(2000, 10)
        fresh = event(5, 20)
        process = namespace["_process_button_events"]
        await process(self.hass, self.run, "TEST_A", button, [old])
        self.hass.bus.async_fire.assert_not_called()
        await process(self.hass, self.run, "TEST_A", button, [fresh, old])
        self.hass.bus.async_fire.assert_called_once()
        namespace["_queue_click"].assert_called_once()
        self.assertEqual(self.hass.bus.async_fire.call_args.args[1]["log_id"], 5)
        await process(self.hass, self.run, "TEST_A", button, [fresh, old])
        self.hass.bus.async_fire.assert_called_once()

    async def test_multi_button_id_independence(self):
        process = namespace["_process_button_events"]
        a = {"thingName": "TEST_A", "model": "S200B"}
        b = {"thingName": "TEST_B", "model": "S200D"}
        shared = event(7, 100)
        await process(self.hass, self.run, "TEST_A", a, [shared])
        await process(self.hass, self.run, "TEST_B", b, [shared])
        await process(self.hass, self.run, "TEST_A", a, [event(8, 110), shared])
        await process(self.hass, self.run, "TEST_B", b, [event(8, 110), shared])
        self.assertEqual(self.hass.bus.async_fire.call_count, 2)
        devices = [
            c.args[1]["device_id"] for c in self.hass.bus.async_fire.call_args_list
        ]
        self.assertEqual(devices, ["TEST_A", "TEST_B"])

    async def test_unknown_event_is_still_emitted(self):
        b = {"thingName": "TEST_C", "model": "S200B"}
        await namespace["_process_button_events"](self.hass,self.run,"TEST_C",b,[])
        await namespace["_process_button_events"](
            self.hass,self.run,"TEST_C",b,[event(9,100,"futureEvent")]
        )
        self.assertEqual(self.hass.bus.async_fire.call_args.args[1]["action"],"unknown")

    def test_bounded_history(self):
        remember = namespace["_remember_event"]
        for n in range(1501):
            remember(self.run, "A", (str(n),str(n),"singleClick"))
        self.assertEqual(len(self.run["seen_event_keys"]["A"]), 1000)
        self.assertNotIn(("0","0","singleClick"), self.run["seen_event_keys"]["A"])


class StartupTests(IsolatedAsyncioTestCase):
    async def test_click_held_until_automation_ready(self):
        b = {"thingName":"TEST_A", "model":"S200B"}
        rt=runtime()
        rt["pending_clicks"]["TEST_A"]=1
        h=SimpleNamespace(
            state="NOT_RUNNING",
            bus=SimpleNamespace(async_fire=MagicMock()),
        )
        waits=[]
        async def fake_sleep(sec):
            waits.append(sec)
            if len(waits) == 5:
                h.state="RUNNING"
        with patch.object(asyncio, "sleep", fake_sleep):
            await namespace["_flush_clicks"](h,rt,b)
        h.bus.async_fire.assert_called_once()
        kind, payload = h.bus.async_fire.call_args.args
        self.assertEqual(kind, "tapo_s200b_pressed")
        self.assertEqual(payload["action"], "single_click")
        self.assertEqual(payload["event"], "single_click")
        self.assertEqual(payload["device_id"], "TEST_A")
        self.assertEqual(rt["pending_clicks"],{})
        self.assertEqual(waits[0],1.4)

    async def test_ready_immediately_keeps_current_event(self):
        b={"thingName":"TEST_A","model":"S200B"}
        rt=runtime()
        rt["pending_clicks"]["TEST_A"]=2
        h=SimpleNamespace(
            state="RUNNING",
            bus=SimpleNamespace(async_fire=MagicMock()),
        )
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await namespace["_flush_clicks"](h,rt,b)
        self.assertEqual(h.bus.async_fire.call_args.args[1]["action"], "double_click")


if __name__ == "__main__":
    import unittest
    unittest.main()
