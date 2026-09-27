# AGENTS.md

This file is for coding agents and maintainers working on this repository.

## Project goal

Expose Tapo S200B/S200D click and rotation events to Home Assistant when the button is paired through a Tapo hub such as H200.

The proven transport in this repository is **Tapo Thing Cloud Event Log polling**.

## Do not make this incorrect assumption

Do not infer that local button alerts work just because python-kasa can discover the H200, can discover the S200B/S200D child, or contains a TriggerLogs module.

For the H200/S200B setup that motivated this project, local trigger-log polling returned no event entries after physical button activity while the cloud Event Log contained them.

If a future firmware/library version gains a reliable local source, add it as a separate transport rather than silently changing this cloud integration.

## Critical invariants

1. **Never replay history on startup.** Seed each button at the greatest current `logId`; emit only IDs greater than that baseline.
2. **Track each button independently.** Multiple buttons can have unrelated log streams.
3. **Never commit or log private values.** Real account addresses, account secrets, cloud tokens, Thing IDs, IPs, Home Assistant storage dumps, phone names, and household entity IDs do not belong here.
4. **Preserve raw semantics.** Native names currently observed are `singleClick`, `doubleClick`, and `rotation`.
5. **Treat triple-click as derived.** `triple_click` comes from the Home Assistant grouping layer, not a claimed native Tapo event.
6. **Keep unknown events observable.** Normalize them as `action: unknown` instead of discarding them.
7. **Do not leak authentication material in exceptions.** Avoid dumping request headers, config entries, or full storage records.

## Cloud flow

1. Authenticate to the legacy Thing API.
2. Discover the regional app-server URL.
3. Fetch the account Thing list.
4. Select S200B/S200D records.
5. Fetch each button's Event Log.
6. Sort fresh entries by `logId`.
7. Normalize and emit them.

See `docs/PROTOCOL.md` for the request/response sequence.

## File boundaries

`cloud.py` should remain a small asynchronous network client.

`event_parser.py` must remain importable without Home Assistant so it can be reused by tests, scripts, MQTT bridges, Node-RED bridges, or other platforms.

Home Assistant lifecycle/event-bus behavior belongs in `__init__.py` and setup UI behavior belongs in `config_flow.py`.

## Testing

At minimum run:

```bash
python3 -m compileall custom_components tests
python3 -m unittest discover -s tests -v
```

Before publishing, inspect the repository for private data, absolute home paths, real email addresses, LAN addresses, Home Assistant notification/entity names, tokens, or storage exports.

## Example values

Use placeholders such as:

- `user@example.com`
- `REDACTED_THING_ID`
- `light.living_room`

Never copy real values from a Home Assistant registry, config entry, log, or packet capture into documentation or tests.
