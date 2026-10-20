from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import (
    TapoAuthenticationError,
    TapoCloudClient,
    TapoCloudError,
    build_ssl_context,
)
from .const import (
    CONF_ACCOUNT,
    CONF_APP_SERVER_URL,
    CONF_SECRET,
    CONF_TERMINAL_UUID,
    CONF_TOKEN,
    DOMAIN,
)


PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


class TapoS200BCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate_client(
        self, account: str, secret: str, *, terminal_uuid: str | None = None
    ) -> TapoCloudClient:
        ssl_context = await self.hass.async_add_executor_job(build_ssl_context)
        client = TapoCloudClient(
            async_get_clientsession(self.hass),
            account,
            secret,
            terminal_uuid=terminal_uuid,
            ssl_context=ssl_context,
        )
        await client.login_thing_api()
        await client.discover_buttons()
        return client

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            account = str(user_input[CONF_ACCOUNT]).strip()
            account_secret = str(user_input[CONF_SECRET])
            try:
                client = await self._validate_client(account, account_secret)
            except TapoAuthenticationError:
                errors["base"] = "invalid_auth"
            except (TapoCloudError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    hashlib.sha256(account.lower().encode()).hexdigest()
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Tapo S200B/S200D Cloud Events",
                    data={
                        CONF_ACCOUNT: account,
                        CONF_SECRET: account_secret,
                        CONF_TERMINAL_UUID: client.terminal_uuid,
                        CONF_TOKEN: str(client.token or ""),
                        CONF_APP_SERVER_URL: client.app_server_url,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.EMAIL
                    )
                ),
                vol.Required(CONF_SECRET): PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ):
        """Ask for new credentials after the cloud rejects authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        """Validate the new password and safely reload the existing entry."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            secret = str(user_input[CONF_SECRET])
            try:
                client = await self._validate_client(
                    str(entry.data[CONF_ACCOUNT]),
                    secret,
                    terminal_uuid=entry.data.get(CONF_TERMINAL_UUID),
                )
            except TapoAuthenticationError:
                errors["base"] = "invalid_auth"
            except (TapoCloudError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                account = str(entry.data[CONF_ACCOUNT]).strip()
                await self.async_set_unique_id(
                    hashlib.sha256(account.lower().encode()).hexdigest()
                )
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_SECRET: secret,
                        CONF_TERMINAL_UUID: client.terminal_uuid,
                        CONF_TOKEN: str(client.token or ""),
                        CONF_APP_SERVER_URL: client.app_server_url,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_SECRET): PASSWORD_SELECTOR}),
            errors=errors,
        )
