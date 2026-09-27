# Protocol notes

This document describes the minimum cloud flow used by this repository. It is intended for maintainers and AI coding agents that want to port the technique to another platform.

## Scope

Validated target: a Tapo S200B paired to an H200, with the button's Event Log visible in the Tapo app.

This is an unofficial, undocumented cloud interface. Treat every field and endpoint as changeable.

## 1. Thing API login

The client performs the legacy Tapo Thing login with the account identifier, account secret, app type, and a generated terminal UUID.

The response yields a short-lived cloud token. The token is sensitive and must never be committed, printed in issue logs, or embedded in examples.

## 2. Regional app-server discovery

A signed request asks Tapo for service URLs for the account. The integration selects the service URL for:

```text
nbu.iot-app-server.app-v2
```

The signing constants are application-level values used by the Tapo Android client. They are not unique to a user.

## 3. Thing discovery

Request:

```http
GET {app_server_url}/v2/things
```

with the Thing authorization headers.

The integration filters returned records by model:

```text
S200B
S200D
```

Useful per-device fields include `thingName`, `model`, and one or more app-server URL fields.

Treat `thingName` as a private device/account identifier when sharing diagnostics.

## 4. Event Log

For each supported button:

```http
GET {button_app_server}/v1/things/{url_encoded_thingName}/events
    ?fetchSize=50
    &order=DESC
    &fetchType=normal
```

Observed event records contain fields such as:

```json
{
  "logId": 123456,
  "name": "rotation",
  "timestamp": 1790490001,
  "params": {
    "rotate_deg": 15
  }
}
```

Observed native names:

| Native name | Meaning |
| --- | --- |
| `singleClick` | one native click |
| `doubleClick` | native double-click |
| `rotation` | dial rotation; degrees are read from `params.rotate_deg` |

Positive rotation degrees are treated as clockwise and negative values as anti-clockwise.

Unknown native names should still be emitted on the raw Home Assistant event so new firmware behavior can be discovered without changing the network client first.

## 5. Polling and deduplication

The endpoint is fetched in descending order. The integration converts each `logId` to an integer and uses it as a monotonic high-water mark **per button**.

On the first successful fetch after startup:

```text
baseline = max(current logIds)
emit nothing
```

On later fetches:

```text
fresh = entries where logId > baseline
sort fresh ascending by logId
emit fresh
baseline = max(emitted logId)
```

This seed-on-start rule is essential: without it, restarting Home Assistant can replay historical presses and trigger real automations.

## 6. Home Assistant normalization

`event_parser.py` is deliberately independent of Home Assistant.

`tapo_s200b_event` is the closest public representation of the Event Log entry.

`tapo_s200b_rotated` is a filtered convenience event for rotations.

`tapo_s200b_pressed` is a higher-level derived event. The runtime groups click units in a short window. A native `doubleClick` contributes two click units. Three or more units become the convenience action `triple_click`.

Do not reverse that distinction in documentation.

## 7. Local API note

The existence of a locally discovered H200/S200B device does not prove that physical button events are available through local trigger logs. The H200/S200B system used to develop this integration returned no usable local trigger entries while the Tapo cloud Event Log did.

If a future local transport becomes reliable, it should be implemented as an explicit alternative transport with separate tests and documentation.
