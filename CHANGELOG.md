# Changelog

## v0.1.2 — 2026-10-20

### Fixed — HACS review (@frenck)

- Stop polling immediately after rejected Tapo authentication and start Home Assistant's reauthentication flow. Reauthenticate updates and reloads the existing config entry.
- Prevent repeated invalid-password login attempts; use exponential backoff (5–300 seconds) for transient API and network failures.
- Remove the unmanaged diagnostic state; no orphan status sensor remains after unloading the integration. The integration continues to emit Home Assistant event-bus events.
- Catch aiohttp client errors and timeouts during setup and reauthentication, showing a connection error instead of Unknown error.

### Fixed — H200/S200B field testing

- Handle non-monotonic Tapo event log IDs by deduplicating recent event fingerprints per button, instead of dropping new records below an old high-water mark.
- Buffer grouped button presses while Home Assistant automations finish initializing (up to 120 seconds).
- Add legacy event field alongside action on grouped press events for existing local automations.

### Verification

- Expanded unit tests covering authentication, bounded retries, unsorted IDs, startup behavior, multi-button isolation, and event compatibility.
- CI, HACS validation and hassfest must pass before this release is published.
- The event sequencing and startup fixes were derived from a real Home Assistant 2026.9.3 / H200 / S200B installation. The published multi-button integration requires further real-device validation.

## v0.1.1

- Initial submission release.
