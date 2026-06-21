from __future__ import annotations

from runtime.hub.sync import SYNC_LIGHT_LABELS, SyncLightState, resolve_sync_light_state


def build_sync_indicator(
    *,
    degraded: bool = False,
    pending_routes: int = 0,
    refresh_seconds: int = 0,
) -> dict[str, str]:
    state: SyncLightState = resolve_sync_light_state(
        degraded=degraded,
        pending_routes=pending_routes,
        seconds_since_refresh=0,
        auto_refresh_seconds=refresh_seconds,
        refreshing=False,
    )
    return {
        "state": state,
        "label": SYNC_LIGHT_LABELS[state],
    }


def build_coord_meta(*, degraded: bool = False, pending_routes: int = 0) -> dict[str, str]:
    if pending_routes > 0:
        return {
            "coord_state": "pending",
            "coord_label": f"Coordinador: {pending_routes} rutas pendientes",
        }
    if degraded:
        return {
            "coord_state": "degraded",
            "coord_label": "Coordinador: local-only",
        }
    return {
        "coord_state": "ok",
        "coord_label": "Coordinador: conectado",
    }
