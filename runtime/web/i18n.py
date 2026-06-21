from __future__ import annotations

import re

ENTITY_LABELS: dict[str, str] = {
    "proposed": "Propuesta",
    "ready": "Lista",
    "claimed": "Reclamada",
    "in_progress": "En progreso",
    "blocked": "Bloqueada",
    "done": "Hecha",
    "cancelled": "Cancelada",
    "low": "Baja",
    "medium": "Media",
    "high": "Alta",
    "critical": "Crítica",
    "fix": "Corrección",
    "feature": "Funcionalidad",
    "audit_followup": "Seguimiento",
    "doc": "Documentación",
    "refactor": "Refactor",
    "ops": "Operaciones",
    "draft": "Borrador",
    "published": "Publicada",
    "closed": "Cerrada",
    "superseded": "Reemplazada",
}

TASK_ACTION_LABELS: dict[str, str] = {
    "claim": "Reclamar",
    "start": "Iniciar",
    "block": "Bloquear",
    "done": "Completar",
    "release": "Liberar",
}

FIELD_LABELS: dict[str, str] = {
    "priority": "Prioridad",
    "state": "Estado",
    "task_type": "Tipo",
    "task type": "Tipo",
    "effort": "Esfuerzo",
    "risk": "Riesgo",
}

PAGE_TYPE_TITLES: dict[str, str] = {
    "purpose": "Propósito",
    "architecture": "Arquitectura",
    "custom": "Página personalizada",
}

_MESSAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Task claimed\.$"), "Tarea reclamada."),
    (re.compile(r"^Claim released\.$"), "Reclamación liberada."),
    (re.compile(r"^Task moved to in progress\.$"), "Tarea en progreso."),
    (re.compile(r"^Task moved to blocked\.$"), "Tarea bloqueada."),
    (re.compile(r"^Task moved to done\.$"), "Tarea completada."),
    (re.compile(r"^Task moved to ready\.$"), "Tarea marcada como lista."),
    (re.compile(r"^Task moved to claimed\.$"), "Tarea reclamada."),
    (re.compile(r"^Task moved to proposed\.$"), "Tarea marcada como propuesta."),
    (re.compile(r"^Task moved to cancelled\.$"), "Tarea cancelada."),
    (re.compile(r"^Task '(.+)' created\.$"), r"Tarea «\1» creada."),
    (re.compile(r"^Updated ([a-z_ ]+)\.$"), None),
    (re.compile(r"^Task description is required\.$"), "La descripción de la tarea es obligatoria."),
    (re.compile(r"^Project page saved\.$"), "Página del proyecto guardada."),
    (re.compile(r"^Project not found\.$"), "Proyecto no encontrado."),
    (re.compile(r"^Task not found in project\.$"), "Tarea no encontrada en el proyecto."),
    (re.compile(r"^Publish an audit before creating tasks\.$"), "Publica una auditoría antes de crear tareas."),
    (re.compile(r"^Claim registry unavailable\.$"), "Registro de reclamaciones no disponible."),
    (re.compile(r"^No active claim for this task\.$"), "No hay reclamación activa para esta tarea."),
    (re.compile(r"^Use Claim or Start for that state\.$"), "Usa Reclamar o Iniciar para ese estado."),
    (re.compile(r"^Invalid task field or value\.$"), "Campo o valor de tarea no válido."),
    (re.compile(r"^Invalid task field\.$"), "Campo de tarea no válido."),
    (re.compile(r"^Invalid page type\.$"), "Tipo de página no válido."),
    (re.compile(r"^Invalid priority: (.+)\.$"), r"Prioridad no válida: \1."),
    (re.compile(r"^Invalid task type: (.+)\.$"), r"Tipo de tarea no válido: \1."),
    (re.compile(r"^Invalid initial state: (.+)\.$"), r"Estado inicial no válido: \1."),
    (re.compile(r"^Bootstrap not adopted\.$"), "El proyecto no está adoptado."),
    (re.compile(r"^Unknown action\.$"), "Acción desconocida."),
)


def pill_label(key: str) -> str:
    if key in ENTITY_LABELS:
        return ENTITY_LABELS[key]
    normalized = key.replace("_", " ")
    if normalized in ENTITY_LABELS:
        return ENTITY_LABELS[normalized]
    return normalized.title()


def task_action_label(action: str) -> str:
    return TASK_ACTION_LABELS.get(action, action.title())


def audit_count_label(count: int) -> str:
    if count == 1:
        return "1 auditoría"
    return f"{count} auditorías"


def linked_task_count_label(count: int) -> str:
    if count == 1:
        return "1 tarea"
    return f"{count} tareas"


def translate_ui_message(message: str) -> str:
    if message.startswith("Error: "):
        return f"Error: {translate_ui_message(message[7:])}"
    for pattern, replacement in _MESSAGE_PATTERNS:
        match = pattern.fullmatch(message)
        if not match:
            continue
        if replacement is None:
            field_key = match.group(1).strip().replace(" ", "_")
            label = FIELD_LABELS.get(field_key) or FIELD_LABELS.get(match.group(1).strip()) or match.group(1).strip()
            return f"{label} actualizado."
        return pattern.sub(replacement, message)
    return message
