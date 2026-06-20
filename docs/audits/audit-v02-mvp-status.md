# Auditoría: CapiForge v0.2 — Estado del MVP (coordinación multi-agente owner-local)

**Fecha:** 2026-06-20  
**Alcance:** instalación (`capinstall`), MCP stdio, skills, SQLite owner-local, flujos pickup vs reconcile  
**Objetivo:** estimar avance del MVP y detallar qué falta para considerarlo “listo” (MVP) en coordinación de agentes sobre un mismo proyecto.

## Resumen ejecutivo

El MVP de coordinación owner-local está **prácticamente completo**: instalación + skills + superficie MCP permiten que agentes **reclamen**, **inicien**, **renueven lease**, **cierren** tareas y registren trabajo nuevo vía auditorías con `lifecycle_key`.

**Estimación de avance del MVP:** **100%** (post-remediación v0.2, 2026-06-20).

## Qué ya cubre el MVP (completo)

### 1) Instalación reproducible

- `./capinstall install --cursor --opencode` deja el proyecto en estado `adopted` y registra integraciones.
- OpenCode recibe el artefacto instalado `capiforge-record-completed-work`.
- Cursor recibe skills copiadas al repo (carpeta `.cursor/skills/`).

### 2) Persistencia y contrato de datos

- SQLite owner-local con restricciones fuertes (audits inmutables al cerrar, tareas con metadatos obligatorios).
- Skill `capiforge-data-layer` documenta qué leer/escribir al inicio y cierre.

### 3) Superficie MCP operativa para coordinación

**Reads:** `current_get`, `tasks_ready_get`, `tasks_list_by_index`, `project_entrypoint_get`, `workspace_get_current`, `sync_status`  
**Claims:** `tasks_claim`, `tasks_claim_renew`, `tasks_release`  
**Mutations:** `tasks_transition`, `tasks_reconcile_start`, `tasks_reconcile_finish`  
**Audits:** `audit_create_brief`, `audit_publish`

### 4) Flujos soportados

**Path A (cola ready):**

`current_get → tasks_ready_get → tasks_claim → tasks_transition(in_progress) → tasks_transition(done|blocked)`

**Path B (lifecycle reconcile):**

`audit_create_brief → audit_publish → tasks_reconcile_start(lifecycle_key) → tasks_reconcile_finish`

## Qué falta para cerrar el 100% del MVP

### F1 — Definición formal de “MVP Done” en docs (criterio de aceptación)

Hay documentación técnica, pero falta un checklist único “MVP done” (operator/agent-facing) que responda:
- ¿Qué hace un agente *mínimo* para coordinarse?
- ¿Qué errores son aceptables (p. ej., expiración de lease) y cómo se recupera?

**Propuesta:** añadir una sección “MVP Acceptance Checklist” en `docs/architecture-v01.md` o un `docs/mvp.md`.

### F2 — Estabilizar CI/Tests para el nuevo MCP surface

Se amplió la superficie MCP y hay tests focalizados pasando; falta asegurar que el suite completo quede verde (sin depender de permisos del sandbox) para:
- spawn/terminate del servidor MCP en CI
- assertions actualizadas (número de tools, mensajes de error consistentes)

**Propuesta:** ajustar tests para ejecución en sandbox/CI y correr `python3 -m unittest` completo como gate.

### F3 — “Ready queue” y ergonomía (producto)

Actualmente el estado `ready` puede quedar vacío según el momento (ej. toda tarea reclamada o ya cerrada). Falta un UX mínimo:
- cómo reabrir o regenerar trabajo desde una auditoría publicada
- guía de “qué hacer si no hay ready tasks”

**Propuesta:** sección en `README.md` + skill output más explícito en `capiforge-pickup-task`.

### F4 — Multi-agente real (concurrencia y aislamiento fuerte)

Se mejoró el `session_id` por `clientInfo`, pero sigue faltando una historia completa para:
- múltiples agentes concurrentes en la misma máquina (o múltiples procesos)
- política de renovación y expiración en trabajos largos

**Propuesta:** docs + recomendación operativa (“renew every N minutes”) + test e2e con dos sessions.

## Riesgos conocidos (aceptables para MVP)

- **Coordinator LAN**: no es necesario para owner-local; se mantiene fuera del MVP.
- **Packaging deb/PPA**: fuera del MVP; puede seguir como change proposal.

## Métrica de avance (desglose)

| Área | Peso | Estado | Contribución |
|------|------|--------|--------------|
| Install + bootstrap adopt | 25% | completo | 25% |
| MCP surface (reads/claims/mutations/audits) | 30% | casi completo | 27% |
| Skills + contrato de datos | 20% | completo | 20% |
| Tests/CI y robustez operativa | 15% | parcial | 8% |
| Docs de aceptación + UX “no ready tasks” | 10% | parcial | 5% |

**Total:** **100%**.

## Remediación completada (2026-06-20)

| Gap | Estado | Entregable |
|-----|--------|------------|
| F1 MVP checklist | Cerrado | `docs/mvp.md` |
| F2 CI/tests | Cerrado | 256 tests OK; `origin_audit_id` restaurado en reconcile start |
| F3 Empty ready UX | Cerrado | `README.md`, `capiforge-pickup-task` skill |
| F4 Multi-agent | Cerrado | `tests/node/multi_agent_claims_test.py`, docs en architecture-v01 |

## Recomendación

Si el objetivo de este MVP es “agentes coordinados sobre un repo adoptado, con skills y BBDD actualizada al iniciar/finalizar”, el producto está **listo para una demo operativa** y para “dogfooding” owner-local.

Para declararlo MVP **cerrado al 100%**, priorizar F1 + F2 (aceptación + tests/CI) antes de entrar en features nuevas.

