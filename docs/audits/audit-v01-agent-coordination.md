# Auditoría: CapiForge v0.1 — Estado y coordinación de agentes

**Fecha:** 2026-06-19  
**Alcance:** Runtime owner-local, instalación, MCP, skills, persistencia SQLite  
**Objetivo:** Evaluar preparación para que agentes coordinados trabajen sobre un mismo proyecto con skills instaladas y BBDD actualizada al inicio/fin de tarea.

## Hallazgos

### H1 — Núcleo de dominio sólido (OK)
Auditorías y tareas con ciclo de vida completo, claims exclusivos, metadatos de cierre obligatorios y trazabilidad en `task_mutations`. Esquema en `storage/node-schema.sql`.

### H2 — Instalación funcional pero sin entrega de skills (GAP)
`capinstall` instala binary, bootstrap y MCP. No registra skills ni artefacto de automatización OpenCode (Phase 3 pendiente).

### H3 — Superficie MCP desalineada con skills (CRÍTICO)
`tasks_claim` funciona; `tasks_transition` no está en MCP. Skills start/close no pueden completarse vía MCP para tareas del queue `ready`.

### H4 — Flujo lifecycle reconcile operativo (OK)
`audit_create_brief → audit_publish → tasks_reconcile_start → tasks_reconcile_finish` implementado y testeado. Es el camino viable hoy para trabajo nuevo.

### H5 — Agentes sin contrato de datos explícito (GAP)
No hay documentación agente-facing del esquema SQLite, campos JSON, ni reglas de actualización al inicio/fin de tarea.

### H6 — Multi-agente limitado (RIESGO)
Session ID fijo y lease 5 min sin renovación MCP. Viable para un agente; frágil para coordinación concurrente.

## Tareas derivadas

| lifecycle_key | Prioridad | Resumen |
|---------------|-----------|---------|
| `audit/v0.1/mcp-transition-surface` | critical | Exponer `tasks_transition` (o wrappers start/close genéricos) en MCP stdio |
| `audit/v0.1/skills-mcp-alignment` | high | Alinear skills pickup/start/close con superficie MCP real |
| `audit/v0.1/agent-data-layer-doc` | high | Skill/doc de capa de datos: esquema, estados, metadatos, lifecycle_key |
| `audit/v0.1/install-automation` | high | Completar Phase 3: registro determinista de skills en install/update |
| `audit/v0.1/architecture-onboarding` | medium | Documento de arquitectura y estado v0.1 para kickoff del proyecto |
| `audit/v0.1/session-identity` | medium | Mejorar aislamiento de sesión y renovación de lease en MCP |
| `audit/v0.1/seed-audit-tasks` | high | Publicar esta auditoría y crear tareas en BBDD (meta-tarea inicial) |

## Criterios de éxito del objetivo

- [ ] `./capinstall` deja skills + MCP listos sin configuración manual
- [ ] Un agente puede iniciar y cerrar una tarea (queue o lifecycle) solo vía MCP
- [ ] Skills documentan qué actualizar en BBDD al comenzar y finalizar
- [ ] Auditoría publicada con tareas `ready` vinculadas por `lifecycle_key`
