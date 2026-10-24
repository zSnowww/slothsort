# SlothSort for Telegram 🦥

[![Pruebas](https://github.com/zSnowww/slothsort/actions/workflows/ci.yml/badge.svg)](https://github.com/zSnowww/slothsort/actions/workflows/ci.yml)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Hacktoberfest 2026 · Week 3](https://img.shields.io/badge/Hacktoberfest_2026-Week_3%3A_Slow_and_Steady-orange)](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)

SlothSort analiza tus diálogos de Telegram, propone carpetas con Gemma y las crea mediante MTProto únicamente después de tu revisión chat por chat.

[Ver video de la demo sintética](docs/demo.mp4) · [Ver captura](docs/demo-poster.png)

## Hacktoberfest 2026

Este proyecto se creó para el [Open-Source AI Challenge, semana 3: *Slow and Steady*](https://dev.to/challenges/hacktoberfest-week3-2026-10-19). La idea del reto es usar IA abierta para ahorrar trabajo: aquí, Gemma propone cómo ordenar chats y canales sin que tengas que crear cada carpeta a mano. La revisión y la decisión final siguen siendo tuyas.

La candidatura a DEV todavía no está publicada. Al presentarla, SlothSort se orienta a:

- **Premio general** del reto, por aplicar un modelo de pesos abiertos a una tarea repetitiva.
- **[Best Use of Gemma](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)**, porque `gemma3:4b` es el modelo predeterminado para clasificar diálogos mediante Ollama; la [demo sintética](docs/demo.mp4) muestra una propuesta calculada con él.

Estas son categorías a las que apunta el proyecto, no premios ni una inscripción ya confirmados. Los [criterios y categorías oficiales](https://dev.to/challenges/hacktoberfest-week3-2026-10-19) pertenecen a DEV.

## Qué hace

- Se conecta como usuario mediante Telethon y MTProto; no usa la Bot API.
- Ofrece cuatro modos: solo metadatos; metadatos y descripciones; mensajes recientes de grupos y canales; o mensajes recientes de todos los chats, incluidos privados. La web selecciona grupos y canales de forma inicial.
- Permite elegir 5, 10 o 20 mensajes por chat (10 inicialmente). Consulta mensajes solo al analizar con un modo que los incluye. El texto se envía al motor seleccionado; no se devuelve al navegador ni se conserva en el plan de SlothSort.
- Permite elegir Ollama, Antigravity CLI (`agy`), Codex CLI u OpenCode CLI. Los motores CLI requieren confirmación explícita porque pueden enviar los datos consultados a proveedores externos y conservar sus propias sesiones.
- Consulta las carpetas existentes y evita proponer títulos duplicados.
- Muestra una propuesta y una estimación de confianza por chat. Las propuestas claras quedan preseleccionadas, las dudosas esperan tu decisión y las de confianza baja quedan sin carpeta.
- Permite mover o quitar cada chat, y editar el nombre de una carpeta antes de aplicar.
- Muestra avisos de progreso, éxito y error; permite deshacer la última creación de carpetas si estas no han sido modificadas después.

## 1. Preparar credenciales de Telegram

Obtén tu `api_id` y `api_hash` en [my.telegram.org](https://my.telegram.org), sección **API development tools**. El `api_hash` es secreto.

```bash
cp .env.example .env
```

Completa en `.env`:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=tu_hash_secreto
```

`.env` y los archivos `.session` están ignorados por Git.
El archivo `.env` está oculto en algunos exploradores de archivos; activa la visualización de archivos ocultos si no lo ves. La aplicación lo carga automáticamente al iniciar, sin reemplazar variables ya definidas en el entorno.

## 2. Iniciar sesión una vez

```bash
uv sync
uv run python scripts/login.py
```

Telegram pedirá tu teléfono, el código recibido y, si tienes verificación en dos pasos, la contraseña. La sesión queda guardada en `.data/slothsort.session` con permisos solo para tu usuario.

> El archivo de sesión equivale a una credencial de acceso. No lo compartas, no lo subas a GitHub y no lo copies a otra máquina sin protegerlo.

## 3. Ejecutar

```bash
ollama pull gemma3:4b
uv run uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000`, elige el motor y el nivel de análisis, genera una propuesta y revisa cada chat antes de crear carpetas. La confianza es una estimación del modelo, no una probabilidad calibrada.
La configuración inicial analiza solo los primeros tres chats para que la prueba sea breve en CPU. Aumenta `SLOTHSORT_MAX_CHATS` en `.env` y reinicia el servidor para ampliar el lote. La web muestra la etapa en curso mientras analiza.

Los conectores CLI usan las autenticaciones y modelos configurados en cada herramienta. La app no envía las credenciales de Telegram a esos procesos, ejecuta cada análisis desde un directorio temporal y solicita confirmación antes de pasar los datos de chats. Aun así, un CLI puede usar la nube o guardar su propia conversación; revisa su proveedor y política de datos antes de seleccionarlo. Ollama sigue siendo la opción local predeterminada. Estos conectores tienen pruebas automatizadas con procesos simulados, pero no se han validado con todas las versiones y configuraciones reales de los CLI.

### Demo sin cuenta de Telegram

Con Ollama y `gemma3:4b` disponibles, ejecuta `uv run python -m scripts.demo` y abre `http://127.0.0.1:8001`. Esta versión usa chats inventados pero clasifica con el modelo real. La creación y reversión de carpetas se simulan en memoria: **nunca se conecta a Telegram**. El aviso amarillo en la interfaz identifica la demo.

El video incluido en `docs/demo.mp4` se grabó con esta modalidad. Para que dure 16 segundos, reutiliza una propuesta ya calculada por Gemma y omite la espera de inferencia; el flujo de revisión, creación simulada y reversión sí se capturó en vivo. Para volver a generarlo, instala Playwright en un entorno temporal con `uv run --with playwright playwright install ffmpeg` y ejecuta `uv run --with playwright python -m scripts.record_demo` mientras el servidor de demo esté activo. Requiere Chromium y ffmpeg en el sistema.

Después de crear carpetas, **Deshacer última creación** elimina solo las carpetas que SlothSort creó en esa operación y que siguen iguales en Telegram. No modifica carpetas preexistentes. El botón funciona mientras este proceso del servidor conserve el historial en memoria; reiniciarlo lo borra.

## Pruebas

```bash
uv run pytest
```

Las pruebas usan dobles de Telegram y Ollama: no necesitan credenciales, no se conectan a tu cuenta y no crean carpetas reales.

## Arquitectura

```text
Telegram ──MTProto/Telethon──► FastAPI ──contexto elegido──► motor seleccionado
                                  │
                                  └── revisión por chat ── aprobación ──► dialog filters
                                                                       └── deshacer creación
```

Telegram denomina `dialog filters` a las carpetas de chats. SlothSort crea filtros con listas explícitas de diálogos mediante `messages.updateDialogFilter`.

## Límites conocidos

- La autenticación inicial se realiza en la terminal, no en el navegador.
- Una propuesta vive en memoria y se consume una sola vez.
- Todavía no edita ni elimina carpetas existentes.
- Deshacer no recupera el historial tras reiniciar el servidor y no borra carpetas modificadas por otro cliente.
- Los mensajes, cuando se habilitan, se limitan a 5, 10 o 20 de los más recientes por chat y a 300 caracteres por mensaje; nunca se descargan archivos multimedia. La muestra reciente puede no representar el tema habitual de un chat.
- La calidad de la clasificación depende del contexto disponible. Un nombre ambiguo puede quedar sin carpeta.
- Telegram aplica límites diferentes según la cuenta y puede rechazar carpetas adicionales.

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md). Las mejoras pequeñas y acompañadas por pruebas son bienvenidas.

## Licencia

[MIT](LICENSE)
