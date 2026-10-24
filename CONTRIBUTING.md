# Cómo contribuir

Gracias por ayudar a que SlothSort sea más útil y seguro.

1. Abre o elige un issue y comenta que quieres trabajarlo.
2. Crea una rama corta y enfocada.
3. Ejecuta `uv sync` y `uv run pytest`.
4. Mantén el cambio pequeño; añade pruebas cuando cambie el comportamiento.
5. Abre un pull request explicando el problema, la solución y cómo la probaste.

## Principios del proyecto

- Ninguna carpeta se crea sin vista previa y aprobación explícita.
- Nunca confiar directamente en identificadores o títulos producidos por el modelo.
- Consultar mensajes solo en un modo que los incluya. El modo inicial incluye grupos y canales, no chats privados.
- Requerir consentimiento antes de enviar contexto a conectores CLI que pueden usar la nube.
- No incluir textos de mensajes en respuestas HTTP, logs ni planes persistidos.
- No registrar teléfonos, códigos, contraseñas, API hashes ni sesiones.
- Mantener pruebas que no necesiten Telegram ni un modelo instalado.

## Ideas para empezar

- Añadir reglas para canales, bots, grupos y chats privados.
- Mejorar el muestreo de mensajes para combinar actividad reciente y antigua.
- Añadir una exportación JSON del plan.
- Añadir pruebas de integración opcionales con Telegram y Ollama.
- Mejorar accesibilidad y traducciones.
