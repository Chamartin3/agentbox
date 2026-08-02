# API REST y WebSocket

AgentBox expone una API REST (más un stream WebSocket) bajo `/api`, servida en
el puerto `8765`. El servicio es FastAPI, por lo que se genera en vivo una
**referencia interactiva y siempre actualizada**:

| URL | Qué |
|---|---|
| `/docs` | Swagger UI: prueba cada endpoint en el navegador |
| `/openapi.json` | Esquema OpenAPI legible por máquina |

Convenciones usadas más abajo: los parámetros de ruta van entre `{llaves}`; todos los cuerpos son JSON
(`content-type: application/json`) salvo que se indique lo contrario; las marcas de tiempo son cadenas
ISO-8601; algunos campos almacenados (`composition_snapshot`, `variables`,
`validation_errors`) se devuelven como **cadenas codificadas en JSON**, no como objetos anidados.

---

## Ejecuciones

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/api/runs` | Crear una ejecución (asíncrona; devuelve `run_id`) |
| `GET` | `/api/runs` | Listar ejecuciones; filtros + paginación |
| `GET` | `/api/runs/_stats` | Estadísticas agregadas de ejecuciones |
| `GET` | `/api/runs/_facets` | Facetas de filtro disponibles |
| `GET` | `/api/runs/{run_id}` | Obtener una ejecución |
| `GET` | `/api/runs/{run_id}/prompt` | Prompt ensamblado, fragmento por fragmento |
| `GET` | `/api/runs/{run_id}/transcript` | Todos los eventos de la transcripción |
| `WS` | `/api/runs/{run_id}/stream` | Stream de eventos en vivo (reproduce si ya terminó) |
| `POST` | `/api/runs/{run_id}/cancel` · `/rerun` | Cancelar / volver a ejecutar |
| `POST` | `/api/runs/{run_id}/complete` · `/snapshot` · `/post_outcome` | Callbacks del backend |
| `GET` `POST` | `/api/runs/{run_id}/comments` | Listar / añadir comentarios |
| `PUT` `DELETE` | `/api/runs/{run_id}/rating` | Establecer / borrar una valoración de 0 a 5 |

### Crear una ejecución

`POST /api/runs`. Solo `agent` es obligatorio; todo lo demás es opcional. `input`
lanza una ejecución headless; omítelo para una sesión interactiva. Fija la ejecución con
`runner_profile` (o `backend`); de lo contrario, se resuelve por el perfil vinculado del agente y, luego,
el predeterminado del sistema.

```json title="Request body"
{
  "agent": "research-analyst",
  "input": "Summarize this abstract on retrieval-augmented generation: ...",
  "runner_profile": "ollama",
  "variables": { "audience": "execs" },
  "workspace": "research",
  "timeout_seconds": 900,
  "webhook_url": "https://your-service.example.com/hooks/agentbox",
  "fresh_workspace": false,
  "session_mode": "headless"
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `agent` | string | **obligatorio**; id del agente |
| `input` | string | Entrada del prompt; omitir para interactivo |
| `variables` | object | Sustituciones `{{var}}` en el prompt |
| `session_id` | string | Reanudar una sesión existente |
| `workspace` | string | Espacio de trabajo con nombre; el predeterminado es efímero |
| `timeout_seconds` | int | Override por ejecución del timeout del runner del agente |
| `webhook_url` | string | Callback de finalización para esta ejecución |
| `backend` | string | Forzar un backend (`opencode`, `claude_code`, ...) |
| `runner_profile` | string | Forzar un perfil de runner (prevalece sobre el del agente) |
| `runner_config` | object | Overrides ad-hoc del runner |
| `fresh_workspace` | bool | Forzar un espacio de trabajo efímero limpio |
| `session_mode` | `"headless"` `"persistent"` | Modo de ejecución |

```json title="200 Response"
{ "run_id": "run-abc123", "agent": "research-analyst" }
```

Errores: `404` agente desconocido · `403` `{"code":"agent_disabled",...}` · `422`
entrada inválida · `503` ningún backend disponible.


### Obtener una ejecución

`GET /api/runs/{run_id}` → la ejecución más su uso.

```json title="200 Response"
{
  "run": {
    "id": "run-abc123",
    "agent_id": "research-analyst",
    "session_id": null,
    "status": "ok",
    "input": "Summarize this abstract ...",
    "output": "Summary: ...",
    "error": null,
    "created_at": "2026-08-02T10:15:04Z",
    "finished_at": "2026-08-02T10:15:12Z",
    "agent_version_id": 12,
    "runner_profile_id": "ollama",
    "validation_status": "ok",
    "validation_errors": null,
    "conversation_format": "opencode",
    "variables": "{\"audience\": \"execs\"}",
    "composition_snapshot": "{...}"
  },
  "usage": {
    "model": "ollama:llama3",
    "input_tokens": 4200,
    "output_tokens": 640,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "cost_usd": 0.0,
    "duration_ms": 8010
  }
}
```

`status` es uno de `queued`, `running`, `ok`, `error`, `timeout`, `cancelled`.
`usage` es `null` hasta que el backend lo reporta.

### Listar ejecuciones

`GET /api/runs` con parámetros de query: `agent`, `status`, `executor`, `agent_version`,
`q`, `since`, `until`, `limit` (por defecto 50), `offset`, `paginated`.

```json title="200 Response (paginated=true)"
{
  "items": [
    {
      "id": "run-abc123",
      "agent_id": "research-analyst",
      "status": "ok",
      "created_at": "2026-08-02T10:15:04Z",
      "finished_at": "2026-08-02T10:15:12Z",
      "agent_version": 3,
      "reported_model": "ollama:llama3",
      "cost_usd": 0.0,
      "duration_ms": 8010,
      "rating": 4
    }
  ],
  "total": 1,
  "offset": 0,
  "limit": 50,
  "has_more": false
}
```

Sin `paginated=true`, la respuesta es un array plano de los mismos elementos.

### Estadísticas de ejecuciones

`GET /api/runs/_stats` (mismos parámetros de filtro que el listado) → agregados.

```json title="200 Response"
{
  "totals": { "runs": 30, "input_tokens": 126000, "output_tokens": 19200, "cost_usd": 3.71, "avg_duration_ms": 8450 },
  "by_agent":  [ { "agent_id": "research-analyst", "runs": 30, "tokens": 145200, "cost_usd": 3.71 } ],
  "by_model":  [ { "model": "ollama:llama3", "runs": 18, "tokens": 80100, "cost_usd": 0.0 } ],
  "by_version":[ { "version": 3, "runs": 12, "tokens": 60000 } ],
  "by_status": [ { "status": "ok", "runs": 28 }, { "status": "error", "runs": 2 } ],
  "timeseries":[ { "bucket": "2026-08-01", "runs": 10, "cost_usd": 1.2 } ]
}
```

### Valorar y comentar

```json title="PUT /api/runs/{run_id}/rating"
{ "rating": 4 }
```

```json title="POST /api/runs/{run_id}/comments"
{ "author": "you@example.com", "body": "Good summary, missed one finding." }
```

```json title="Comment 200 Response"
{ "id": 7, "run_id": "run-abc123", "author": "you@example.com", "body": "Good summary, missed one finding.", "created_at": "2026-08-02T10:20:00Z" }
```

`DELETE /api/runs/{run_id}/rating` borra la valoración.

### Hacer streaming de una ejecución

`WS /api/runs/{run_id}/stream`: conéctate y recibe eventos JSON. En vivo mientras
se ejecuta; reproducido desde la transcripción si la ejecución ya terminó.

```json title="Events (one JSON object per message)"
{"type": "thinking", "run_id": "run-abc123", "text": "Reading the abstract..."}
{"type": "tool_call", "tool": "fs.read", "arguments": {"path": "paper.md"}}
{"type": "text", "role": "assistant", "text": "Summary: ...", "delta": true}
{"type": "validation", "ok": true, "attempt": 1, "mode": "strict"}
{"type": "usage", "input_tokens": 4200, "output_tokens": 640, "cost_usd": 0.0}
{"type": "done", "ok": true, "status": "ok"}
```

Valores de `type` de evento: `text`, `thinking`, `tool_call`, `tool_result`, `usage`,
`validation`, `retry`, `timeout`, `log`, `done`.

---

## Agentes

| Método | Ruta | Propósito |
|---|---|---|
| `GET` `POST` | `/api/agents` | Listar / crear |
| `GET` `PATCH` `DELETE` | `/api/agents/{agent_id}` | Obtener / actualizar / eliminar |
| `POST` | `/api/agents/{agent_id}/enable` · `/disable` | Alternar disponibilidad |
| `PATCH` | `/api/agents/{agent_id}/workspace` | Establecer espacio de trabajo |
| `GET` `PATCH` `DELETE` | `/api/agents/{agent_id}/runner-profile` | Obtener / vincular / desvincular perfil |
| `GET` `PUT` | `/api/agents/{agent_id}/validation` | Validación de entrada y salida |
| `GET` `PUT` | `/api/agents/{agent_id}/prompt` | Leer / editar el prompt |
| `GET` | `/api/agents/{agent_id}/prompt/versions[/{version}]` | Versiones del prompt |
| `POST` | `/api/agents/{agent_id}/prompt/rollback` | Revertir el prompt |
| `GET` | `/api/agents/{agent_id}/versions[/{version}]` | Versiones del agente |
| `GET` | `/api/agents/{agent_id}/versions/{a}/diff/{b}` | Comparar versiones |
| `POST` | `/api/agents/{agent_id}/versions/{version}/rollback` · `/publish` | Revertir / publicar |
| `POST` `DELETE` | `/api/agents/{agent_id}/versions/{version}/files[/{file_id}]` | Archivos de versión |
| `GET` `POST` `DELETE` | `/api/agents/{agent_id}/tool_grants[/{tool}]` | Concesiones de herramientas |
| `POST` `DELETE` | `/api/agents/{agent_id}/forbidden_tools[/{tool}]` | Herramientas prohibidas |
| `GET` | `/api/agents/{agent_id}/effective_tools` | Allow/deny resuelto |
| `GET` | `/api/agent_tools[/{tool_name}]` | Descubrir herramientas |

### Crear un agente

`POST /api/agents` → `201`. Obligatorios: `id`, `description`, `runner`, `author`,
`changelog` (≥3 caracteres). `runner` es una especificación de runner: pasa `{}` para los valores predeterminados.

```json title="Request body"
{
  "id": "research-analyst",
  "description": "Summarizes research papers into structured output",
  "prompt": "You are a research analyst. Produce a concise, structured summary.",
  "runner": { "timeout_seconds": 1200, "max_validation_retries": 2 },
  "composition": { "output_validation": "strict" },
  "tools": ["fs.read"],
  "tags": ["nlp", "analysis"],
  "webhook_url": null,
  "author": "you@example.com",
  "changelog": "initial draft"
}
```

```json title="201 Response"
{ "agent_id": "research-analyst", "version": 1, "version_id": 12 }
```

`409 {"code":"already_exists",...}` si el id ya está en uso. Cada edición crea una nueva
versión; revierte con los endpoints de versión o de prompt-rollback.

### Leer / editar el prompt

```json title="GET /api/agents/{agent_id}/prompt → 200"
{ "path": "agents/research-analyst/system.md", "content": "You are a research analyst. ...", "size": 512, "mtime": "2026-08-02T10:00:00Z" }
```

```json title="PUT /api/agents/{agent_id}/prompt (request)"
{ "content": "You are a meticulous research analyst. ..." }
```

El `PUT` captura una nueva versión solo si el contenido cambió (deduplicación por hash de
contenido) y devuelve la misma forma que `GET`.

```json title="POST /api/agents/{agent_id}/prompt/rollback (request)"
{ "target_version": 2, "author": "you@example.com" }
```

---

## Motores (backends, perfiles, proveedores)

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/runner-backends` | Listar backends |
| `GET` `POST` | `/api/runner-profiles` | Listar / crear perfiles |
| `GET` `PATCH` `DELETE` | `/api/runner-profiles/{profile_id}` | Obtener / actualizar / eliminar |
| `GET` | `/api/runner-profiles/{profile_id}/stats` | Estadísticas de ejecución por perfil |
| `GET` | `/api/runner-providers` | Listar proveedores |
| `POST` | `/api/runner-providers/refresh` | Refrescar la caché de modelos |
| `GET` | `/api/runner-providers/{provider_id}/models` | Listar los modelos de un proveedor |

`/api/providers/**` es un alias de `/api/runner-profiles/**`.

### Crear un perfil de runner

`POST /api/runner-profiles`. Obligatorios: `name`, `backend`. `id` es opcional (se
genera uno si se omite). Los proveedores locales (Ollama) no necesitan `api_key_env`.

```json title="Request body: containerized Ollama"
{
  "id": "ollama",
  "name": "Ollama (container)",
  "backend": "token",
  "provider": "ollama",
  "model": "ollama:llama3",
  "base_url": "http://ollama:11434",
  "is_enabled": true
}
```

```json title="201 Response (full profile)"
{
  "id": "ollama",
  "name": "Ollama (container)",
  "description": null,
  "backend": "token",
  "provider": "ollama",
  "model": "ollama:llama3",
  "base_url": "http://ollama:11434",
  "api_key_env": null,
  "output_mode": "auto",
  "params": {},
  "headers": {},
  "extra_args": [],
  "is_enabled": true,
  "is_system_default": false,
  "created_at": "2026-08-02T09:00:00Z",
  "updated_at": "2026-08-02T09:00:00Z"
}
```

`PATCH /api/runner-profiles/{id}` acepta cualquier subconjunto de los campos mutables
(`name`, `model`, `base_url`, `api_key_env`, `is_enabled`, `is_system_default`,
...) y devuelve el perfil actualizado.

---

## Recursos

| Método | Ruta | Propósito |
|---|---|---|
| `GET` `POST` | `/api/repo-resources` | Listar / crear recursos |
| `POST` | `/api/repo-resources/{resource_id}/versions/upload` | Subir una versión (multipart) |
| `GET` | `/api/repo-resources/{resource_id}` · `/preview-modes` | Inspeccionar |
| `DELETE` | `/api/repo-resources/{resource_id}` | Eliminar |
| `GET` `PUT` | `/api/agents/{agent_id}/prompt-resources` | Listar / vincular recursos del prompt |
| `POST` | `/api/agents/{agent_id}/prompt-resources/preview` | Previsualizar el prompt compuesto |
| `GET` `PUT` | `/api/workspaces/{id}/resources` | Listar / vincular recursos del espacio de trabajo |

### Crear y subir un recurso

```json title="POST /api/repo-resources (request) → 201"
{ "slug": "research-guide", "type": "document", "display_name": "Research Guide", "tags": ["research"] }
```

Sube el contenido como una **nueva versión** con campos de formulario multipart (`file`,
`changelog`, `actor`):

```bash
curl -X POST http://localhost:8765/api/repo-resources/research-guide/versions/upload \
  -F 'file=@./guidelines.md' \
  -F 'changelog=initial' \
  -F 'actor=you@example.com'
```

### Vincular un recurso en el prompt

`PUT /api/agents/{agent_id}/prompt-resources` reemplaza las vinculaciones del prompt del
agente. Coloca el `marker` (p. ej. `{{GUIDELINES}}`) en el prompt del sistema y el
recurso se sustituye en tiempo de composición.

```json title="Request body"
{
  "bindings": [
    { "resource_id": "research-guide", "marker": "{{GUIDELINES}}", "slot": "system", "mode": "inline", "required": true }
  ],
  "reason": "inline the research guide",
  "actor": "you@example.com"
}
```

`mode` es `inline` o `reference`; `slot` es el slot del prompt (p. ej. `system`).

---

<a id="workspace-mcp"></a>

## Espacios de trabajo

| Método | Ruta | Propósito |
|---|---|---|
| `GET` `POST` | `/api/workspaces` | Listar / crear |
| `GET` `DELETE` | `/api/workspaces/by-name/{name}` | Obtener / eliminar |
| `GET` `PUT` | `/api/workspaces/by-name/{name}/permissions` | Permisos |
| `GET` | `/api/workspaces/by-name/{name}/mcp-tools` · `/skills[/{skill}]` | Herramientas MCP / skills |
| `POST` | `/api/workspaces/by-name/{name}/generate-configs` · `/generate-skills` | Regenerar |
| `GET` `PUT` | `/api/workspaces/by-name/{name}/file` | Leer / escribir un archivo |
| `GET` `PUT` | `/api/workspaces/{id}/resources` · `/subagents` · `/skill-bindings` | Vinculaciones |
| `POST` | `/api/workspaces/{id}/resources/dry-run` | Previsualizar una vinculación |
| `GET` `PUT` | `/api/workspaces/{id}/credentials` | Credenciales del espacio de trabajo |
| `GET` | `/api/workspaces/{id}/available_tools` | Herramientas disponibles |
| `GET` `PUT` `POST` | `/api/workspaces/{id}/env-doc[/preview]` | Documento de entorno |
| `GET` | `/api/workspaces/{id}/mcp[/servers]` · `/mcp/policy` | MCP del espacio de trabajo |
| `PUT` `DELETE` | `/api/workspaces/{id}/mcp/servers/{server_name}` | Añadir / eliminar servidor MCP |
| `PUT` | `/api/workspaces/{id}/mcp/policy` | Establecer la política de herramientas |
| `POST` | `/api/workspaces/{id}/mcp/refresh` | Reintrospectar |

### Crear un espacio de trabajo

```json title="POST /api/workspaces (request) → 201"
{ "name": "research", "description": "Persistent research workspace", "path": "/agentbox/workspaces/research" }
```

Omite `path` para un directorio gestionado. `409` si el nombre ya existe.

### Vincular un recurso en un espacio de trabajo

`PUT /api/workspaces/{id}/resources` materializa un recurso como un archivo en disco.

```json title="Request body"
{
  "bindings": [
    { "resource_id": "research-guide", "target_path": "docs/guidelines.md", "materialize_mode": "copy", "on_conflict": "overwrite" }
  ],
  "reason": "share the research guide",
  "actor": "you@example.com"
}
```

`materialize_mode`: `copy` · `symlink` · `mount`. `on_conflict`: `error` ·
`overwrite` · `skip`.

---

## Feedback y uso

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/activity/summary` · `/api/activity/runs` | Agregados de actividad |
| `GET` | `/api/usage` | Uso agregado de tokens / coste |

## Sistema

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/health` · `/api/health` | Liveness |
| `GET` `PATCH` | `/api/settings[/{section}]` · `/deployment` · `/env-secrets` | Ajustes |
| `GET` `PUT` `POST` `DELETE` | `/api/project/mcp-servers[/{name}][/introspect]` | Servidores MCP del proyecto |
| `GET` `POST` `PUT` `DELETE` | `/api/host-env/{capabilities,profiles}` | Herramientas / perfiles de host-env |
| `GET` `PUT` | `/api/agents/{agent_id}/host-env` | Concesiones de host-env del agente |
| `GET` | `/api/runs/{run_id}/host-env-calls` | Auditoría de llamadas a host-env |
| `GET` `POST` `DELETE` | `/api/credentials[/{credential_id}]` | Credenciales almacenadas |
| `GET` | `/api/mcp/servers[/{name}/tools]` · `/groups` | Inventario interno de MCP |

---

Ver también: **[CLI](reference-cli.md)** · **[MCP](reference-mcp.md)**.
