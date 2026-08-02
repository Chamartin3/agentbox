# Salida estructurada y validada

Un resumen legible por humanos está bien; un resumen que el código pueda consumir
es mejor. Cuando se adjunta un **esquema de salida**, AgentBox valida la salida del
agente contra él y, ante un fallo en modo `strict`, vuelve a ejecutar con el error
de validación añadido al prompt, hasta un límite configurado.

## Definir el esquema

```json title="output_schema.json"
{
  "type": "object",
  "required": ["title", "summary", "key_findings"],
  "properties": {
    "title": { "type": "string" },
    "summary": { "type": "string" },
    "key_findings": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

## Adjuntarlo y habilitar la validación

Adjunta el esquema al agente y activa la validación estricta con reintentos.

=== "Dashboard"

    Abre la pestaña **Composition** del agente. En **Schema slots**, usa **+ set /
    upload** en la fila **Output schema** para adjuntar `output_schema.json`, y
    elige el modo ante discrepancia (`strict` / `warn` / `off`) desde el desplegable
    que está allí mismo. El límite de reintentos vive en el paso **Runner**: define
    **max validation retries** al crear el agente, o en la pestaña Configuration
    después.

    <figure markdown>
      ![Configuración del Runner: esquema de salida y reintentos de validación](img/agent-runner.png)
      <figcaption>El paso Runner lleva el esquema y la configuración de reintentos: <code>output_schema_path</code> y <code>max validation retries</code>.</figcaption>
    </figure>

=== "API / CLI"

    La configuración del agente lleva dos ajustes relacionados:

    ```json title="agent config (composition + runner)"
    {
      "composition": { "output_schema": "output_schema.json", "output_validation": "strict" },
      "runner": { "output_schema_path": "output_schema.json", "max_validation_retries": 2 }
    }
    ```

    ```bash
    # Adjunta el archivo de esquema al agente
    agentbox agent files add research-analyst --kind output_schema ./output_schema.json
    ```

| Ajuste | Significado |
|---|---|
| `composition.output_validation` | `strict`, `warn` u `off` |
| `runner.output_schema_path` | El esquema contra el que validar la salida |
| `runner.max_validation_retries` | Reejecuciones permitidas ante una salida inválida |

## Qué ocurre durante una ejecución

El stream muestra un evento `validation` y, si falla, un evento `retry`
antes del siguiente intento:

```json
{"type": "validation", "ok": false, "attempt": 1, "mode": "strict", "engine": "jsonschema", "error": "key_findings: required"}
{"type": "retry", "attempt": 2, "reason": "validation_failed"}
{"type": "validation", "ok": true, "attempt": 2, "mode": "strict"}
```

La ejecución finalizada registra el resultado para que se pueda filtrar por él:

```bash
curl -s http://localhost:8765/api/runs/run-abc123 \
  | jq '{status: .run.status, validation: .run.validation_status, errors: .run.validation_errors}'
```

| Campo | Significado |
|---|---|
| `validation_status` | `ok` o `failed` tras el intento final |
| `validation_errors` | Los errores del esquema, si los hay |

!!! tip "Avisar en lugar de fallar"
    Define `output_validation = "warn"` para registrar problemas de validación sin
    reejecutar ni hacer fallar la ejecución. Usa `strict` cuando un sistema aguas
    abajo dependa de la forma; usa `warn` mientras aún estás dando forma al prompt.

!!! note "Esquemas de entrada también"
    El mismo mecanismo valida la **entrada**. Añade un `input_schema` a la
    composición para rechazar solicitudes malformadas antes de que el agente se ejecute.

---

Siguiente: **[5. Espacios de trabajo →](05-workspaces.md)**
