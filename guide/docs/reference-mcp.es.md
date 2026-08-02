# MCP

AgentBox incluye un **servidor MCP interno** que expone sus propias operaciones
(agentes, prompts, ejecuciones, feedback y recursos) como herramientas MCP. Cualquier
cliente MCP (Claude Code, un agente, un harness personalizado) puede apuntar a él para controlar AgentBox
de forma programática mediante el Model Context Protocol.

Esto es distinto de los servidores MCP **externos** conectados *a* un
espacio de trabajo (consulta [Espacios de trabajo](05-workspaces.md) y la
[API](reference-api.md#workspace-mcp)); esta página documenta el propio servidor
de AgentBox.

## Ejecutar el servidor

El punto de entrada `agentbox-mcp` viene incluido en la imagen:

```bash
docker compose exec agentbox agentbox-mcp
```

El transporte y el enlace se controlan mediante variables de entorno:

| Variable de entorno | Valor por defecto | Propósito |
|---|---|---|
| `AGENTBOX_MCP_TRANSPORT` | `stdio` | `stdio` o `http` |
| `AGENTBOX_MCP_HOST` | `0.0.0.0` | Host de enlace (transporte http) |
| `AGENTBOX_MCP_PORT` | `8766` | Puerto de enlace (transporte http) |

El servidor está construido con FastMCP bajo el nombre `agentbox`. Los plugins pueden registrar
herramientas adicionales a través del grupo de entry-points `agentbox.agent_tools`.

## Catálogo de herramientas

### Ejecuciones

| Herramienta | Propósito |
|---|---|
| `list_runs` | Lista las ejecuciones con filtros |
| `get_run` | Obtiene una ejecución |
| `get_run_output` | Salida final |
| `get_run_transcript` | Transcripción completa |
| `get_run_conversation` | Vista con formato de conversación |
| `get_run_logs` | Eventos de log |
| `get_run_errors` | Errores de una ejecución |
| `get_run_usage` | Tokens / coste |
| `get_run_prompt_fragments` | Prompt ensamblado, por fragmento |
| `get_run_time_remaining` | Tiempo restante de una ejecución en curso |
| `get_run_webhook_deliveries` | Registro de entregas de webhooks |
| `list_run_comments` · `add_run_comment` | Leer / añadir comentarios |

### Agentes

| Herramienta | Propósito |
|---|---|
| `list_agents` · `search_agents` | Explorar agentes |
| `get_agent` | Obtiene un agente |
| `list_agent_tags` | Etiquetas conocidas |
| `get_agent_prompt_fragments` | Los fragmentos de prompt compuestos del agente |
| `list_executors` | Backends disponibles |

### Prompts

| Herramienta | Propósito |
|---|---|
| `get_prompt` · `edit_prompt` | Leer / editar el prompt del sistema |
| `preview_prompt` | Previsualizar un prompt compuesto |
| `list_prompt_versions` | Historial de versiones |
| `get_prompt_diff` | Comparar dos versiones |
| `rollback_prompt` · `promote_version` | Revertir / promover una versión |

### Recursos y enlaces

| Herramienta | Propósito |
|---|---|
| `create_repo_resource` · `create_repo_resource_from_files` | Crear recursos |
| `get_prompt_resources` · `set_prompt_resources` | Listar / definir enlaces de prompt |
| `bind_prompt_resource` · `unbind_prompt_resource` | Enlazar / desenlazar un recurso |
| `set_workspace_resources` | Enlazar recursos a un espacio de trabajo |
| `build_workspace` · `dry_run_workspace_resources` | Construir / previsualizar un espacio de trabajo |
| `set_mcp_policy` · `toggle_mcp_server` · `toggle_mcp_tool` | Gestionar el MCP del espacio de trabajo |
| `render_env_doc` · `set_env_doc` | Documento de entorno del espacio de trabajo |
| `set_host_env_grants` · `list_host_env_calls` | Concesiones / auditoría del entorno del host |

### Feedback y estadísticas

| Herramienta | Propósito |
|---|---|
| `add_agent_version_rating` · `list_agent_version_ratings` | Valorar / listar valoraciones de versiones |
| `add_agent_version_comment` | Comentar sobre una versión |
| `list_agent_versions` | Lista de versiones |
| `agent_stats` · `activity_summary` · `aggregate_usage` | Resúmenes agregados |

### Utilidad

| Herramienta | Propósito |
|---|---|
| `get_run_time_remaining` | (ejecuciones, arriba) |
| hora actual | Herramienta `time` para agentes con noción del reloj |

---

Consulta también: **[API REST y WebSocket](reference-api.md)** · **[CLI](reference-cli.md)**.
