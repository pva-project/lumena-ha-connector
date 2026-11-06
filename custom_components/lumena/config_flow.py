"""Povezivanje sa Perfectusom: adresa servera + jednokratni kod."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CODE, CONF_SECRET, CONF_SERVER_URL, DOMAIN, PAIR_PATH

_LOGGER = logging.getLogger(__name__)


def _clean_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")

    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    return url


class LumenaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            server_url = _clean_url(user_input[CONF_SERVER_URL])
            code = str(user_input[CONF_CODE]).strip().upper()
            session = async_get_clientsession(self.hass)

            try:
                async with session.post(
                    f"{server_url}{PAIR_PATH}",
                    json={"code": code},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    body = await response.json(content_type=None)

                    if response.status == 400:
                        errors["base"] = "invalid_code"
                    elif response.status >= 300 or not isinstance(body, dict) or not body.get("secret"):
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(f"{server_url}")
                        self._abort_if_unique_id_configured(
                            updates={CONF_SERVER_URL: server_url, CONF_SECRET: body["secret"]}
                        )

                        return self.async_create_entry(
                            title=f"Lumena · {body.get('organization') or 'Perfectus'}",
                            data={CONF_SERVER_URL: server_url, CONF_SECRET: body["secret"]},
                        )
            except (aiohttp.ClientError, TimeoutError, ValueError):
                _LOGGER.exception("Lumena: uparivanje nije uspjelo")
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_SERVER_URL, default=(user_input or {}).get(CONF_SERVER_URL, "https://")): str,
                vol.Required(CONF_CODE): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
