from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rich.text import Text

CONTENT_PADDING = "2 4"
SIDENAV_WIDTH = 30
SIDENAV_PADDING = "1 2"

DEFAULT_THEME = "neon"
THEME_ORDER = ("neon", "notion", "light")


@dataclass(frozen=True)
class ThemePalette:
    name: str
    label: str
    dark: bool
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
    selected_row_style: str
    cta_text_style: str
    task_state_styles: Mapping[str, str]
    priority_styles: Mapping[str, str]
    effort_styles: Mapping[str, str]
    risk_styles: Mapping[str, str]
    task_type_styles: Mapping[str, str]
    audit_state_styles: Mapping[str, str]


def _css_for_palette(palette: ThemePalette) -> str:
    return f"""
Screen {{
    background: {palette.background};
    color: {palette.text};
}}

#layout {{
    height: 1fr;
}}

#sidenav {{
    width: 30;
    background: {palette.panel};
    padding: 1 1;
    border-right: solid {palette.border};
}}

#sidenav-brand {{
    text-style: bold;
    color: {palette.accent};
    margin-bottom: 1;
    padding: 0 1;
}}

.sidenav-action {{
    color: {palette.cta};
    margin-bottom: 1;
    padding: 0 1;
}}

.sidenav-action:hover {{
    background: {palette.hover};
}}

#nav-tree {{
    height: 1fr;
}}

.nav-row {{
    padding: 0 1;
    height: 1;
}}

.nav-row:hover {{
    background: {palette.hover};
}}

.nav-row--active {{
    background: {palette.hover};
    border-left: thick {palette.accent};
    color: {palette.text};
    text-style: bold;
}}

.nav-row--workspace {{
    color: {palette.text};
}}

.nav-row--project {{
    color: {palette.muted};
}}

.nav-row--page {{
    color: {palette.muted};
}}

#content-panel {{
    padding: 1 2;
    height: 1fr;
}}

#content-header {{
    margin-bottom: 0;
    height: auto;
}}

#content-header-top {{
    width: 100%;
    height: auto;
}}

#content-header-left {{
    width: 1fr;
    height: auto;
}}

#title-row {{
    height: 1;
    width: 100%;
}}

#tasks-empty {{
    display: none;
    color: {palette.muted};
    width: 100%;
    padding: 1 0;
    text-align: center;
}}

#tasks-empty.visible {{
    display: block;
}}

#refresh-status {{
    color: {palette.muted};
    width: auto;
    text-align: right;
    content-align: right middle;
}}

#breadcrumb {{
    color: {palette.muted};
    margin-bottom: 0;
}}

#page-title {{
    text-style: bold;
    color: {palette.text};
    width: auto;
}}

#header-rule {{
    color: {palette.accent};
    margin-bottom: 1;
}}

#header-rule.hidden {{
    display: none;
}}

#sidenav.panel-focused {{
    border-right: thick {palette.accent};
}}

#content-panel.panel-focused {{
    border-left: thick {palette.accent};
}}

.nav-row--focused {{
    background: {palette.hover};
    border-left: thick {palette.cta};
    color: {palette.text};
    text-style: bold;
}}

#task-meta {{
    display: none;
    color: {palette.muted};
    width: auto;
    padding-left: 1;
}}

#task-meta.visible {{
    display: block;
}}

#task-filters {{
    height: 1;
    margin-bottom: 1;
}}

#task-filters.hidden {{
    display: none;
}}

#tasks-table {{
    display: none;
    width: 100%;
    height: 1fr;
    min-height: 14;
    overflow-x: hidden;
}}

#tasks-table.visible {{
    display: block;
}}

#content-body.hidden {{
    display: none;
}}

#content-main.hidden {{
    display: none;
}}

#docs-shell {{
    display: none;
    width: 100%;
    height: 1fr;
}}

#docs-shell.visible {{
    display: block;
}}

#docs-index-label {{
    color: {palette.muted};
    margin-bottom: 1;
}}

#docs-list {{
    height: auto;
    max-height: 8;
    margin-bottom: 1;
}}

#docs-detail {{
    width: 100%;
    min-height: 8;
    background: {palette.panel};
    border: thick {palette.accent};
    padding: 1 2;
    margin-top: 1;
}}

#docs-detail-toolbar {{
    width: 100%;
    height: 1;
    margin-bottom: 1;
}}

#docs-detail-title {{
    width: 1fr;
    text-style: bold;
    color: {palette.text};
}}

.docs-nav-btn {{
    width: auto;
    margin-left: 1;
    color: {palette.cta};
    text-style: bold;
}}

.docs-nav-btn.disabled {{
    color: {palette.muted};
    text-style: none;
}}

#docs-detail-scroll {{
    height: 1fr;
    width: 100%;
}}

#docs-detail-content {{
    width: 100%;
    color: {palette.text};
}}

#docs-tasks-section {{
    width: 100%;
    height: auto;
    margin-top: 1;
}}

#docs-tasks-label {{
    color: {palette.muted};
    margin-bottom: 1;
}}

#docs-tasks-list {{
    height: auto;
    max-height: 10;
    overflow-y: auto;
}}

.audit-task-row {{
    padding: 0 1;
    height: 1;
}}

.audit-task-row--selected {{
    background: {palette.hover};
    text-style: bold;
}}

.clickable:hover {{
    background: {palette.hover};
}}

.filter-pill {{
    padding: 0 1;
    height: 1;
}}

.filter-pill--active {{
    background: {palette.hover};
    text-style: bold;
    color: {palette.accent};
}}

.filter-spacer {{
    width: auto;
    height: 1;
}}

.doc-row {{
    padding: 0 1;
    height: 1;
}}

.doc-row--selected {{
    background: {palette.hover};
    border-left: thick {palette.accent};
    text-style: bold;
}}

.doc-section-label {{
    color: {palette.muted};
    margin-top: 1;
}}

.doc-file {{
    color: {palette.muted};
}}

.empty-docs {{
    color: {palette.muted};
}}

#content-body {{
    height: 1fr;
}}

#task-drawer {{
    height: auto;
    max-height: 12;
    overflow-y: auto;
    padding: 0 1;
    border-top: solid {palette.border};
    display: none;
}}

#task-drawer.visible {{
    display: block;
}}

.empty-state {{
    width: 100%;
    height: 100%;
    align: center middle;
    color: {palette.muted};
}}

.empty-state-cta {{
    color: {palette.cta};
    text-style: bold;
    margin-top: 1;
}}

#footer-hints {{
    dock: bottom;
    height: 1;
    color: {palette.muted};
    padding: 0 2;
    background: {palette.panel};
}}

#status-bar {{
    dock: bottom;
    height: 1;
    background: {palette.panel};
    color: {palette.muted};
    padding: 0 2;
}}

#status-bar.success {{
    color: {palette.success};
}}

#status-bar.error {{
    color: {palette.error};
}}

.task-table-header {{
    color: {palette.muted};
    margin-bottom: 1;
}}

.task-table-rule {{
    color: {palette.border};
    margin-bottom: 1;
}}

Screen#startup-splash {{
    background: {palette.background};
    color: {palette.text};
    align: center middle;
}}

#splash-hint {{
    color: {palette.muted};
    margin-top: 1;
    text-align: center;
}}

InputScreen, ModalScreen {{
    background: {palette.background} 80%;
    align: center middle;
}}

.modal-panel {{
    width: 50;
    height: auto;
    background: {palette.panel};
    border: solid {palette.accent};
    padding: 2;
}}

.modal-title {{
    text-style: bold;
    color: {palette.accent};
    margin-bottom: 1;
}}

.modal-hint {{
    color: {palette.muted};
    margin-top: 1;
}}
"""


