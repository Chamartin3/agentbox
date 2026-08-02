# Trabaja de forma interactiva

Todo lo anterior ejecutaba un agente en modo **headless**: una sola pasada, con
la salida a través de la API. Pero ese mismo entorno aislado y con recursos
acotados puede alojar una **sesión interactiva en vivo**. El operador conduce el
propio CLI del backend (Claude Code, OpenCode, ...) dentro del espacio de trabajo
del agente, con sus herramientas, skills y configuración de MCP ya en su sitio.

Este es el caso de uso prioritario para el trabajo iterativo: control total del
entorno, la sesión completa capturada y sin distracciones que el agente no
debería tener.

## Headless frente a interactivo

Los agentes declaran un `session_mode`:

| `session_mode` | Comportamiento |
|---|---|
| `headless` | Ejecución de una sola pasada; entrada y salida a través de la API |
| `persistent` | Sesión de larga duración conducida de forma interactiva por una terminal |

## Lanza una sesión personalizada de OpenCode

El objetivo de este recorrido: una TUI de OpenCode ejecutándose en un espacio de
trabajo específico, exponiendo únicamente unos pocos agentes elegidos como
subagentes. Nada más de la librería es visible dentro de la sesión.

**1. Crea (o reutiliza) un espacio de trabajo persistente** para que los
archivos, el historial y el estado se mantengan entre sesiones:

```bash
agentbox work ws new research --path /agentbox/workspaces/research
```

**2. Añade solo los agentes que esta sesión debe ver.** Un espacio de trabajo
expone un conjunto seleccionado de agentes al backend como subagentes. Vincula
solo los deseados, cada uno como un objeto con un `agent_id` y un `alias`:

```bash
curl -X PUT http://localhost:8765/api/workspaces/research/subagents \
  -H 'content-type: application/json' \
  -d '{
    "subagents": [
      { "agent_id": "web-writer", "alias": "web-writer", "display_order": 0 },
      { "agent_id": "authz-reader", "alias": "authz-reader", "display_order": 1 }
    ]
  }'
```

Solo estos dos aparecen dentro de la sesión; el resto de los agentes quedan fuera.

!!! note "Un subagente necesita un prompt para renderizarse"
    Un agente aparece únicamente si su versión activa tiene contenido de prompt.
    Los agentes con un prompt vacío se omiten silenciosamente cuando se compone
    la configuración del espacio de trabajo.

**3. Regenera la configuración del espacio de trabajo** para que las referencias
de subagentes aterricen donde OpenCode las descubre (`.opencode/`):

```bash
agentbox work file gen research
```

**4. Lanza OpenCode en el espacio de trabajo.** Esta es una sesión ad-hoc (sin
agente de nivel superior), anclada al backend `opencode` y al espacio de trabajo
`research`:

```bash
agentbox run --backend opencode --workspace research
```

La sesión se abre en la TUI de OpenCode, acotada a `research`, con `web-writer`
y `authz-reader` disponibles como subagentes y nada más.

!!! tip "¿Ejecutándolo en un contenedor?"
    OpenCode y el CLI viven dentro del contenedor, así que lanza la TUI allí:

    ```bash
    docker exec -it agentbox-sample \
      agentbox run --backend opencode --workspace research
    ```

    Los pasos 1-3 se ejecutan a través de la API contra el puerto del host al que
    hayas mapeado el servicio en tu `docker-compose`.

### Reanuda una sesión

```bash
agentbox run --backend opencode --workspace research --session-id sess-abc123
```

!!! tip "¿Vinculado a un único agente en su lugar?"
    Para abrir una sesión en el backend y el espacio de trabajo propios de un
    agente, ejecútalo sin un prompt: `agentbox run research-analyst`. La sesión
    se abre en el harness de ese agente (por ejemplo, la TUI de Claude Code), ya
    acotada a sus recursos, skills y herramientas.

La sesión se ejecuta en la propia **TUI** del harness en la terminal del operador
— esa parte no es el dashboard. Pero la sesión se captura igual que cualquier
ejecución, y el dashboard la muestra **en vivo**: el flujo de eventos avanza por
el WebSocket a medida que progresa el trabajo, y luego queda completamente
navegable después (transcripción, llamadas a herramientas, uso).

<figure markdown>
  ![Flujo de eventos de la sesión en vivo en el dashboard](img/interactive-session.png)
  <figcaption>El flujo de eventos en vivo del dashboard para una sesión — texto, llamadas a herramientas y uso transmitiéndose por el WebSocket, filtrable y navegable después de que termina.</figcaption>
</figure>

## Qué proporciona la sesión

- El **prompt compuesto** del agente, sus recursos y skills, ya colocados donde
  el backend los espera.
- Solo las **herramientas permitidas**. Concede o revoca sin salir:

    ```bash
    agentbox agent tool ls research-analyst
    agentbox agent tool grant research-analyst shell.exec
    ```

- Los servidores MCP configurados para el espacio de trabajo (herramientas
  internas del host más cualquier MCP externo conectado):

    ```bash
    agentbox work mcp show research
    agentbox work mcp tools research
    ```

- **Captura** completa de la sesión, igual que una ejecución headless:
  transcripción, uso y tiempos, navegables después en el dashboard y mediante
  `agentbox history`.

## Qué backends lo soportan

| Backend | Interactivo |
|---|---|
| `claude_code` | Sí, TUI completa |
| `opencode` | Sí, TUI completa |
| `codex` | Limitado |
| `pi` | Limitado, sin terminal completa |
| `token` | No, en proceso, sin CLI |

!!! warning "Aún no es un sandbox a nivel de sistema operativo"
    Una sesión interactiva con `shell.exec` concedido puede alcanzar el sistema
    de archivos y la red del host. Acota las herramientas deliberadamente y
    ejecuta de forma interactiva únicamente agentes de confianza. Consulta la
    [nota sobre aislamiento](01-setup-system.md#isolation).

## Entra en un shell simple del espacio de trabajo

Para explorar el entorno sin lanzar un agente:

```bash
agentbox work ws shell research     # shell in the workspace
agentbox work ws explore research   # browse its files
```

---

Con esto se completa el recorrido: AgentBox está configurado, un proveedor está
listo, se crea y ejecuta un primer agente, se impone la salida estructurada, el
trabajo ocurre en espacios de trabajo aislados, las ejecuciones se automatizan
con webhooks, los harnesses se evalúan y comparan, y se conduce una sesión
interactiva en vivo, todo desde un único backend capturado y controlable.

Vuelve a la **[Introducción](index.md)**.
