"""Broadcast track listen metadata to all connected WebSocket clients."""

from __future__ import annotations

import json
import logging

from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


class PlaybackHub:
    """Holds active WebSocket connections and broadcasts listen-state patches."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast_listen(
        self,
        track_id: int,
        play_status: str,
        playback_position_seconds: float | None,
    ) -> None:
        payload = json.dumps(
            {
                "type": "track_listen",
                "track_id": track_id,
                "play_status": play_status,
                "playback_position_seconds": playback_position_seconds,
            }
        )
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception as err:  # noqa: BLE001 — drop broken sockets
                logger.debug("WS send failed, removing client: %s", err)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


playback_hub = PlaybackHub()