NEON_PALETTE = ThemePalette(
    name="neon",
    label="Neon",
    dark=True,
    background="#1a1a2e",
    panel="#16213e",
    border="#0f3460",
    accent="#00d4ff",
    cta="#ff00ff",
    text="#e0e0e0",
    muted="#888888",
    hover="#0f3460",
    success="#00ff88",
    error="#ff4444",
    rule="#333355",
    selected_row_style="bold reverse bright_black",
    cta_text_style="bold bright_magenta",
    task_state_styles={
        "proposed": "reverse bright_black",
        "ready": "bold reverse bright_yellow",
        "claimed": "bold reverse bright_magenta",
        "in_progress": "bold reverse bright_blue",
        "blocked": "bold reverse bright_red",
        "done": "bold reverse bright_green",
        "cancelled": "strike dim",
    },
    priority_styles={
        "critical": "bold reverse bright_red",
        "high": "bold reverse orange1",
        "medium": "reverse bright_yellow",
        "low": "reverse bright_black",
    },
    effort_styles={"high": "reverse orange1", "medium": "reverse bright_yellow", "low": "reverse bright_black"},
    risk_styles={"high": "bold reverse bright_red", "medium": "reverse bright_yellow", "low": "reverse bright_black"},
    task_type_styles={
        "fix": "reverse bright_cyan",
        "feature": "reverse bright_green",
        "audit_followup": "reverse bright_magenta",
        "doc": "reverse bright_blue",
        "refactor": "reverse bright_yellow",
        "ops": "reverse bright_black",
    },
    audit_state_styles={
        "draft": "reverse bright_black",
        "published": "bold reverse bright_green",
        "closed": "bold reverse bright_blue",
        "superseded": "strike dim",
    },
)

