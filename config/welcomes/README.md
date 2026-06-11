# Mensajes de bienvenida personalizables

El bot manda un saludo simpático a los perfiles que entran y parecen legítimos
(cuenta antigua, con foto, nombre normal). Esos saludos se editan aquí, en
archivos de texto. **No hace falta tocar código.**

## Formato

- **Una frase por línea.**
- Líneas vacías y las que empiezan por `#` se ignoran (son comentarios).
- Usa `{name}` donde quieras que aparezca el nombre del usuario.
- Debajo de cada saludo, el bot añade siempre un pie fijo con las normas.

Ejemplo:

```
# Mi grupo de fotografía
📷 Bienvenido/a {name}. Aquí se habla de diafragmas a las 3 AM.
🎞️ {name}, otro adicto al revelado. Bienvenido/a.
```

## Qué archivo se usa para cada grupo

Para un mensaje que entra en el chat con id `-100123456789`, el bot busca por orden:

1. `config/welcomes/-100123456789.txt`  → saludos SOLO de ese grupo (temáticos)
2. `config/welcomes/generic.txt`        → saludo genérico (este se versiona)
3. dos frases por defecto incluidas en el código (último recurso)

Así cada grupo puede tener su propia personalidad. Para saber el chat_id de un
grupo, añade @getidsbot o @RawDataBot al grupo.

## Importante

- Los archivos por grupo (`<chat_id>.txt`) están en `.gitignore`: cada quien
  pone los suyos sin subirlos al repo. El repo solo trae `generic.txt` de ejemplo.
- Para **desactivar** del todo los saludos simpáticos: pon
  `FRIENDLY_WELCOMES_ENABLED=false` en tu `.env`. (Los usuarios legítimos
  seguirán entrando sin verificación; simplemente no se publica el saludo.)
- También puedes fijar un welcome fijo por grupo desde Telegram con `/setwelcome`.
