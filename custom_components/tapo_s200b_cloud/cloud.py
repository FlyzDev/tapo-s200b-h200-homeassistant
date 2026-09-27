from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

# Legacy Thing login is the path the Tapo app still exposes for Event Log data.
# EU is the path validated by this project. The generic legacy endpoint is kept
# as a fallback because TP-Link account routing varies.
THING_LOGIN_URLS = (
    "https://eu-wap.tplinkcloud.com",
    "https://wap.tplinkcloud.com",
)

# Static Android app signing material. These are vendor application constants,
# not per-user credentials. They have been publicly documented for years.
ACCESS_KEY = "4d11b6b9d5ea4d19a829adbb9714b057"
SIGNING_KEY = "6ed7d97f3e73467f8a5bab90b577ba4c"

THING_APP_TYPE = "Tapo_Android"
THING_APP_VERSION = "3.21.112"
DEFAULT_BUTTON_MODELS = frozenset({"S200B", "S200D"})
THING_SERVICE_IDS = (
    "nbu.iot-app-server.app-v2",
    "nbu.iot-cloud-gateway.app-v2",
    "nbu.iot-security.appdevice-v2",
)


class TapoCloudError(Exception):
    """Base error for the unofficial Tapo Thing Cloud client."""


class TapoTokenExpired(TapoCloudError):
    """Raised when the Thing API rejects an expired token."""


def error_code(obj: Any) -> int:
    if not isinstance(obj, dict):
        return 0
    for key in ("error_code", "errorCode"):
        if key in obj:
            try:
                return int(obj[key])
            except (TypeError, ValueError):
                return 1
    return 0


def build_ssl_context() -> ssl.SSLContext:
    """Trust system roots plus TP-Link cloud roots bundled with the integration."""
    ca_file = Path(__file__).with_name("tplink-ca.pem")
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(ca_file))
    return context


class TapoCloudClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        account: str,
        account_secret: str,
        *,
        terminal_uuid: str | None = None,
        token: str | None = None,
        app_server_url: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.session = session
        self.account = account
        self.account_secret = account_secret
        self.terminal_uuid = terminal_uuid or uuid.uuid4().hex.upper()
        self.token = token
        self.app_server_url = app_server_url or ""
        self.ssl_context = ssl_context or build_ssl_context()

    def _signed_headers(self, body: str, endpoint: str) -> dict[str, str]:
        stamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        content_md5 = base64.b64encode(
            hashlib.md5(body.encode()).digest()
        ).decode()
        payload = (
            content_md5 + "\n" + stamp + "\n" + nonce + "\n" + endpoint
        ).encode()
        signature = hmac.new(
            SIGNING_KEY.encode(),
            payload,
            hashlib.sha1,
        ).digest().hex()
        return {
            "Content-Md5": content_md5,
            "X-Authorization": (
                f"Timestamp={stamp}, Nonce={nonce}, AccessKey={ACCESS_KEY}, "
                f"Signature={signature}"
            ),
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "okhttp/3.12.13",
        }

    def _thing_headers(self) -> dict[str, str]:
        if not self.token:
            raise TapoCloudError("Not authenticated")
        return {
            "Authorization": "ut|" + self.token,
            "app-cid": "app:Tapo_Android:" + self.terminal_uuid,
            "x-app-name": THING_APP_TYPE,
            "x-app-version": THING_APP_VERSION,
            "x-term-id": self.terminal_uuid,
            "x-app-ospf": "Android",
            "x-app-brand": "TPLINK",
            "Content-Type": "application/json",
            "User-Agent": "okhttp/3.12.13",
        }

    async def _signed_post(
        self,
        base_url: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"))
        async with self.session.post(
            base_url + endpoint,
            data=body,
            headers=self._signed_headers(body, endpoint),
            ssl=self.ssl_context,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            raw = await response.text()
        if response.status >= 400:
            raise TapoCloudError(f"Signed request HTTP {response.status}")
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as err:
            raise TapoCloudError("Invalid signed cloud response") from err
        code = error_code(envelope)
        if code:
            raise TapoCloudError(f"Signed cloud error {code}")
        result = envelope.get("result")
        return result if isinstance(result, dict) else {}

    async def _legacy_login(self, base_url: str) -> str:
        payload = {
            "method": "login",
            "params": {
                "appType": THING_APP_TYPE,
                "cloudUserName": self.account,
                "cloudPassword": self.account_secret,
                "terminalUUID": self.terminal_uuid,
            },
        }
        async with self.session.post(
            base_url,
            json=payload,
            ssl=self.ssl_context,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            raw = await response.text()
        if response.status >= 400:
            raise TapoCloudError(f"Thing login HTTP {response.status}")
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as err:
            raise TapoCloudError("Invalid Thing login response") from err
        code = error_code(envelope)
        if code:
            raise TapoCloudError(f"Thing login error {code}")
        result = envelope.get("result")
        if not isinstance(result, dict) or not result.get("token"):
            raise TapoCloudError("Thing login returned no token")
        return str(result["token"])

    async def _discover_app_server(self, base_url: str) -> str:
        endpoint = "/api/v2/common/getAppServiceUrlByCloudUserName"
        result = await self._signed_post(
            base_url,
            endpoint,
            {
                "cloudUserName": self.account,
                "serviceIds": list(THING_SERVICE_IDS),
            },
        )
        services = result.get("serviceList") or []
        service_url = next(
            (
                item.get("serviceUrl")
                for item in services
                if isinstance(item, dict)
                and item.get("serviceId") == "nbu.iot-app-server.app-v2"
            ),
            None,
        )
        if not service_url:
            raise TapoCloudError("Thing app server not found")
        return str(service_url)

    async def login_thing_api(self) -> dict[str, str]:
        """Authenticate and discover the regional Thing app server."""
        failures: list[str] = []
        for base_url in THING_LOGIN_URLS:
            try:
                token = await self._legacy_login(base_url)
                app_server_url = await self._discover_app_server(base_url)
            except (aiohttp.ClientError, TapoCloudError) as err:
                failures.append(f"{base_url}: {type(err).__name__}")
                continue
            self.token = token
            self.app_server_url = app_server_url
            return {
                "token": token,
                "appServerUrl": app_server_url,
            }
        raise TapoCloudError(
            "Thing login/service discovery failed on all known endpoints: "
            + ", ".join(failures)
        )

    async def list_things(self) -> list[dict[str, Any]]:
        if not self.token or not self.app_server_url:
            raise TapoCloudError("Not authenticated")
        params = {
            "page": 0,
            "pageSize": 200,
            "includeKasaShareDevices": "false",
            "includePcDevice": "false",
            "includeMatterDevice": "false",
            "includeExternalVendorDeviceInfo": "false",
        }
        async with self.session.get(
            self.app_server_url + "/v2/things",
            params=params,
            headers=self._thing_headers(),
            ssl=self.ssl_context,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            raw = await response.text()
        if response.status in (401, 403):
            raise TapoTokenExpired("Thing token expired")
        if response.status >= 400:
            raise TapoCloudError(f"Thing list HTTP {response.status}")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as err:
            raise TapoCloudError("Invalid Thing list response") from err
        code = error_code(result)
        if code:
            raise TapoCloudError(f"Thing list error {code}")
        things = result.get("data") or []
        return [item for item in things if isinstance(item, dict)]

    async def discover_buttons(
        self,
        models: frozenset[str] = DEFAULT_BUTTON_MODELS,
    ) -> list[dict[str, Any]]:
        things = await self.list_things()
        buttons = [
            item
            for item in things
            if str(item.get("model") or "").upper() in models
        ]
        if not buttons:
            supported = ", ".join(sorted(models))
            raise TapoCloudError(f"No supported button found ({supported})")
        return buttons

    async def thing_events(
        self,
        button: dict[str, Any],
        *,
        fetch_size: int = 50,
    ) -> list[dict[str, Any]]:
        if not self.token:
            raise TapoCloudError("Not authenticated")
        thing_name = str(button.get("thingName") or "")
        if not thing_name:
            raise TapoCloudError("Button Thing name is missing")
        base_url = str(
            button.get("appServerUrlV2")
            or button.get("appServerUrlRenewal")
            or button.get("appServerUrl")
            or self.app_server_url
        )
        params = {
            "fetchSize": fetch_size,
            "order": "DESC",
            "fetchType": "normal",
        }
        endpoint = f"/v1/things/{quote(thing_name, safe='')}/events"
        async with self.session.get(
            base_url + endpoint,
            params=params,
            headers=self._thing_headers(),
            ssl=self.ssl_context,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            raw = await response.text()
        if response.status in (401, 403):
            raise TapoTokenExpired("Thing token expired")
        if response.status >= 400:
            raise TapoCloudError(f"Thing events HTTP {response.status}")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as err:
            raise TapoCloudError("Invalid Thing event response") from err
        code = error_code(result)
        if code:
            raise TapoCloudError(f"Thing event error {code}")
        events = result.get("events") or []
        return [item for item in events if isinstance(item, dict)]
