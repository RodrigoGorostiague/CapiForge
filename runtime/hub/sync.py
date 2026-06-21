from __future__ import annotations

from typing import Literal

SyncLightState = Literal["ok", "degraded", "pending", "stale", "refreshing"]

SYNC_LIGHT_LABELS: dict[SyncLightState, str] = {
    "ok": "Sync OK",
    "degraded": "Local-only",
    "pending": "Rutas pendientes",
    "stale": "Datos desactualizados",
    "refreshing": "Actualizando",
}


def resolve_sync_light_state(
    *,
    degraded: bool,
    pending_routes: int,
    seconds_since_refresh: int,
    auto_refresh_seconds: int,
    refreshing: bool,
) -> SyncLightState:
    if refreshing:
        return "refreshing"
    if pending_routes > 0:
        return "pending"
    if degraded:
        return "degraded"
    if auto_refresh_seconds > 0 and seconds_since_refresh > auto_refresh_seconds:
        return "stale"
    return "ok"
