from __future__ import annotations

from dataclasses import dataclass

from runtime.web.i18n import pill_label


@dataclass(frozen=True)
class _ThemePalette:
    background: str
    panel: str
    border: str
    accent: str
    cta: str
    text: str
    muted: str
    hover: str
    success: str
    error: str
    rule: str


PALETTE = _ThemePalette(
    background="#ffffff",
    panel="#f7f6f3",
    border="#e9e9e7",
    accent="#2383e2",
    cta="#2383e2",
    text="#37352f",
    muted="#787774",
    hover="#efefef",
    success="#0f7b4a",
    error="#c4554d",
    rule="#e0e0e0",
)

# Semantic pill tones: (background, text)
PILL_TONES: dict[str, tuple[str, str]] = {
    "dim": ("#f1f1ef", "#787774"),
    "neutral": ("#f1f1ef", "#37352f"),
    "yellow": ("#fef3d9", "#b87514"),
    "gold": ("#fef3d9", "#b87514"),
    "orange": ("#fdecc8", "#d9730d"),
    "red": ("#fdebec", "#c4554d"),
    "green": ("#e7f3ef", "#0f7b4a"),
    "blue": ("#e7f3f8", "#2383e2"),
    "cyan": ("#e7f3f8", "#2383e2"),
    "magenta": ("#f3eef8", "#9065b0"),
}

TASK_STATE_TONE = {
    "proposed": "dim",
    "ready": "yellow",
    "claimed": "magenta",
    "in_progress": "blue",
    "blocked": "red",
    "done": "green",
    "cancelled": "dim",
}

PRIORITY_TONE = {
    "low": "dim",
    "medium": "yellow",
    "high": "orange",
    "critical": "red",
}

EFFORT_TONE = {
    "low": "dim",
    "medium": "yellow",
    "high": "orange",
}

RISK_TONE = {
    "low": "dim",
    "medium": "yellow",
    "high": "red",
}

TASK_TYPE_TONE = {
    "fix": "cyan",
    "feature": "green",
    "audit_followup": "magenta",
    "doc": "blue",
    "refactor": "yellow",
    "ops": "dim",
}

AUDIT_STATE_TONE = {
    "draft": "dim",
    "published": "green",
    "closed": "blue",
    "superseded": "dim",
}


def css_variables_block() -> str:
    p = PALETTE
    lines = [
        f"  --cf-bg: {p.background};",
        f"  --cf-main: {p.background};",
        f"  --cf-sidebar: {p.panel};",
        f"  --cf-header: {p.panel};",
        f"  --cf-detail-panel: #f7f6f3;",
        f"  --cf-border: {p.border};",
        f"  --cf-border-strong: #d3d1cb;",
        f"  --cf-accent: {p.accent};",
        f"  --cf-cta: {p.cta};",
        f"  --cf-text: {p.text};",
        f"  --cf-muted: {p.muted};",
        f"  --cf-hover: {p.hover};",
        f"  --cf-success: {p.success};",
        f"  --cf-error: {p.error};",
        f"  --cf-rule: {p.rule};",
        "  --app-header-height: 53px;",
        "  --task-detail-width: 320px;",
        "  --sidebar-width: 240px;",
    ]
    for name, (bg, fg) in PILL_TONES.items():
        lines.append(f"  --pill-{name}-bg: {bg};")
        lines.append(f"  --pill-{name}-fg: {fg};")
    return ":root {\n" + "\n".join(lines) + "\n}"


def _pill_class(prefix: str, key: str, tone_map: dict[str, str]) -> str:
    tone = tone_map.get(key, "neutral")
    slug = key.replace("_", "-")
    return f"pill pill-{prefix} pill-{prefix}--{slug} pill-tone--{tone}"


def pill_class_for_task_state(state: str) -> str:
    return _pill_class("state", state, TASK_STATE_TONE)


def pill_class_for_priority(priority: str) -> str:
    return _pill_class("priority", priority, PRIORITY_TONE)


def pill_class_for_effort(effort: str) -> str:
    return _pill_class("effort", effort, EFFORT_TONE)


def pill_class_for_risk(risk: str) -> str:
    return _pill_class("risk", risk, RISK_TONE)


def pill_class_for_task_type(task_type: str) -> str:
    return _pill_class("type", task_type, TASK_TYPE_TONE)


def pill_class_for_audit_state(state: str) -> str:
    return _pill_class("audit", state, AUDIT_STATE_TONE)


