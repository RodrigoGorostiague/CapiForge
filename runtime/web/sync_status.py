from __future__ import annotations

import json

from runtime.tui.view import SYNC_LIGHT_LABELS, SyncLightState, resolve_sync_light_state


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
