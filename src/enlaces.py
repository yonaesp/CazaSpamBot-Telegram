"""Enlaces permanentes a un mensaje de Telegram.

Vive aparte porque lo necesitan `handlers` y `admin_report`, y el segundo no
puede importar al primero sin ciclo.

⚠️ **Solo para los avisos por privado al admin.** En el grupo sigue en pie la
regla de no publicar enlaces clicables hacia spammers: allí van nombre e id.
"""
from __future__ import annotations


def al_mensaje(chat, message_id: int | None) -> str | None:
    """Permalink de ese mensaje, o None si el chat no tiene ninguno.

    Tres formas, y solo dos existen:
      - grupo o canal PÚBLICO → `https://t.me/<username>/<id>`;
      - supergrupo privado    → `https://t.me/c/<id sin el -100>/<id>`;
      - grupo básico o DM     → no hay permalink, y no se inventa.

    La forma plana vale también en grupos con foros: no lleva `message_thread_id`
    (comprobado con un enlace real de Windows 11, que tiene temas).
    """
    if not message_id or chat is None:
        return None
    uname = getattr(chat, "username", None)
    if uname:
        return f"https://t.me/{uname}/{message_id}"
    cid = str(getattr(chat, "id", "") or "")
    if cid.startswith("-100") and cid[4:].isdigit():
        return f"https://t.me/c/{cid[4:]}/{message_id}"
    return None
