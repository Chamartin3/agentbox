# Automatiza con webhooks

Para un worker de un solo uso, hacer polling rara vez es deseable. Dada una
`webhook_url`, en cuanto la ejecución termina AgentBox devuelve la llamada con la
ejecución completada: estado, salida y uso. Esto es lo que convierte a AgentBox en una
API agéntica multiuso: envías el trabajo y el resultado se te devuelve.

## Configura el webhook por ejecución

```bash
curl -X POST http://localhost:8765/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "agent": "research-analyst",
    "input": "Summarize this paper ...",
    "webhook_url": "https://your-service.example.com/hooks/agentbox"
  }'
```

## O conviértelo en el valor por defecto del agente

Configura una `webhook_url` en el propio agente y cada ejecución dispara el webhook al
completarse, a menos que una petición lo sobrescriba.

=== "Dashboard"

    Abre el agente, ve a la pestaña **Configuration** y rellena el
    campo **webhook URL** dentro de los ajustes de ejecución (el mismo panel que se muestra en
    [3. Gestionar agentes](03-first-agent.md#composition)). Cada ejecución del agente
    devolverá entonces la llamada al completarse.

=== "API"

    ```json title="agent config"
    { "webhook_url": "https://your-service.example.com/hooks/agentbox" }
    ```

## Entrega y verificación

AgentBox hace un POST del payload de la ejecución completada a la URL de destino, con reintentos, y registra
cada entrega (estado, respuesta, latencia, error) para que las llamadas fallidas queden
visibles en lugar de perderse silenciosamente.

Para verificar que el payload realmente provino de AgentBox, configura un secreto de firma:

```bash title=".env"
AGENTBOX_WEBHOOK_SECRET=some-long-random-string
```

Las entregas se firman entonces con un HMAC que el receptor puede comprobar antes de
confiar en el cuerpo.

!!! tip "Pruebas locales"
    Apunta la `webhook_url` a un endpoint de inspección de peticiones (por ejemplo, un
    `nc -l 9000` local o un túnel a un servidor de desarrollo) para ver la forma exacta del payload
    antes de conectarlo a producción.

---

Siguiente: **[Evaluar y mejorar →](07-evaluate.md)**
