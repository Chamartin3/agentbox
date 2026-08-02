# Gestión de agentes

Un **agente** es una definición con nombre ensamblada a partir de piezas. En su
núcleo se encuentra un prompt de sistema, pero el prompt rara vez es la historia
completa.

Un agente asocia esquemas de validación que restringen lo que entra y lo que
vuelve, y recursos (documentos, scripts, skills) de los que se nutre el prompt.

Esos esquemas y recursos son objetos reutilizables por derecho propio, así que
varios agentes pueden compartir un mismo esquema de salida o un mismo documento
de referencia.

AgentBox lo mantiene todo en una **base de datos**. No hay archivos de agente que
gestionar: el agente se compone y se ejecuta directamente en el **dashboard**.

!!! info "Requisito previo"
    Se ha configurado al menos un proveedor en
    [2. Configurar un proveedor](02-setup-providers.md). Esta página ejecuta el
    agente sobre el perfil configurado ahí (`MyRunnerProfile`).

## Crear el agente { #create-the-agent }

=== "Dashboard"

    Abre **Agents → New agent**. Un breve asistente cubre todo lo que un
    agente necesita, un paso a la vez:

    1. **Identity** — id, descripción y etiquetas opcionales.
    2. **Runner** — qué backend lo ejecuta, el modelo, el timeout, los límites de
       reintentos y un esquema de salida opcional.
    3. **Prompt** — el prompt de sistema en línea (versionado a partir de aquí).
    4. **Tools** — qué herramientas puede usar este agente.
    5. **Review** — confirmar y crear.

    <figure markdown>
      ![Creación de un agente en el dashboard](img/agent-new.png)
      <figcaption>El asistente New Agent — Identity → Runner → Prompt → Tools → Review. El agente se escribe en la base de datos y aparece de inmediato en la lista de agentes.</figcaption>
    </figure>

    Usa estos valores:

    - **id:** `research-analyst`
    - **prompt:** *You are a research analyst. Given a paper or article, produce
      a concise, structured summary. Be specific and avoid filler.*

    Todo lo definido aquí es editable más adelante desde la página de detalle del
    agente (pestañas Configuration / Composition / Tools).

=== "API"

    ```bash
    curl -X POST http://localhost:8765/api/agents \
      -H 'content-type: application/json' \
      -d '{
        "id": "research-analyst",
        "description": "Summarizes research papers into structured output",
        "prompt": "You are a research analyst. Given a paper or article, produce a concise, structured summary. Be specific and avoid filler.",
        "runner": { "timeout_seconds": 1200 },
        "author": "you@example.com",
        "changelog": "initial draft"
      }'
    ```

Todo agente vive en la lista **Agents**, donde cualquiera puede buscarse,
filtrarse por runner y abrirse para editar:

<figure markdown>
  ![La lista de agentes](img/agents-list.png)
  <figcaption>La lista de agentes: cada agente con su perfil de runner, espacio de trabajo, versión activa y número de ejecuciones.</figcaption>
</figure>

## Composición { #composition }

AgentBox no trata el prompt como una única cadena opaca. **Compone** el prompt de
sistema a partir de fragmentos en un orden fijo (prompt base, esquema de entrada,
referencias, esquema de salida) y captura cada fragmento con su origen, de modo
que la entrada exacta al modelo queda visible.

La pestaña **Composition** del agente es donde esto se muestra en vivo. A medida
que se enlazan recursos, el panel **Live composed prompt** muestra el texto
completamente ensamblado y un desglose de cómo se generó: el recuento de bytes de
cada fragmento y su proporción del prompt final, de modo que nada sobre lo que ve
el modelo queda oculto.

<figure markdown>
  ![Composición de un agente con varios recursos enlazados](img/agent-composition.png)
  <figcaption>Un agente con varios recursos enlazados: el prompt, los enlaces de recursos y el gráfico Live composed prompt que muestra la contribución de cada fragmento al texto generado.</figcaption>
