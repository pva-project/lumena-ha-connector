"""Stalna veza Home Assistant → Perfectus i izvršavanje zahtjeva."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_SECRET, CONF_SERVER_URL, CONF_USER_ID, SOCKET_PATH, USER_NAME

_LOGGER = logging.getLogger(__name__)

MAX_MESSAGE = 64 * 1024 * 1024
RETRY_MIN = 5
RETRY_MAX = 60


class LumenaConnection:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._task: asyncio.Task | None = None
        self._refresh_token = None
        self._access_token: str | None = None
        self._access_created = 0.0
        self._stopping = False
        self._socket = None
        self._watch: set[str] = set()
        self._unsub_states = None

    # ------------------------------------------------------------ start/stop

    async def async_start(self) -> None:
        await self._ensure_user()
        self._unsub_states = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_state)
        self._task = self.hass.async_create_background_task(self._run(), "lumena-connector")

    async def async_stop(self) -> None:
        self._stopping = True

        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None

        if self._task is not None:
            self._task.cancel()

    # ------------------------------------------------------------ pristup lokalnom HA

    async def _ensure_user(self) -> None:
        """Sistemski korisnik (admin) samo za konektor; token nikad ne
        napušta Home Assistant."""

        auth = self.hass.auth
        user = None
        user_id = self.entry.data.get(CONF_USER_ID)

        if user_id:
            user = await auth.async_get_user(user_id)

        if user is None:
            user = await auth.async_create_system_user(USER_NAME, group_ids=[GROUP_ID_ADMIN])
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_USER_ID: user.id}
            )

        tokens = list(user.refresh_tokens.values())
        self._refresh_token = tokens[0] if tokens else await auth.async_create_refresh_token(user)

    def _token(self) -> str:
        now = self.hass.loop.time()

        if not self._access_token or now - self._access_created > 15 * 60:
            self._access_token = self.hass.auth.async_create_access_token(self._refresh_token)
            self._access_created = now

        return self._access_token

    def _local_url(self) -> str:
        api = self.hass.config.api
        scheme = "https" if api and api.use_ssl else "http"
        port = api.port if api else 8123

        return f"{scheme}://127.0.0.1:{port}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    # ------------------------------------------------------------ uživo

    @callback
    def _on_state(self, event: Event) -> None:
        """Javi Perfectusu promjenu stanja (samo za entitete koje prati)."""

        entity_id = event.data.get("entity_id")
        ws = self._socket

        if ws is None or ws.closed or entity_id not in self._watch:
            return

        new_state = event.data.get("new_state")
        payload = {
            "type": "state",
            "entity_id": entity_id,
            "state": None if new_state is None else {
                "entity_id": entity_id,
                "state": new_state.state,
                "attributes": dict(new_state.attributes),
                "last_changed": new_state.last_changed.isoformat(),
                "last_updated": new_state.last_updated.isoformat(),
            },
        }

        self.hass.async_create_task(ws.send_str(json.dumps(payload, default=str)))

    # ------------------------------------------------------------ veza

    async def _run(self) -> None:
        delay = RETRY_MIN
        session = async_get_clientsession(self.hass)
        server = str(self.entry.data[CONF_SERVER_URL]).rstrip("/")
        url = server.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + SOCKET_PATH

        while not self._stopping:
            try:
                async with session.ws_connect(url, heartbeat=30, max_msg_size=MAX_MESSAGE) as ws:
                    await ws.send_json({
                        "type": "hello",
                        "secret": self.entry.data[CONF_SECRET],
                        "ha_version": HA_VERSION,
                        "location_name": self.hass.config.location_name,
                    })
                    welcome = await ws.receive_json(timeout=20)

                    if welcome.get("type") != "welcome":
                        _LOGGER.error("Lumena: server je odbio vezu: %s", welcome.get("error"))
                        delay = RETRY_MAX
                        raise ConnectionError("odbijeno")

                    _LOGGER.info("Lumena: povezano sa %s", server)
                    delay = RETRY_MIN
                    self._socket = ws

                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            request = message.json()

                            if request.get("type") == "watch" and "id" not in request:
                                self._watch = set(request.get("entities") or [])
                                continue

                            self.hass.async_create_task(self._answer(ws, request))
                        elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                self._socket = None
                raise
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Lumena: veza prekinuta (%s), ponovo za %s s", exc, delay)

            self._socket = None

            if self._stopping:
                return

            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)

    async def _answer(self, ws, request: dict[str, Any]) -> None:
        request_id = request.get("id")

        try:
            kind = request.get("type")

            if kind == "http":
                result = await self._http(request)
            elif kind == "ws":
                result = await self._ws(request.get("requests") or [])
            elif kind == "upload":
                result = await self._upload(request)
            elif kind == "ping":
                result = {"pong": True}
            else:
                raise ValueError(f"Nepoznat zahtjev: {kind}")

            response = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            response = {"id": request_id, "ok": False, "error": str(exc)[:300]}

        if not ws.closed:
            await ws.send_str(json.dumps(response, default=str))

    async def _http(self, request: dict[str, Any]) -> dict[str, Any]:
        session = async_get_clientsession(self.hass, verify_ssl=False)
        method = str(request.get("method") or "GET").upper()
        path = str(request.get("path") or "/")

        if not path.startswith("/api/"):
            raise ValueError("Dozvoljen je samo /api/ pristup.")

        async with session.request(
            method,
            f"{self._local_url()}{path}",
            headers=self._headers(),
            json=request.get("json"),
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if request.get("binary"):
                body = await response.read()
                return {
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type", "application/octet-stream"),
                    "body_b64": base64.b64encode(body).decode(),
                }

            text = await response.text()

            try:
                body = await response.json(content_type=None) if text else None
            except ValueError:
                body = text

            return {"status": response.status, "body": body}

    async def _ws(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = self._local_url().replace("http", "ws", 1) + "/api/websocket"
        results: dict[int, Any] = {}

        async with session.ws_connect(url, max_msg_size=MAX_MESSAGE) as ws:
            await ws.receive_json(timeout=10)
            await ws.send_json({"type": "auth", "access_token": self._token()})
            auth = await ws.receive_json(timeout=10)

            if auth.get("type") != "auth_ok":
                return {"error": "Lokalni Home Assistant je odbio konektor."}

            for index, item in enumerate(requests, start=1):
                await ws.send_json({**item, "id": index})

            while len(results) < len(requests):
                message = await ws.receive_json(timeout=40)

                if message.get("type") != "result":
                    continue

                if not message.get("success"):
                    error = (message.get("error") or {}).get("message") or "greška"
                    return {"error": error}

                results[int(message["id"])] = message.get("result")

        return {"results": [results.get(index) for index in range(1, len(requests) + 1)]}

    async def _upload(self, request: dict[str, Any]) -> dict[str, Any]:
        session = async_get_clientsession(self.hass, verify_ssl=False)
        form = aiohttp.FormData()
        form.add_field("media_content_id", str(request.get("directory_id") or ""))
        form.add_field(
            "file",
            base64.b64decode(request.get("body_b64") or ""),
            filename=str(request.get("file_name") or "reklama"),
            content_type=str(request.get("content_type") or "application/octet-stream"),
        )

        async with session.post(
            f"{self._local_url()}/api/media_source/local_source/upload",
            headers=self._headers(),
            data=form,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as response:
            text = await response.text()

            try:
                body = await response.json(content_type=None) if text else None
            except ValueError:
                body = text

            return {"status": response.status, "body": body}
