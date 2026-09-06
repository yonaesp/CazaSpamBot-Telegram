"""Detector: usuario nuevo que REENVÍA un mensaje desde un canal/bot externo
en su primer mensaje o en los primeros minutos tras unirse.

Patrón de spam clásico:
 1. Cuenta nueva entra al grupo.
 2. En su primer mensaje (o pocos segundos/minutos después) reenvía contenido
    promocional desde un canal externo: estafa, criptomonedas, contenido adulto,
    promoción de otro grupo, etc.
 3. Los usuarios reales casi nunca reenvían contenido de canales como primer
    aporte: primero saludan, hacen una pregunta o aportan algo propio.

Por tanto, "primer mensaje = forward desde canal/bot" es señal muy fuerte de spam.
"""
from __future__ import annotations


from telegram import Message

from ..i18n import t
from . import Hit

# Ventana en segundos desde el primer_seen del user para que un forward cuente
# como "primeros minutos" (3 min por defecto).
EARLY_WINDOW_S = 180


def _es_reenvio_de_uno_mismo(
    msg: Message, origin_type: str, origin_user_id: int | None, origin_name: str | None,
) -> bool:
    """¿El mensaje reenviado es SUYO PROPIO?

    Reenviarse algo de uno mismo (desde Mensajes Guardados, o desde otro chat
    donde escribió) no es traer contenido de fuera, que es justo lo que este
    detector busca. Es lo que hace cualquiera que rescata una captura o un dato
    que ya había mandado en otro sitio.

    Caso real (7-sep-2026, Windows 11): «Kleo» entró, se verificó y reenvió un
    mensaje SUYO con la captura de una compra y 165 caracteres preguntando si su
    licencia era retail. `origin_name` era su propio usuario. Sumó 80 aquí y 70 en
    `first_msg_media` (que ya había dictaminado perfil NO sospechoso) = 150, o sea
    ban federado en los cuatro grupos y reporte a Telegram, sin que una sola regla
    de contenido hubiera saltado. En los 15 casos del histórico este detector solo
    ha acertado con origen CANAL (7 de 7); con origen usuario nunca ha cazado nada.
    """
    autor = getattr(msg, "from_user", None)
    if autor is None:
        return False
    if origin_type == "user" and origin_user_id is not None:
        return origin_user_id == autor.id
    # Con la privacidad de reenvío puesta, Telegram oculta la cuenta y solo deja el
    # nombre visible: no hay id que comparar, así que se compara ese nombre.
    if origin_type == "hidden_user" and origin_name:
        propios = {
            (autor.first_name or "").strip(),
            f"{autor.first_name or ''} {autor.last_name or ''}".strip(),
        }
        return origin_name.strip() in propios - {""}
    return False


def check(
    msg: Message,
    is_first_msg: bool,
    seconds_since_first_seen: float | None = None,
) -> Hit:
    """Detecta forward desde canal/bot en primer mensaje o primeros 3 min.

    Args:
      msg: el mensaje de Telegram.
      is_first_msg: True si el bot lo considera primer mensaje (msg_count<=window).
      seconds_since_first_seen: segundos desde que el bot vio al user por primera
        vez. None si desconocido.
    """
    in_early_window = (
        seconds_since_first_seen is not None
        and seconds_since_first_seen <= EARLY_WINDOW_S
    )
    if not is_first_msg and not in_early_window:
        return Hit.none()

    # PTB 21+: forward_origin (preferido). Fallbacks legacy: forward_from_chat,
    # forward_from, forward_sender_name.
    origin = getattr(msg, "forward_origin", None)
    fwd_chat = getattr(msg, "forward_from_chat", None)
    fwd_user = getattr(msg, "forward_from", None)
    fwd_sender_name = getattr(msg, "forward_sender_name", None)

    if not (origin or fwd_chat or fwd_user or fwd_sender_name):
        return Hit.none()

    origin_type: str = "unknown"
    origin_name: str | None = None
    origin_user_id: int | None = None

    if fwd_chat is not None:
        origin_type = fwd_chat.type or "channel"  # channel, supergroup, group
        origin_name = fwd_chat.username or fwd_chat.title
    elif fwd_user is not None:
        origin_type = "bot" if getattr(fwd_user, "is_bot", False) else "user"
        origin_name = fwd_user.username or fwd_user.first_name
        origin_user_id = getattr(fwd_user, "id", None)
    elif fwd_sender_name:
        origin_type = "hidden_user"
        origin_name = fwd_sender_name
    elif origin is not None:
        # PTB ≥21 — origin puede ser MessageOriginChannel / MessageOriginUser
        # / MessageOriginHiddenUser. Reflexionamos sobre type field.
        otype = getattr(origin, "type", "")
        if otype == "channel":
            origin_type = "channel"
            ch = getattr(origin, "chat", None)
            origin_name = (ch.username or ch.title) if ch else None
        elif otype == "user":
            u = getattr(origin, "sender_user", None)
            origin_type = "bot" if (u and getattr(u, "is_bot", False)) else "user"
            origin_name = (u.username or u.first_name) if u else None
            origin_user_id = getattr(u, "id", None) if u is not None else None
        elif otype == "hidden_user":
            origin_type = "hidden_user"
            origin_name = getattr(origin, "sender_user_name", None)
        elif otype == "chat":
            origin_type = "chat"
            sc = getattr(origin, "sender_chat", None)
            origin_name = (sc.username or sc.title) if sc else None

    # Un reenvío de uno mismo no es contenido traído de fuera: no hay nada que
    # puntuar. Va ANTES de la severidad para que no dependa del origen ni de la
    # ventana temprana.
    if _es_reenvio_de_uno_mismo(msg, origin_type, origin_user_id, origin_name):
        return Hit.none()

    # Severidad:
    # - Forward desde channel en primer msg → BAN directo (score 100)
    # - Forward desde bot en primer msg → BAN (score 95)
    # - Forward desde user/hidden_user en primer msg → KICK (score 80)
    if origin_type in ("channel", "chat"):
        score = 100
        sev = t("reason.forward_channel")
    elif origin_type == "bot":
        score = 95
        sev = t("reason.forward_bot")
    else:
        score = 80
        sev = t("reason.forward_other", origin_type=origin_type)

    # Si está en la ventana temprana pero ya tiene varios mensajes, suaviza un poco
    if not is_first_msg and in_early_window:
        score = max(70, score - 15)
        sev += " " + t("reason.forward_early_window", seconds=EARLY_WINDOW_S)

    reasons = [sev]
    if origin_name:
        reasons.append(t("reason.forward_origin", origin_name=origin_name))

    return Hit(
        rule="forward_first_msg",
        score=score,
        reason=" + ".join(reasons),
        payload={
            "origin_type": origin_type,
            "origin_name": origin_name,
            "is_first_msg": is_first_msg,
            "seconds_since_first_seen": seconds_since_first_seen,
        },
    )
