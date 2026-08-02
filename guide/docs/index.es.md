<p align="center" markdown>
  ![AgentBox](img/logo.svg){ width="320" }
</p>

<p align="center" markdown>
**Ejecuta agentes reutilizables dentro de entornos aislados y completamente
capturados, con control granular sobre las herramientas y los recursos que puede usar cada agente.**
</p>

AgentBox es un backend de orquestación de agentes. Un agente y los
recursos que necesita se definen una sola vez, se ejecutan en un entorno controlado limitado exactamente
a las herramientas permitidas, y se devuelven como una captura completa de la ejecución (transcripción,
tokens, coste, tiempos y llamadas a herramientas) para inspeccionar, puntuar y mejorar. El mismo
agente se ejecuta en cualquier harness compatible (Claude Code, OpenCode, Codex, Pi,
pydantic-ai) a través de una única API.

Está pensado para ingenieros de plataforma y de IA que integran agentes en sus propios
productos, y para quienes necesitan que las ejecuciones de agentes sean aisladas, reproducibles y
medibles en lugar de improvisadas.

La guía tiene dos partes. **Instalación y configuración** pone AgentBox en marcha y
lo apunta a un proveedor. **Uso** construye, ejecuta y mejora agentes.

## Instalación y configuración

| Paso | Qué ocurre |
|---|---|
| **[1. Instalación](01-setup-system.md)** | Construye la imagen, inicia el servicio, abre el panel |
| **[2. Configurar un proveedor](02-setup-providers.md)** | Apunta AgentBox a Ollama, una clave de API o un backend de CLI; un perfil de runner |

## Uso

| Paso | Qué ocurre |
|---|---|
| **[3. Gestionar agentes](03-first-agent.md)** | Compón un agente a partir de un prompt, recursos y esquemas; versionado e historial de ejecuciones |
| **[4. Salida estructurada](04-structured-output.md)** | Impón un esquema JSON y reintenta ante salidas no válidas |
| **[5. Espacios de trabajo](05-workspaces.md)** | Entornos aislados efímeros y persistentes |
| **[6. Trabajar de forma interactiva](09-interactive.md)** | Dirige una sesión en vivo y aislada limitada a unos pocos agentes elegidos |
| **[7. Automatizar con webhooks](06-webhooks.md)** | Envía los resultados completados a un servicio externo |
| **[8. Evaluar y mejorar](07-evaluate.md)** | Puntúa ejecuciones, haz seguimiento de la calidad, añade y reutiliza recursos |
| **[9. Cambiar de harness y comparar](08-compare.md)** | Ejecuta un agente en muchos backends; compara tokens, tiempo y calidad |

## Referencia

| Página | Qué |
|---|---|
| **[API REST y WebSocket](reference-api.md)** | Todos los endpoints, agrupados; además de los `/docs` y `/openapi.json` en vivo |
| **[CLI](reference-cli.md)** | El mapa del comando `agentbox` |
| **[MCP](reference-mcp.md)** | El propio servidor MCP de AgentBox y su catálogo de herramientas |

## Conceptos fundamentales

| Concepto | Qué es |
|---|---|
| **[Agente](03-first-agent.md#create-the-agent)** | Una definición con nombre: un prompt compuesto, un esquema de salida opcional y un perfil de runner. |
| **[Runner / backend](02-setup-providers.md#what-a-runner-profile-is)** | El harness que ejecuta el agente: `claude_code`, `opencode`, `codex`, `pi` o `token` (pydantic-ai, en proceso). |
| **[Espacio de trabajo](05-workspaces.md)** | El entorno aislado en el que se ejecuta una ejecución. Efímero (nuevo en cada ejecución) o persistente (reutilizado). |
| **[Recurso](03-first-agent.md#attach-resources)** | Una entrada tipada colocada en un espacio de trabajo o prompt: documento de texto, esquema JSON, script o skill. |
| **[Ejecución](03-first-agent.md#run-history)** | Una ejecución de un agente, capturada por completo: transcripción, uso, tiempos y llamadas a herramientas. |

---

Empieza con **[1. Instalación →](01-setup-system.md)**
