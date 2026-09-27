# Contributing

Bug reports and compatibility reports are welcome.

Please include Home Assistant version, hub model, button model, region if relevant, and the integration error class/status.

Do **not** publish account identifiers, account secrets, tokens, Thing IDs, Home Assistant `.storage` contents, or complete request headers.

For new event types, a sanitized sample should keep only the fields needed to understand the event shape. Replace real device identifiers with `REDACTED_THING_ID`.

Before opening a pull request, run:

```bash
python3 -m compileall custom_components tests
python3 -m unittest discover -s tests -v
```
