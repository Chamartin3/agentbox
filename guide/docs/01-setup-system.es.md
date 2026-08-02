# Instalación

Compila e inicia AgentBox. El servicio se ejecuta **sin credenciales**: un
proveedor de modelos se configura en el [siguiente paso](02-setup-providers.md), y
solo para el proveedor que realmente estés usando. Una vez que el sistema esté en
marcha y haya un proveedor configurado, puedes [crear y ejecutar](03-first-agent.md) un agente.

---

## Compilar la imagen

AgentBox se distribuye como una imagen de Docker que contiene el servicio FastAPI, la CLI y
el panel de control precompilado.

```bash
git clone https://github.com/Chamartin3/agentbox.git
cd agentbox
docker compose build agentbox
```

## Iniciar el servicio

```bash
docker compose up -d agentbox
```

El servicio **inicializa su base de datos automáticamente en el primer arranque** (las
migraciones de Alembic se ejecutan al arrancar; no hay un comando de migración aparte) y
**genera perfiles de runner predeterminados**, uno por proveedor, listos para habilitar en el
siguiente paso. El contenedor gestiona dos volúmenes con nombre de forma predeterminada:

| Volumen | Punto de montaje | Contenido |
|---|---|---|
| `agentbox-data` | `/data` | Base de datos SQLite + transcripciones de ejecuciones |
| `agentbox-creds` | `/agentbox/creds` | Todas las credenciales de backend; cada backend en su propio subdirectorio |

Ambos son reubicables: define `AGENTBOX_DATA_VOLUME` o `AGENTBOX_CREDS_VOLUME` a una
ruta del host (p. ej. `./data`) para hacer un bind-mount en lugar de usar el volumen con
nombre. Déjalos sin definir para mantener los volúmenes con nombre gestionados por el
contenedor anteriores.

### Personalizar los endpoints

La imagen sirve dos cosas: la **API** (más el panel de control) y un servidor **MCP**
independiente. Ambos escuchan en puertos fijos dentro del contenedor (`8765` y `8766`); lo
que personalizas es el puerto del host en el que se publica cada uno, definido en tu `.env` o
en el entorno de compose.

| Variable | Predeterminado | Qué controla |
|---|---|---|
| `AGENTBOX_PORT` | `8765` | Puerto del host en el que se publican la API y el panel de control |
| `AGENTBOX_CONTAINER_NAME` | `agentbox` | Nombre del contenedor de la API |
| `AGENTBOX_MCP_PORT` | `8766` | Puerto del host en el que se publica el servidor MCP |
| `AGENTBOX_MCP_HOST` | `0.0.0.0` | Interfaz a la que se enlaza el servidor MCP dentro del contenedor |
| `AGENTBOX_MCP_TRANSPORT` | `http` (en compose) | Transporte MCP: `http` expone HTTP en streaming en `/mcp`; `stdio` para una tubería local |
| `AGENTBOX_MCP_CONTAINER_NAME` | `agentbox-mcp` | Nombre del contenedor MCP |

Por ejemplo, para mover ambos fuera de los valores predeterminados:

```bash
# .env
AGENTBOX_PORT=9000
AGENTBOX_MCP_PORT=9001
```

La API estará entonces en `http://localhost:9000` y MCP en `http://localhost:9001/mcp`.
En la red compartida de docker, otros servicios siguen alcanzándolos por el nombre del
contenedor y el puerto interno (`http://agentbox:8765`, `http://agentbox-mcp:8766/mcp`).

Verifica que esté saludable:

```bash
curl -s http://localhost:8765/api/runs | head
# -> {"items": [], "total": 0, ...}  (empty run list)
```

## Abrir el panel de control

Abre el panel de control de AgentBox en un navegador. La página de inicio de **Activity** es
el punto de partida: volumen de ejecuciones a lo largo del tiempo, tasa de fallos, totales de
tokens y coste, y un feed en vivo de las ejecuciones recientes. En una instancia nueva
empieza vacía y se va rellenando a medida que se ejecutan los agentes; la captura de abajo es
una instancia con historial.

<figure markdown>
  ![Panel de control de AgentBox](img/dashboard-home.png)
  <figcaption>El panel de control de Activity: ejecuciones a lo largo del tiempo, tasa de fallos, totales de tokens/coste, desgloses por acción y por modelo, y un feed en vivo de ejecuciones recientes.</figcaption>
</figure>

---

<a id="isolation"></a>

!!! warning "Límite de aislamiento: léelo antes de conceder acceso al shell"
    Una ejecución está aislada a su directorio de espacio de trabajo y a las herramientas que
    tiene permitidas. Esto es un ámbito a nivel de sistema de archivos, **no** un sandbox a
    nivel de sistema operativo. Un backend con acceso al shell puede alcanzar el host. Concede
    acceso al shell o a herramientas solo a agentes de confianza, y ejecuta AgentBox en una
    infraestructura controlada.

Siguiente: **[Configurar un proveedor →](02-setup-providers.md)**
