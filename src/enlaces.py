"""Enlaces permanentes a un mensaje de Telegram.

Vive aparte porque lo necesitan `handlers` y `admin_report`, y el segundo no
puede importar al primero sin ciclo.

⚠️ **Solo para los avisos por privado al admin.** En el grupo sigue en pie la
regla de no publicar enlaces clicables hacia spammers: allí van nombre e id.
"""
from __future__ import annotations

from types import SimpleNamespace


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


def al_perfil(user_id, nombre: str, username: str | None = None) -> str:
    """`<a>` al perfil de una persona, o su nombre a secas si no hay id ni @.

    Con @usuario va `https://t.me/<usuario>`, que abre siempre. La mención por id
    (`tg://user?id=`) es el respaldo: la Bot API solo garantiza que funcione si la
    persona habló con el bot o es miembro del chat donde se menciona, y el privado
    del admin no es ese chat. Por eso el aviso de borrados salía con el nombre
    sin enlace (29-oct-2026). `nombre` llega ya escapado.
    """
    uname = (username or "").lstrip("@")
    if uname and uname.replace("_", "").isalnum():
        return f'<a href="https://t.me/{uname}">{nombre}</a>'
    if user_id:
        return f'<a href="tg://user?id={user_id}">{nombre}</a>'
    return nombre


def al_grupo(chat_id, titulo: str, username: str | None = None,
             message_id: int | None = None) -> str:
    """`<a>` al grupo, o el título a secas si no tiene enlace posible.

    Público → `https://t.me/<username>`. Supergrupo privado → no hay enlace al chat
    sin un mensaje, así que se usa `message_id`: abre el grupo en ese punto aunque
    el mensaje ya no exista. `titulo` llega ya escapado.
    """
    uname = (username or "").lstrip("@")
    if uname and uname.replace("_", "").isalnum():
        return f'<a href="https://t.me/{uname}">{titulo}</a>'
    url = al_mensaje(SimpleNamespace(id=chat_id, username=None), message_id)
    return f'<a href="{url}">{titulo}</a>' if url else titulo

