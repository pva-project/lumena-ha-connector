"""
Lumena Connector: Home Assistant sam otvara sigurnu vezu prema
Perfectusu (bez Nabu Case i bez otvaranja portova) i izvršava njegove
zahtjeve nad lokalnim Home Assistantom.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .connection import LumenaConnection
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    connection = LumenaConnection(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = connection
    await connection.async_start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    connection: LumenaConnection | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if connection is not None:
        await connection.async_stop()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Brisanje integracije briše i njenog sistemskog korisnika."""

    from .const import CONF_USER_ID

    user_id = entry.data.get(CONF_USER_ID)

    if user_id:
        user = await hass.auth.async_get_user(user_id)
        if user is not None:
            await hass.auth.async_remove_user(user)
