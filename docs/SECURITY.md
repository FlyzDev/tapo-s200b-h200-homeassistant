# Security and privacy

This integration needs a Tapo account session to read the cloud Event Log.

## Sensitive values

Treat all of these as private:

- Tapo account address
- Tapo account secret
- cloud/session token
- terminal UUID when associated with a real account
- Thing/device identifiers
- Home Assistant config entries and `.storage`
- LAN addresses and household entity names when they identify a private setup

Do not include real values in issues, screenshots, example YAML, tests, or commits.

## Storage

The Home Assistant config flow stores authentication information in Home Assistant's config-entry storage so the integration can reconnect after restart.

That means Home Assistant backups may contain credentials. Protect backups accordingly.

## Logging

The integration intentionally reports error classes/status rather than request headers or authentication values.

If debugging requires a raw server response, sanitize it locally before sharing it. In particular remove authentication headers, account data, Thing IDs, tokens, terminal identifiers, and private network information.

## Repository audit

Before a public release, inspect the entire Git tree for personal strings, credentials, absolute home-directory paths, private IPs, device IDs, and accidentally copied Home Assistant storage.

The certificate bundle in `custom_components/tapo_s200b_cloud/tplink-ca.pem` contains public TP-Link certificate-authority certificates. It is not a user/client key.

## Reporting a security issue

If a finding would expose credentials or another user's private Tapo data, do not paste the secret into a public issue. Describe the affected code path without including the value.