NOTION_PALETTE = ThemePalette(
    name="notion",
    label="Notion",
    dark=True,
    background="#191919",
    panel="#202020",
    border="#2f2f2f",
    accent="#9b9a97",
    cta="#529cca",
    text="#e3e2e0",
    muted="#7a7a7a",
    hover="#2a2a2a",
    success="#4dab7f",
    error="#d97373",
    rule="#2f2f2f",
    selected_row_style="bold reverse #373737",
    cta_text_style="bold blue",
    task_state_styles={
        "proposed": "dim",
        "ready": "yellow",
        "claimed": "magenta",
        "in_progress": "bold blue",
        "blocked": "red",
        "done": "green",
        "cancelled": "strike dim",
    },
    priority_styles={"critical": "bold red", "high": "orange1", "medium": "yellow", "low": "dim"},
    effort_styles={"high": "orange1", "medium": "yellow", "low": "dim"},
    risk_styles={"high": "bold red", "medium": "yellow", "low": "dim"},
    task_type_styles={
        "fix": "cyan",
        "feature": "green",
        "audit_followup": "magenta",
        "doc": "blue",
        "refactor": "yellow",
        "ops": "dim",
    },
    audit_state_styles={"draft": "dim", "published": "green", "closed": "blue", "superseded": "strike dim"},
)

LIGHT_PALETTE = ThemePalette(
    name="light",
    label="Light",
    dark=False,
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
    selected_row_style="bold reverse #efefef",
    cta_text_style="bold blue",
    task_state_styles={
        "proposed": "dim",
        "ready": "bold dark_orange",
        "claimed": "bold magenta",
        "in_progress": "bold blue",
        "blocked": "bold red",
        "done": "bold green",
        "cancelled": "strike dim",
    },
    priority_styles={"critical": "bold red", "high": "dark_orange", "medium": "gold3", "low": "dim"},
    effort_styles={"high": "dark_orange", "medium": "gold3", "low": "dim"},
    risk_styles={"high": "bold red", "medium": "gold3", "low": "dim"},
    task_type_styles={
        "fix": "blue",
        "feature": "green",
        "audit_followup": "magenta",
        "doc": "cyan",
        "refactor": "gold3",
        "ops": "dim",
    },
    audit_state_styles={"draft": "dim", "published": "bold green", "closed": "bold blue", "superseded": "strike dim"},
)

THEMES: dict[str, ThemePalette] = {
    "neon": NEON_PALETTE,
    "notion": NOTION_PALETTE,
    "light": LIGHT_PALETTE,
}

_active_theme_name = DEFAULT_THEME


def normalize_theme_name(name: str | None) -> str:
    if not name:
        return DEFAULT_THEME
    lowered = name.strip().lower()
    return lowered if lowered in THEMES else DEFAULT_THEME


def theme_names() -> tuple[str, ...]:
    return THEME_ORDER


def active_theme() -> ThemePalette:
    return THEMES[_active_theme_name]


def set_active_theme(name: str) -> ThemePalette:
    global _active_theme_name
    _active_theme_name = normalize_theme_name(name)
    return active_theme()


def next_theme_name(current: str | None = None) -> str:
    current_name = normalize_theme_name(current or _active_theme_name)
    index = THEME_ORDER.index(current_name)
    return THEME_ORDER[(index + 1) % len(THEME_ORDER)]


def css_for_theme(name: str | None = None) -> str:
    return _css_for_palette(THEMES[normalize_theme_name(name)])


APP_CSS = css_for_theme(DEFAULT_THEME)


def labelize(key: str) -> str:
    return key.replace("_", " ").title()


def _lookup(styles: Mapping[str, str], key: str) -> str:
    return styles.get(key, "dim")


def style_for_task_state(state: str) -> str:
    return _lookup(active_theme().task_state_styles, state)


def style_for_priority(priority: str) -> str:
    return _lookup(active_theme().priority_styles, priority)


def style_for_effort(effort: str) -> str:
    return _lookup(active_theme().effort_styles, effort)


def style_for_risk(risk: str) -> str:
    return _lookup(active_theme().risk_styles, risk)


def style_for_task_type(task_type: str) -> str:
    return _lookup(active_theme().task_type_styles, task_type)


def style_for_audit_state(state: str) -> str:
    return _lookup(active_theme().audit_state_styles, state)


def style_for_cta() -> str:
    return active_theme().cta_text_style


def style_for_selected_row() -> str:
    return active_theme().selected_row_style


def render_pill(label: str, style: str) -> Text:
    text = Text()
    text.append(" ", style="")
    text.append(label, style=style)
    text.append(" ", style="")
    return text


def append_pill(text: Text, label: str, style: str, *, spacer: str = "  ") -> Text:
    if len(text) > 0:
        text.append(spacer)
    text.append_text(render_pill(label, style))
    return text
