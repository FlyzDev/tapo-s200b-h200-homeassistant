from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import (
    TapoCloudClient,
    TapoCloudError,
    TapoTokenExpired,
    build_ssl_context,
)
from .const import (
    CLICK_WINDOW_SECONDS,
    CONF_ACCOUNT,
    CONF_APP_SERVER_URL,
    CONF_SECRET,
    CONF_TERMINAL_UUID,
    CONF_TOKEN,
    DOMAIN,
    FETCH_SIZE,
    POLL_SECONDS,
    PRESS_EVENT_NAME,
    RAW_EVENT_NAME,
    ROTATE_EVENT_NAME,
)
from .event_parser import device_id, event_log_id, normalize_event

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if entry.entry_id in hass.data[DOMAIN]:
        return True

    ssl_context = await hass.async_add_executor_job(build_ssl_context)
    client = TapoCloudClient(
        async_get_clientsession(hass),
        entry.data[CONF_ACCOUNT],
        entry.data[CONF_SECRET],
        terminal_uuid=entry.data.get(CONF_TERMINAL_UUID),
        token=entry.data.get(CONF_TOKEN),
        app_server_url=entry.data.get(CONF_APP_SERVER_URL),
        ssl_context=ssl_context,
    )
    runtime: dict[str, Any] = {
        "client": client,
        "buttons": {},
        "last_log_ids": {},
        "seeded": set(),
        "pending_clicks": {},
        "flush_tasks": {},
        "errors": 0,
    }
    hass.data[DOMAIN][entry.entry_id] = runtime
    _set_status(hass, "starting", runtime)

    runtime["task"] = hass.async_create_background_task(
        _poll_loop(hass, entry, runtime),
        name="tapo_s200b_cloud_poll",
    )

    def _on_stop(_event: Any) -> None:
        _cancel_runtime(runtime)

    runtime["unsub_stop"] = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        _on_stop,
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime:
        unsub_stop = runtime.pop("unsub_stop", None)
        if unsub_stop is not None:
            unsub_stop()
        _cancel_runtime(runtime)
    return True


def _cancel_runtime(runtime: dict[str, Any]) -> None:
    task = runtime.get("task")
    if task is not None and not task.done():
        task.cancel()
    for task in runtime.get("flush_tasks", {}).values():
        if task is not None and not task.done():
            task.cancel()


def _set_status(
    hass: HomeAssistant,
    state: str,
    runtime: dict[str, Any],
    **extra: Any,
) -> None:
    buttons = list(runtime.get("buttons", {}).values())
    hass.states.async_set(
        "sensor.tapo_s200b_cloud",
        state,
        {
            "friendly_name": "Tapo S200B/S200D Cloud Events",
            "poll_seconds": POLL_SECONDS,
            "fetch_size": FETCH_SIZE,
            "button_count": len(buttons),
            "models": sorted(
                {
                    str(button.get("model") or "")
                    for button in buttons
                    if button.get("model")
                }
            ),
            **extra,
        },
    )


async def _poll_loop(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: dict[str, Any],
) -> None:
    while True:
        try:
            if not runtime["buttons"]:
                await _connect(hass, entry, runtime)

            client: TapoCloudClient = runtime["client"]
            total_events = 0
            for key, button in list(runtime["buttons"].items()):
                events = await client.thing_events(
                    button,
                    fetch_size=FETCH_SIZE,
                )
                valid = [
                    item for item in events if event_log_id(item) is not None
                ]
                total_events += len(valid)
                await _process_button_events(
                    hass,
                    runtime,
                    key,
                    button,
                    valid,
                )

            runtime["errors"] = 0
            _set_status(
                hass,
                "connected",
                runtime,
                returned_events=total_events,
            )

        except TapoTokenExpired:
            runtime["buttons"] = {}
            if not await _reconnect(hass, entry, runtime):
                await asyncio.sleep(15)
                continue
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            runtime["errors"] = int(runtime.get("errors", 0)) + 1
            if runtime["errors"] == 1 or runtime["errors"] % 30 == 0:
                _LOGGER.warning(
                    "Tapo Event Log poll failed (%s): %s",
                    runtime["errors"],
                    type(err).__name__,
                )
            _set_status(
                hass,
                "error",
                runtime,
                error=type(err).__name__,
                consecutive_errors=runtime["errors"],
            )
            if runtime["errors"] >= 3:
                runtime["buttons"] = {}
                await _reconnect(hass, entry, runtime)
                await asyncio.sleep(5)

        await asyncio.sleep(POLL_SECONDS)