</figure>

Todo lo relativo a un agente —su runner, límites de ejecución, prompt, recursos y
herramientas— es editable desde su página de detalle en el dashboard:

<figure markdown>
  ![Configuración de un agente en el dashboard](img/agent-config.png)
  <figcaption>La pestaña Configuration del agente: perfil de runner, espacio de trabajo, límites de ejecución y la concesión exacta de herramientas (Enabled vs Available), cada una con una descripción.</figcaption>
</figure>

### Asociar recursos { #attach-resources }

Un **recurso** es una entrada tipada (documento, esquema, script o skill)
asociada una vez y reutilizada.

Enlazar un recurso en lugar de pegar texto en el prompt significa que muchos
agentes comparten una única fuente de verdad: actualiza el recurso y todos los
agentes enlazados a él adoptan la nueva versión.

!!! tip "En el dashboard"
    Gestiona los recursos reutilizables en **Resources** en la navegación
    superior, y luego enlaza uno a un agente desde su pestaña **Composition**
    (dentro del prompt) o a un espacio de trabajo desde la página del espacio de
    trabajo (como un archivo en disco). La API/CLI de abajo hace lo mismo para
    scripts y automatización.

<figure markdown>
  ![La biblioteca de recursos compartidos](img/resources-list.png)
  <figcaption>Recursos compartidos: cada documento, esquema, script y skill en una sola biblioteca, reutilizable entre agentes y espacios de trabajo. + new resource añade uno.</figcaption>
</figure>

**1. Crear y subir un recurso:**

```bash
curl -X POST http://localhost:8765/api/repo-resources \
  -H 'content-type: application/json' \
  -d '{ "slug": "research-guide", "type": "document", "display_name": "Research Guide" }'

agentbox ops resource repo upload research-guide ./guidelines.md --changelog "initial"
```

**2. Enlázalo dentro del prompt** con un marcador. Coloca `{{GUIDELINES}}` en
cualquier parte del prompt de sistema y el contenido del recurso se sustituye en
el momento de la composición:

```bash
curl -X PUT http://localhost:8765/api/agents/research-analyst/prompt-resources \
  -H 'content-type: application/json' \
  -d '{
    "bindings": [
      { "resource_id": "research-guide", "marker": "{{GUIDELINES}}", "slot": "system", "mode": "inline", "required": true }
    ],
    "reason": "inline the research guide",
    "actor": "you@example.com"
  }'
```

