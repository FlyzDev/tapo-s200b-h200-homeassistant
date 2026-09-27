from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import TapoCloudClient, TapoCloudError, build_ssl_context
from .const import (
    CONF_ACCOUNT,
    CONF_APP_SERVER_URL,
    CONF_SECRET,
    CONF_TERMINAL_UUID,
    CONF_TOKEN,
    DOMAIN,
)


class TapoS200BCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            account = str(user_input[CONF_ACCOUNT]).strip()
            account_secret = str(user_input[CONF_SECRET])
            ssl_context = await self.hass.async_add_executor_job(
                build_ssl_context
            )
            client = TapoCloudClient(
                async_get_clientsession(self.hass),
                account,
                account_secret,
                ssl_context=ssl_context,
            )
            try:
                await client.login_thing_api()
                await client.discover_buttons()
            except TapoCloudError:
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
                vol.Required(CONF_SECRET): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