async def _process_button_events(
    hass: HomeAssistant,
    runtime: dict[str, Any],
    key: str,
    button: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    if key not in runtime["seeded"]:
        runtime["last_log_ids"][key] = max(
            (event_log_id(item) or 0 for item in events),
            default=0,
        )
        runtime["seeded"].add(key)
        _LOGGER.info(
            "Tapo button Event Log seeded: model=%s logId=%s",
            button.get("model"),
            runtime["last_log_ids"][key],
        )
        return

    last_log_id = int(runtime["last_log_ids"].get(key, 0))
    fresh = sorted(
        (
            item
            for item in events
            if (event_log_id(item) or 0) > last_log_id
        ),
        key=lambda item: event_log_id(item) or 0,
    )
    for item in fresh:
        payload = normalize_event(item, button)
        if payload is None:
            continue
        hass.bus.async_fire(RAW_EVENT_NAME, payload)
        action = payload.get("action")
        if action == "single_click":
            _queue_click(hass, runtime, button, 1)
        elif action == "double_click":
            _queue_click(hass, runtime, button, 2)
        elif str(action).startswith("rotate_") or action == "rotation":
            hass.bus.async_fire(ROTATE_EVENT_NAME, payload)
        last_log_id = max(last_log_id, int(payload["log_id"]))
    runtime["last_log_ids"][key] = last_log_id


async def _connect(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: dict[str, Any],
) -> None:
    client: TapoCloudClient = runtime["client"]
    await client.login_thing_api()
    buttons = await client.discover_buttons()
    runtime["buttons"] = {
        device_id(button): button
        for button in buttons
        if device_id(button)
    }
    if not runtime["buttons"]:
        raise TapoCloudError("Supported buttons had no Thing identifiers")

    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_TOKEN: str(client.token or ""),
            CONF_APP_SERVER_URL: client.app_server_url,
            CONF_TERMINAL_UUID: client.terminal_uuid,
        },
    )
    _LOGGER.info(
        "Connected to Tapo Thing Event Log for %s button(s)",
        len(runtime["buttons"]),
    )


async def _reconnect(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: dict[str, Any],
) -> bool:
    try:
        await _connect(hass, entry, runtime)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Tapo Thing API reconnect failed: %s",
            type(err).__name__,
        )
        return False
    runtime["errors"] = 0
    return True


def _queue_click(
    hass: HomeAssistant,
    runtime: dict[str, Any],
    button: dict[str, Any],
    weight: int,
) -> None:
    key = device_id(button)
    runtime["pending_clicks"][key] = (
        int(runtime["pending_clicks"].get(key, 0)) + weight
    )
    old_task = runtime["flush_tasks"].get(key)
    if old_task is not None and not old_task.done():
        old_task.cancel()
    runtime["flush_tasks"][key] = hass.async_create_task(
        _flush_clicks(hass, runtime, button)
    )


async def _flush_clicks(
    hass: HomeAssistant,
    runtime: dict[str, Any],
    button: dict[str, Any],
) -> None:
    key = device_id(button)
    try:
        await asyncio.sleep(CLICK_WINDOW_SECONDS)
    except asyncio.CancelledError:
        return

    count = int(runtime["pending_clicks"].pop(key, 0))
    runtime["flush_tasks"].pop(key, None)
    if count <= 0:
        return

    action = (
        "triple_click"
        if count >= 3
        else "double_click"
        if count == 2
        else "single_click"
    )
    hass.bus.async_fire(
        PRESS_EVENT_NAME,
        {
            "action": action,
            "click_count": count,
            "device_id": key,
            "model": str(button.get("model") or ""),
            "source": "tapo_thing_event_log",
            "derived": True,
        },
    )
