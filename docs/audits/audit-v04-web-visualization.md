# Audit: CapiForge v0.4 — Web visualization and Spanish content

**Date:** 2026-06-21  
**Parent:** [audit-v04-expanded-hub.md](audit-v04-expanded-hub.md)  
**Scope:** CapiForge web UI — task detail, home dashboard, Spanish-facing content  
**Owner:** equipo local (fixes de visualización, no hub v0.4 core)

## Summary

Fase autodescriptiva: pulir cómo se muestran los datos en la web de CapiForge y alinear el contenido visible con español. El hub v0.4 sigue en paralelo; aquí solo fixes de presentación y idioma.

## Scope

| Área | Objetivo |
|------|----------|
| Detalle de tarea | Campos legibles, metadatos útiles, acciones y etiquetas en español |
| Inicio | Resumen del proyecto, cola y recientes sin ruido técnico innecesario |
| Contenido en español | UI restante + criterio para auditorías y tareas nuevas en español |

## Derived tasks (`audit/v0.4/web/*`)

| lifecycle_key | Priority | Description |
|---------------|----------|-------------|
| `audit/v0.4/web/task-detail-data` | high | Panel de detalle: datos estructurados, auditoría vinculada, acciones en español |
| `audit/v0.4/web/home-dashboard` | high | Página de inicio: resumen, cola y contexto del proyecto más claro |
| `audit/v0.4/web/spanish-content` | medium | Etiquetas, mensajes y guía de contenido en español para entradas a CapiForge |

## Content policy (Spanish)

- **UI:** all user-visible labels, buttons, toasts, and empty states in Spanish (`runtime/web/i18n.py`).
- **New audits and tasks:** titles and descriptions in Spanish; technical identifiers (`lifecycle_key`, paths) stay as-is.
- **Repo docs:** long-form technical docs may stay in English; product-facing audit briefs in CapiForge prefer Spanish.

## Success criteria

- Detalle de tarea muestra información accionable sin depender de IDs crudos.
- Inicio comunica estado del proyecto y cola de un vistazo.
- Cadenas visibles al usuario y contenido nuevo (audits/tasks) en español.

## References

- [audit-v04-expanded-hub.md](audit-v04-expanded-hub.md)
- [runtime/web/templates/partials/task_detail.html](../../runtime/web/templates/partials/task_detail.html)
- [runtime/web/templates/home.html](../../runtime/web/templates/home.html)
