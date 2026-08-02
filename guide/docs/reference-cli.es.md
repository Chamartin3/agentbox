# CLI

La CLI `agentbox` viene incluida en la imagen. Ejecútala contra el servicio en ejecución:

```bash
docker compose exec agentbox agentbox --help
docker compose exec agentbox agentbox <group> --help
```

Todos los comandos admiten `--help`; esa salida es la referencia autoritativa para las banderas. Esta
página es el mapa de comandos.

## Nivel superior

| Comando | Propósito |
|---|---|
| `agentbox run` | Ejecuta un agente, en modo headless (`-p/--prompt`) o interactivo (sin prompt) |
| `agentbox agent` | Definiciones de agentes, prompts, versiones, herramientas, archivos |
| `agentbox work` | Espacios de trabajo, archivos, MCP, permisos, recursos, skills |
| `agentbox engine` | Perfiles de runner, proveedores, backends, credenciales |
| `agentbox system` | Entorno, salud, host-env, MCP, proyecto, ajustes |
| `agentbox ops` | Operaciones de configuración, recursos y work-env |
| `agentbox history` | Historial de ejecuciones, logs y estadísticas |
| `agentbox mat` | Exporta / importa agentes entre instancias |

## `run`

```bash
agentbox run <agent> -p "prompt"              # headless
agentbox run <agent> --runner-profile ollama  # pick a profile (headless)
agentbox run <agent>                          # interactive TTY session
agentbox run --backend opencode -w research   # ad-hoc interactive, no agent
```

| Bandera | Significado |
|---|---|
| `-p, --prompt` | Prompt para una ejecución headless (POST + stream) |
| `--headless` | Fuerza el modo headless |
| `-b, --backend` | Backend para una sesión interactiva ad-hoc |
| `-w, --workspace` | Anulación de espacio de trabajo con nombre |
| `--model` | Anulación de modelo |
| `-e, --ephemeral` | Fuerza un espacio de trabajo efímero nuevo |
| `--session-id` | Reanuda una sesión |

## `agent`

| Subgrupo | Comandos comunes |
|---|---|
| `agent def` | `new --name <id>` · `ls` · `show <id>` · `edit <id> --runner <profile>` |
| `agent prompt` | `edit <id>` · `log <id>` · `rollback <id> --to <n>` |
| `agent version` | `ls <id>` |
| `agent tool` | `ls <id>` · `grant <id> <tool>` |
| `agent files` | `add <id> --kind output_schema <path>` |
| `agent check` | Valida una definición de agente |

## `work`

| Subgrupo | Comandos comunes |
|---|---|
| `work ws` | `new <name> --path <dir>` · `show` · `explore` · `shell` |
| `work file` | `gen <ws>` (regenera la configuración del backend) |
| `work mcp` | `show <ws>` · `tools <ws>` |
| `work perm` | Permisos del espacio de trabajo |
| `work res` | Vinculaciones de recursos del espacio de trabajo |
| `work skill` | Skills del espacio de trabajo |

## `engine`

| Subgrupo | Comandos comunes |
|---|---|
| `engine profile` | `ls` · `show <id>` · `new --id <id> --backend token --provider <p> --model <m> [--base-url <url>] [--api-key-env <VAR>]` · `delete <id>` |
| `engine provider` | `ls` · `models <provider> [--profile <id>]` · `refresh` |
| `engine backend` | `list` |
| `engine cred` | Gestiona las credenciales almacenadas |

## `system`

| Subgrupo | Propósito |
|---|---|
| `system health` | Comprobación de salud del servicio |
| `system settings` | Lee / actualiza secciones de ajustes |
| `system env` | Inspección del entorno |
| `system host` | Perfiles y concesiones de host-env |
| `system mcp` | Inventario interno de MCP |
| `system project` | Servidores MCP a nivel de proyecto |

## `history`

| Subgrupo | Comandos comunes |
|---|---|
| `history show <run-id>` | Detalle de la ejecución |
| `history log` | `comments <run-id>` |
| `history stat` | `usage --agent <id>` · `runs --range 30d --agent <id>` · `activity --range 30d` |

## `ops` · `mat`

| Comando | Propósito |
|---|---|
| `ops resource repo` | `upload <slug> <path> --changelog <msg>` · `ls` · `show <slug>` · `rollback <slug> --version <n>` |
| `ops cfg` · `ops workenv` | Operaciones de configuración y work-env |
| `mat export <agent> --to <dir>` | Exporta un agente (prompt, configuración, archivos) |
| `mat import <agent> --from <dir>` | Importa un agente a esta instancia |

---

Consulta también: **[REST & WebSocket API](reference-api.md)** · **[MCP](reference-mcp.md)**.
