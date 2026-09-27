# Tapo S200B/S200D Cloud Events for Home Assistant

Unofficial Home Assistant integration that exposes **Tapo S200B/S200D button presses and dial rotations** by reading the Tapo **Thing Cloud Event Log**.

This project was created because an S200B paired to an **H200 hub** can be visible to Home Assistant/python-kasa while its physical button/rotation events are not exposed as usable local automation triggers.

> Tested primarily with **Tapo H200 + S200B**. S200D uses the same event family and is supported by the discovery/parser code, but hardware/firmware combinations can vary.

## What this does

```text
S200B / S200D
      │
      ▼
    H200
      │
      ▼
Tapo Thing Cloud Event Log
      │  HTTPS polling (~1 s)
      ▼
Home Assistant custom integration
      │
      ├─ tapo_s200b_event      raw normalized event
      ├─ tapo_s200b_pressed    grouped click action
      └─ tapo_s200b_rotated    rotation event
```

This version does **not** require a Tapo Smart Action, an H200 LED toggle trick, Node-RED, MQTT, or a second daemon.

## Important: cloud path, not local trigger logs

The working path in this repository is the Tapo app's cloud Event Log API.

Do not confuse it with python-kasa's local hub trigger-log support. The presence of the H200 and its child button in a local integration does not guarantee that physical click/rotation events are exposed locally.

The relevant cloud sequence is documented in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Installation

### HACS custom repository

1. In HACS, open **Integrations**.
2. Add this repository as a **Custom repository** with category **Integration**.
3. Install **Tapo S200B/S200D Cloud Events**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Search for **Tapo S200B/S200D Cloud Events**.
7. Enter your Tapo account email and password.

### Manual installation

Copy `custom_components/tapo_s200b_cloud` into `/config/custom_components/tapo_s200b_cloud`, restart Home Assistant, and add the integration from **Settings → Devices & services**.

## Home Assistant events

### `tapo_s200b_event`

Fired once for every new Event Log entry recognized by the integration. It preserves the native event name and adds a normalized action.

Common native events observed:

- `singleClick` → `single_click`
- `doubleClick` → `double_click`
- `rotation` → `rotate_clockwise`, `rotate_anti_clockwise`, or `rotation`

Every event includes `device_id`, `model`, `log_id`, `timestamp`, `params`, and `source`.

### `tapo_s200b_rotated`

Fired immediately for native `rotation` entries.

- positive `degrees`: clockwise
- negative `degrees`: anti-clockwise
- zero: direction unavailable/neutral

### `tapo_s200b_pressed`

A convenience event derived from native click entries. Clicks that arrive within the grouping window are combined:

- 1 click → `single_click`
- 2 clicks → `double_click`
- 3 or more click units → `triple_click`

`triple_click` is **derived by this integration**. It is not claimed to be a native Tapo event type.

## Automation examples

Single press:

```yaml
automation:
  - alias: S200B single press example
    triggers:
      - trigger: event
        event_type: tapo_s200b_pressed
        event_data:
          action: single_click
    actions:
      - action: light.toggle
        target:
          entity_id: light.living_room
```

Rotate clockwise:

```yaml
automation:
  - alias: S200B rotate clockwise example
    triggers:
      - trigger: event
        event_type: tapo_s200b_rotated
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.degrees | int > 0 }}"
    actions:
      - action: light.turn_on
        target:
          entity_id: light.living_room
        data:
          brightness_step_pct: 10
```

For several buttons, filter on `device_id`. More examples are in [examples/automations.yaml](examples/automations.yaml).

## Multiple buttons and startup behavior

The integration discovers every supported S200B/S200D in the account and keeps an independent Event Log high-water mark for each one.

On first connection after a Home Assistant/integration restart, the greatest current `logId` for each button is recorded as the baseline. Historical entries are **not replayed** as new button presses. Only entries with a greater `logId` are emitted after the baseline is established.

This prevents automations from firing merely because Home Assistant restarted.

## Latency

The default poll interval is 1 second, plus Tapo cloud propagation and normal network latency. This is intended for human-operated smart-button automations, not hard real-time control.

## Security and privacy

- This repository contains no user account, password, token, actual Thing ID, IP address, phone name, household entity ID, or local filesystem path.
- Credentials are entered through the Home Assistant config flow.
- Home Assistant stores the account secret and current cloud token in config-entry storage; treat Home Assistant backups as sensitive.
- The integration does not intentionally log account secrets or tokens.
- Do not attach your Home Assistant `.storage` directory to public bug reports.
- The bundled `tplink-ca.pem` contains public TP-Link CA certificates, not a client certificate or private key.
- Static application signing values in `cloud.py` are vendor application constants, not per-user credentials.

See [docs/SECURITY.md](docs/SECURITY.md) before sharing logs.

## Limitations

- This is an **unofficial** integration based on behavior used by the Tapo app.
- It requires internet access and Tapo cloud availability.
- TP-Link can change endpoints, authentication rules, event names, or response shapes.
- Initial validation is primarily with an EU Tapo account and an H200 + S200B setup.
- Accounts that require a newer or unsupported MFA login flow may fail to authenticate.
- Event history retention is controlled by Tapo.
- A 1-second poll creates regular cloud requests; use responsibly.

## For developers and AI agents

Start with:

- [AGENTS.md](AGENTS.md) — invariants and implementation rules
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — cloud request sequence and event shapes
- [cloud.py](custom_components/tapo_s200b_cloud/cloud.py) — small reusable async cloud client
- [event_parser.py](custom_components/tapo_s200b_cloud/event_parser.py) — Home Assistant-independent event normalization

If adapting the technique to another automation platform, preserve the startup baseline/high-water-mark behavior and keep credentials outside source code.

## Why this exists

H200 can expose the button as a child device without exposing its physical press/rotation stream through the local integration path. The Tapo mobile app can show an Event Log for the button; this project follows that cloud path and turns new entries into Home Assistant bus events.

The protocol notes are intentionally explicit so another developer—or an AI coding agent—can reproduce the method without access to the original author's Home Assistant installation.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with, endorsed by, or supported by TP-Link/Tapo. Product names and trademarks belong to their respective owners. Undocumented cloud interfaces may change without notice.

## References

- python-kasa supported-device notes: https://python-kasa.readthedocs.io/en/latest/
- python-kasa source: https://github.com/python-kasa/python-kasa
- Prior public documentation of Tapo Android request signing: https://github.com/dimme/tapo-cli

These references do not imply endorsement of this integration.