Las subidas están versionadas (`agentbox ops resource repo show research-guide`,
`... rollback --version 1`). Un recurso también puede colocarse como un **archivo
en disco** en el espacio de trabajo en lugar de insertarlo en línea, consulta
[5. Espacios de trabajo](05-workspaces.md#bind-a-resource-into-a-workspace).

Cada recurso es un objeto versionado por derecho propio: abre uno para ver su
contenido activo, subir una nueva versión o revertir:

<figure markdown>
  ![Detalle de un recurso con su historial de versiones](img/resource-detail.png)
  <figcaption>La página de detalle de un recurso: tipo, contenido activo, checksum y el historial completo de versiones — una única fuente de verdad que comparten todos los agentes enlazados a él.</figcaption>
</figure>

### Esquemas de validación

Los esquemas también son recursos. Asocia un esquema de entrada para restringir
lo que acepta una ejecución, y un esquema de salida para forzar al modelo a una
forma validada.

Como un esquema es un recurso, un mismo esquema puede respaldar muchos agentes. El
esquema de salida es lo que convierte texto libre en resultados estructurados y
verificables, el tema de la página siguiente:
[4. Salida estructurada y validada](04-structured-output.md).

## Versionado

Cada creación genera la **versión 1**. Cada edición posterior del prompt o la
configuración crea una nueva versión inmutable.

Por tanto, un agente acumula una línea de versiones que pueden revisarse y
revertirse:

```bash
agentbox agent version ls research-analyst
agentbox agent prompt log research-analyst
agentbox agent prompt rollback research-analyst --to 1
```

Las valoraciones y el uso se agregan por versión, de modo que queda claro si un
cambio ayudó, consulta
[7. Evaluar y mejorar](07-evaluate.md#track-quality-across-versions).

### Historial de ejecuciones { #run-history }

Aparte de la línea de versiones está el **historial de ejecuciones**: cada
invocación del agente, conservada con su transcripción, tokens, coste y
resultado.

Este es el registro que hay que leer para ver cómo se comporta el agente en la
práctica.

```bash
agentbox history stat runs --range 30d --agent research-analyst
agentbox history stat usage --agent research-analyst
agentbox history show <run-id>
```

## Invocar un agente

Un agente siempre lleva un perfil de runner, así que ejecutarlo es solo cuestión
de cómo se le llama. Hay tres vías de entrada:

- **API** (la vía principal): `POST /api/runs`, pensada para programas y otros
  servicios.
- **CLI**: `agentbox run research-analyst -p "..."` para una ejecución headless
  puntual, o `agentbox run research-analyst` para una sesión interactiva en TTY.
- **Dashboard**: el dashboard es donde las ejecuciones se **observan e
  inspeccionan** en vivo y donde una ya existente se **vuelve a ejecutar** con el
  botón **↻ Rerun**. Las nuevas ejecuciones se lanzan desde la API o la CLI de
  arriba; luego cada una aparece en el dashboard para explorarla.

A través de la API, solo `agent` es obligatorio; pasa un `runner_profile` para
anular el que está enlazado al agente:

```bash
curl -X POST http://localhost:8765/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "agent": "research-analyst",
    "input": "Summarize this abstract on retrieval-augmented generation: ...",
    "runner_profile": "MyRunnerProfile"
  }'
```

`POST /api/runs` devuelve de inmediato con un `run_id`; la ejecución se realiza de
forma asíncrona.

El backend se resuelve en este orden: un **perfil de runner** pasado en la
ejecución (`runner_profile`), luego el perfil enlazado al agente, y luego el
perfil por defecto del sistema de la instancia.

### Ver la salida

El dashboard transmite la ejecución a medida que ocurre. A través de la API, los
mismos eventos llegan por un WebSocket:

```bash
websocat ws://localhost:8765/api/runs/run-abc123/stream
```

```json
{"type": "thinking", "run_id": "run-abc123", "text": "Reading the abstract..."}
{"type": "text", "role": "assistant", "text": "Summary: ...", "delta": true}
{"type": "usage", "input_tokens": 4200, "output_tokens": 640, "cost_usd": 0.0}
{"type": "done", "ok": true, "status": "ok"}
```

Tipos de evento: `text`, `thinking`, `tool_call`, `tool_result`, `usage`,
`validation`, `retry`, `timeout`, `log`, `done`. (Las ejecuciones locales de
Ollama reportan `cost_usd` como `0.0`.)

<figure markdown>
  ![Detalle de una ejecución con transcripción](img/run-detail-transcript.png)
  <figcaption>La vista de detalle de la ejecución: transcripción, razonamiento y llamadas a herramientas capturados por completo.</figcaption>
</figure>

La composición mostrada en el agente también se captura **por ejecución**: cada
ejecución registra los fragmentos exactos que entraron en su prompt y de dónde
provino cada uno.

<figure markdown>
  ![Fragmentos del prompt ensamblado](img/run-prompt-fragments.png)
  <figcaption>El prompt ensamblado de la ejecución, fragmento a fragmento con su origen — de modo que queda visible exactamente lo que recibió el modelo en esta ejecución.</figcaption>
</figure>

Ese `text` transmitido es de forma libre. Para obtener un resultado **validado y
estructurado** fiable en código, asocia un esquema de salida, que es el tema de la
página siguiente.

---

Siguiente: **[4. Salida estructurada y validada →](04-structured-output.md)**
