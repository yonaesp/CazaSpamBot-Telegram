# Scripts de utilidad

Herramientas sueltas que complementan al bot. Todas se ejecutan **dentro del
contenedor** (`docker exec -it cazaspam-bot python -m scripts.<nombre>`) y la
mayoría requiere Telethon configurado (ver sección 3 de `.env.example`).

| Script | Qué hace |
|---|---|
| `telethon_login.py` | Autentica la cuenta secundaria de Telethon en dos pasos (`request` pide el código, `confirm <código>` crea `data/telethon.session`). Es lo primero que ejecutas si activas Telethon. |
| `list_my_groups.py` | Lista los grupos/canales donde la cuenta Telethon es miembro y marca si están entre tus `MODERATED_CHAT_IDS`. Útil para diagnosticar. |
| `analyze_members.py` | Barrido de miembros sospechosos de cada grupo (perfiles spam, dormidos, etc.). Por defecto **solo reporta**, no actúa. |
| `analyze_user.py` | Informe completo de un usuario concreto (`python -m scripts.analyze_user @username`): perfil, historial, señales. |
| `capture_rose_welcomes.py` | Migración desde el bot Rose: captura el welcome y las rules que tenías configurados en Rose y los importa a la base de datos del bot. Solo útil si vienes de Rose. |

> Ninguno de estos scripts ejecuta acciones de moderación por sí mismo: son de
> diagnóstico/importación. Las acciones siempre pasan por el bot y su auditoría.
