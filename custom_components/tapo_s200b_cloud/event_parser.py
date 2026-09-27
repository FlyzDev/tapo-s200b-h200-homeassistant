from __future__ import annotations

from typing import Any


def event_log_id(item: dict[str, Any]) -> int | None:
    value = item.get("logId")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def device_id(button: dict[str, Any]) -> str:
    return str(button.get("thingName") or button.get("deviceId") or "")


def normalize_event(
    item: dict[str, Any],
    button: dict[str, Any],
) -> dict[str, Any] | None:
    log_id = event_log_id(item)
    if log_id is None:
        return None

    native_name = str(item.get("name") or "")
    params = item.get("params")
    if not isinstance(params, dict):
        params = {}

    payload: dict[str, Any] = {
        "device_id": device_id(button),
        "model": str(button.get("model") or ""),
        "native_name": native_name,
        "log_id": log_id,
        "timestamp": item.get("timestamp"),
        "params": params,
        "source": "tapo_thing_event_log",
    }

    if native_name == "singleClick":
        payload["action"] = "single_click"
        payload["click_count"] = 1
        return payload

    if native_name == "doubleClick":
        payload["action"] = "double_click"
        payload["click_count"] = 2
        return payload

    if native_name == "rotation":
        try:
            degrees = int(params.get("rotate_deg", 0))
        except (TypeError, ValueError):
            degrees = 0
        payload["degrees"] = degrees
        payload["direction"] = (
            "clockwise"
            if degrees > 0
            else "anti_clockwise"
            if degrees < 0
            else "none"
        )
        payload["action"] = (
            "rotate_clockwise"
            if degrees > 0
            else "rotate_anti_clockwise"
            if degrees < 0
            else "rotation"
        )
        return payload

    payload["action"] = "unknown"
    return payload
