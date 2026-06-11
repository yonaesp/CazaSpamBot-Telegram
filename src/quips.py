"""Catálogo de frases sarcásticas al banear, por regla disparada.

Tono: humor seco, "hasta lueguito", irónico. Sin insultos. Frase corta y
punzante. En plural cuando es batch.

Diseño: cada regla tiene 8-12 variantes, se elige una al azar.
El mensaje resultante se publica en el grupo y se borra a los `PUBLIC_QUIP_DELETE_AFTER_S`
segundos (default 1h para bans individuales, 0 = nunca para batches).
"""
from __future__ import annotations

import random

_QUIPS_BY_RULE: dict[str, list[str]] = {
    "non_allowed_script": [
        "👋 <b>{name}</b>, aquí no se habla {extra}. Bai bai (adiós en chino, por si te pilla lejos).",
        "🐉 <b>{name}</b>, Po diría skadoosh. Yo digo ban.",
        "🥋 <b>{name}</b>, como diría Bruce Lee: be water… pero hacia la salida.",
        "🌸 <b>{name}</b>, te vas con honor (que diría Mulan). Bai bai.",
        "🧙 Confucio dijo: el que entra con spam, sale con ban. <b>{name}</b>, fuera.",
        "🚫 <b>{name}</b>, español o nada. Zai jian.",
        "🗑️ <b>{name}</b> entra escribiendo en {extra}. Spam de manual. Fuera.",
        "🌏 <b>{name}</b>, esto no es un grupo de {extra}. Te bajas aquí.",
        "📭 <b>{name}</b>, tu mensaje en {extra} no es para nosotros.",
        "🛂 Frontera idiomática cerrada para <b>{name}</b>. El {extra} no pasa.",
        "🚪 <b>{name}</b>, salida directa. Bai bai, hasta nunca.",
        "📕 <b>{name}</b>, el {extra} se queda en su diccionario.",
        "🎫 <b>{name}</b>, este billete era para un grupo en {extra}. No hay reembolso.",
        "🪧 <b>{name}</b>, aquí no se habla {extra}. A la calle.",
        "🥡 <b>{name}</b>, el menú es en español. Zai jian.",
        "🐲 <b>{name}</b>, el dragón te escupe fuera. Bai bai.",
        "🎋 Jackie Chan no daría su aprobación a esto. Adiós, <b>{name}</b>.",
    ],
    "external_mention_or_link": [
        "🎣 <b>{name}</b> pescando gente para otro chat en su primer mensaje. Aquí no pica nadie, recoge la caña 🎣",
        "📢 <b>{name}</b>, ¿primer mensaje y ya invitando a otro chat? Clásico spam de manual. Fuera.",
        "🚷 <b>{name}</b>, esto no es un tablón de anuncios. Hasta lueguito.",
        "🪤 <b>{name}</b> cazado mencionando a externos antes de saludar. Spam 101.",
        "🔗 <b>{name}</b>, reparte tus enlaces en otra parte. Adiós.",
        "📨 Carta sin remitente útil de <b>{name}</b>. Directa a la papelera.",
        "🎟️ <b>{name}</b>, las invitaciones a otros grupos se cobran a la puerta. La tuya, con un ban.",
        "🗞️ <b>{name}</b>, ahórrate los panfletos. Hasta lueguito.",
        "🚧 <b>{name}</b>, no se permiten desvíos a otros grupos. A la calle.",
        "📣 <b>{name}</b>, deja de pregonar otros chats. A casa.",
        "🪧 <b>{name}</b>, ni un cartel publicitario ni dos. Fuera.",
    ],
    "cas_match": [
        "🛡️ <b>{name}</b> está marcado en CAS (Combot Anti-Spam). Baneado en miles de grupos, aquí también.",
        "🌐 CAS confirma: spammer global conocido. <b>{name}</b>, fuera.",
        "📋 <b>{name}</b> aparece en la lista federada de spammers de Telegram. Baneo preventivo.",
        "🤖 Otro bot de spam reciclado. <b>{name}</b>, CAS te delató.",
        "🚨 <b>{name}</b>: varios admins en distintos grupos te marcaron como spam. Aquí asumimos lo mismo.",
        "📑 Tu expediente CAS está cargadito, <b>{name}</b>. No nos hacen falta más pruebas.",
        "🔎 La comunidad ya te conoce, <b>{name}</b>. Hasta lueguito.",
        "📛 <b>{name}</b> con la etiqueta CAS pegada. Limpieza preventiva.",
    ],
    "reaction_farming": [
        "❤️ <b>{name}</b>: 0 mensajes pero {extra}. Vete a regalar likes a tu casa 💔",
        "🎁 <b>{name}</b>, si solo das likes y nunca hablas, ¿eres persona o tostadora con wifi?",
        "💘 <b>{name}</b> baneado por farmear reacciones ({extra}). Cariño sin contexto, no, gracias.",
        "🤡 <b>{name}</b> dando corazones en racha sin escribir una palabra. Bot detectado, fuera.",
        "📊 {extra} pero ni un 'hola'. <b>{name}</b>, baneado.",
        "👍 Likes industriales detectados. <b>{name}</b>, hasta lueguito.",
        "🔁 <b>{name}</b> reacciona pero no respira. Patrón de bot, adiós.",
        "🎯 {extra} sin hablar = farming. <b>{name}</b>, fuera del programa.",
        "💖 <b>{name}</b>, ese cariño no solicitado lo guardas para otro grupo. Adiós.",
    ],
    "url_blocklist": [
        "🔗 <b>{name}</b> compartiendo {extra}. Acortadores en blocklist, baneado.",
        "📎 <b>{name}</b>, ¿en pleno 2026 con {extra}? Por favor. Adiós.",
        "🧹 Limpieza: <b>{name}</b> spameando con {extra}. Fuera.",
        "🪒 <b>{name}</b> con su acortador {extra}. Cortado de raíz.",
        "🚫 <b>{name}</b>, {extra} no pasa el filtro. A la calle.",
        "🎯 <b>{name}</b>, los acortadores típicos los detecto al instante. Hasta lueguito.",
        "📛 URL acortada sospechosa de <b>{name}</b>. Adiós.",
    ],
    "manual_admin_ban": [
        "🔨 <b>{name}</b> baneado por orden del admin. Sin más preguntas.",
        "👮 El jefe ha hablado. <b>{name}</b>, fuera.",
        "📣 Decisión administrativa: <b>{name}</b> baneado.",
        "⚖️ Mazo del admin sobre <b>{name}</b>. Sentencia firme.",
        "🚪 <b>{name}</b>, te has ganado un /ban manual. Hasta lueguito.",
        "📜 Por orden directa, <b>{name}</b> al exterior.",
    ],
    "manual_admin_unban": [
        "🕊️ <b>{name}</b> desbaneado. Bienvenida de vuelta, la puerta está abierta.",
        "🤝 Reconciliación: <b>{name}</b> vuelve al grupo. Sin rencores.",
        "🚪 Puerta abierta de nuevo para <b>{name}</b>. A portarse bien.",
        "🪄 Magia administrativa: <b>{name}</b> regresa al grupo.",
        "✅ <b>{name}</b> ya puede volver. El admin levantó el ban.",
        "🌅 Nuevo día para <b>{name}</b>. Desbaneado y de vuelta.",
        "🔓 Cerrojo retirado. <b>{name}</b>, adelante.",
        "🍻 <b>{name}</b> de vuelta. Que sirva de borrón y cuenta nueva.",
    ],
    "federation_known_ban": [
        "🔁 <b>{name}</b> intentó reentrar estando en la lista federada. Baneado otra vez. Persistente.",
        "♻️ <b>{name}</b> ya estaba baneado en otro de mis grupos. Aquí también, hasta nunca.",
        "🚪 <b>{name}</b>, no se vuelve. Baneado en federación.",
        "🔐 La puerta federada está cerrada para <b>{name}</b>. Adiós.",
        "📕 <b>{name}</b>, en mi libro negro federado. Re-baneado al instante.",
        "🛂 Documentación federada caducada para <b>{name}</b>. Fuera.",
        "🎫 Tu pase fue revocado en todos mis grupos, <b>{name}</b>. Sigue intentándolo en otra parte.",
    ],
    "inline_buttons_from_user": [
        "🔘 <b>{name}</b> trae botones inline en su mensaje. Eso solo lo hacen canales y bots, no es de aquí.",
        "🤖 Mensaje de <b>{name}</b> con botones = forward de canal promocional. Adiós.",
        "📲 Botones inline en mensaje de user real = imposible. <b>{name}</b> reenvió spam. Fuera.",
        "🚫 <b>{name}</b>, los botones te delatan: no son tuyos. Hasta lueguito.",
        "🔗 <b>{name}</b> trajo botones con enlaces. Patrón típico de spammer reenviador. Cerrado.",
    ],
    "photos_batch_upload": [
        "🕵️ Nuestra unidad de inteligencia confirma: <b>{name}</b> es un bot. Fuera.",
        "🛰️ Dossier clasificado de <b>{name}</b> abierto y cerrado. Bot confirmado.",
        "🎯 Los analistas del grupo señalan a <b>{name}</b>. No pasa el filtro.",
        "🔬 <b>{name}</b> no pasa nuestro test de humanidad. Adiós.",
        "🧠 Inteligencia interna del bot: <b>{name}</b> es marioneta. Hilos cortados.",
        "🛡️ El servicio secreto del grupo tiene fichado a <b>{name}</b>. Hasta nunca.",
        "📂 Carpeta roja para <b>{name}</b>. Cerramos puerta.",
        "🎩 <b>{name}</b>, tu disfraz no engaña a nuestros analistas. Fuera.",
        "🔭 El radar del bot detectó a <b>{name}</b>. No eres quien dices ser.",
        "🪪 <b>{name}</b>, papeles falsificados detectados. Cerrado.",
    ],
    "commercial_ad": [
        "💼 <b>{name}</b> trae catálogo de ofertas. Esto no es Infojobs. Fuera.",
        "🏷️ <b>{name}</b> publicando anuncios como en El Mundo Today. Adiós.",
        "📢 <b>{name}</b> con estructura de panfleto. Aquí no se reparte propaganda.",
        "🪧 Folleto publicitario detectado de <b>{name}</b>. A la papelera.",
        "🎯 <b>{name}</b>, los anuncios se pagan. El tuyo te costó el ban.",
        "💼 Currículum spam de <b>{name}</b> rechazado. La oferta era falsa, claro.",
        "📰 <b>{name}</b> con panfleto formateado de copy-paste. Hasta nunca.",
        "🚫 Esto no es un tablón de empleo, <b>{name}</b>. Adiós.",
    ],
    "dormant_bot_mention": [
        "👻 <b>{name}</b> resucita tras años en silencio... para promocionar un bot. Cuenta vendida o hackeada. Fuera.",
        "🧟 <b>{name}</b> vuelve de entre los muertos y lo primero que hace es spam de bots. Eso no lo hace un humano. Adiós.",
        "📉 <b>{name}</b>, un año callado y reapareces citando un bot raro. Tu cuenta cambió de dueño. Baneado.",
        "🔐 <b>{name}</b> inactivo eternamente y de golpe menciona un bot. Patrón de cuenta comprometida. Cerrado.",
        "⚰️ <b>{name}</b> sale de la tumba solo para hacer publi de un bot. Cuenta secuestrada. Hasta nunca.",
    ],
    "bio_spam": [
        "📝 <b>{name}</b> trae la bio con escaparate completo. Catálogo cerrado.",
        "🛍️ Bio de <b>{name}</b> = anuncio comercial. Adiós sin abrir el envoltorio.",
        "🔗 <b>{name}</b>, los enlaces seducción te delatan en la bio. Hasta nunca.",
        "🚪 Bio publicitaria detectada: <b>{name}</b> fuera antes de saludar.",
        "📛 <b>{name}</b>, tu perfil grita 'sígueme en mi canal'. No, gracias.",
        "💼 <b>{name}</b> con bio de tienda. Esto no es Wallapop.",
        "🚫 Bio sospechosa para <b>{name}</b>: hablamos español, no buscamos catálogo.",
    ],
    "obvious_spam_profile": [
        "🛂 <b>{name}</b> entra con perfil de spammer marcado. Sin más trámites.",
        "🚫 Perfil de <b>{name}</b> = ficha de spammer. Adiós antes de empezar.",
        "🔎 <b>{name}</b> trae el cartel puesto. Fuera.",
        "🤖 <b>{name}</b>, tu perfil habla por ti. Hasta nunca.",
        "📛 <b>{name}</b>, evidente. No te molestes en escribir.",
        "🛑 Perfil de spam evidente: <b>{name}</b>. Cerramos puerta de entrada.",
    ],
    "forward_first_msg": [
        "📨 <b>{name}</b> entró reenviando spam de un canal. Adiós.",
        "🔁 Primer aporte de <b>{name}</b> fue un forward. Predecible. Baneado.",
        "📤 <b>{name}</b>, los reenvíos a pelo no son saludos. Fuera.",
        "🚪 <b>{name}</b> reenvió contenido externo como primer mensaje. Patrón spammer clásico.",
        "🤖 <b>{name}</b> trae el menú forward, sin presentarse. Cerramos puerta.",
        "📡 Forward desde canal en el primer mensaje de <b>{name}</b>. Eso no se hace.",
    ],
    "first_msg_media": [
        "📸 <b>{name}</b>, primera vez en el grupo y ya con foto promocional. Hasta lueguito spammer 👋",
        "🖼️ <b>{name}</b>, una imagen vale más que mil palabras... y la tuya vale un ban. Adiós.",
        "📷 Llega, posa, spamea. <b>{name}</b>, fuera del casting 🎬",
        "🚫 <b>{name}</b>, esto no es Instagram. Hasta lueguito.",
        "👋 Hasta lueguito spammer, <b>{name}</b>. Tu foto de bienvenida no nos engañó.",
        "🎯 <b>{name}</b>: cuenta nueva + primer mensaje con foto = patrón spam clásico. Adiós.",
        "🧹 Limpieza visual: <b>{name}</b> con su foto-anuncio, fuera del grupo.",
        "📺 Anuncio no solicitado. <b>{name}</b>, directo a la papelera.",
        "🎨 <b>{name}</b> con galería de spam recién abierta. Cierre inmediato.",
        "🖼️ <b>{name}</b> presentándose con catálogo gráfico. Spam de manual, bye.",
        "📰 <b>{name}</b>, portada de revista no autorizada. Retirada y baneo.",
        "🎭 <b>{name}</b> hace su entrada con foto promocional. Telón cerrado.",
    ],
    "jfm_too_fast": [
        "🏃 <b>{name}</b> escribió en {extra}s desde que entró. Más rápido que un humano puede teclear. Bye bot.",
        "⚡ <b>{name}</b>, ni un saludo, ¿eh? Directo al spam. Hasta lueguito.",
        "🤖 Bot programado detectado: <b>{name}</b> en {extra}s desde el join. Adiós.",
        "🕹️ <b>{name}</b> ni leyó las normas. {extra}s y a spamear. Fuera.",
        "💨 Velocidad imposible para humano. <b>{name}</b> al cubo.",
        "⏱️ {extra}s desde el join. <b>{name}</b>, eso es récord olímpico de spam.",
    ],
    "jfm_fast": [
        "💨 <b>{name}</b> entró y escribió en {extra}s. Sospechosamente rápido. Adiós.",
        "🐇 <b>{name}</b>, demasiado deprisa. Bot probable.",
        "⏩ <b>{name}</b> en modo fast-forward. Banneado por sospecha.",
    ],
    "jfm_cron": [
        "🕐 <b>{name}</b> esperó las horas justas antes de spamear. Bot con cron detectado.",
        "⏰ Patrón de cron en <b>{name}</b>: bot programado. Hasta lueguito.",
        "📅 Calendario de spam de <b>{name}</b> incumplido. Adiós.",
        "⌛ <b>{name}</b> aguantó exactamente para spamear. Patrón automático claro.",
    ],
    "tg_deeplink": [
        "🔗 <b>{name}</b> intentando colar deeplink phishing. Hasta lueguito.",
        "🪝 <b>{name}</b>, el <code>tg://</code> de phishing es de los más viejos del libro. Adiós.",
        "🎣 Pesca tg:// detectada. <b>{name}</b> a la calle.",
        "📛 Deeplink sospechoso de <b>{name}</b>. Banneado preventivamente.",
        "🚫 <b>{name}</b>, los enlaces <code>tg://</code> de invitación masiva no cuelan aquí.",
        "🛡️ Phishing tg:// neutralizado. <b>{name}</b> fuera del juego.",
    ],
    "premium_new_link": [
        "⭐ <b>{name}</b>, Premium no compra legitimidad. Cuenta nueva + link en primer mensaje = spam. Bye.",
        "💎 Bonito Premium tienes, <b>{name}</b>. Lástima que lo uses para spamear. Hasta nunca.",
        "🌟 Premium recién hecho + primer mensaje con link. Buen intento, <b>{name}</b>. Pero no.",
        "💳 <b>{name}</b> pagó Premium para hacer spam. Inversión perdida. Adiós.",
        "✨ Premium no es escudo, <b>{name}</b>. Spammer reconocido.",
    ],
    "lols_match": [
        "📁 En la ficha delictiva de <b>{name}</b> ya cabe poco. Antecedentes para parar un tren. ¡Hasta luego!",
        "🚓 <b>{name}</b> con prontuario tan abultado que tiembla la guardia civil. Adiós.",
        "📜 Hoja de antecedentes de <b>{name}</b>: spam, spam, spam y un poco más. Hasta nunca.",
        "🪦 <b>{name}</b> ya tenía lápida puesta. Solo ponemos la flor. Que descanse en paz.",
        "💼 Currículum de <b>{name}</b>: 0 trabajos legítimos, máster en spam. Rechazado.",
        "🚨 <b>{name}</b>, tu reputación te precede y huele a azufre. Adiós.",
        "🗃️ Expediente de <b>{name}</b> tiene más páginas que el Quijote. Cerrado a cal y canto.",
        "🎭 <b>{name}</b> con careta puesta, pero ya te vimos el peluquín. Fuera.",
        "🪤 <b>{name}</b> cae siempre en la misma trampa. Hoy también. Reincidente patético.",
        "📡 La centralita recibió quejas de <b>{name}</b>. Nos sumamos al desfile.",
        "⛓️ <b>{name}</b> reincidente confeso. Ni el comodín del público te salva.",
        "🚔 La poli del barrio tiene a <b>{name}</b> en busca y captura. Colaboramos encantados.",
        "🕵️ El radar lleva tiempo siguiendo a <b>{name}</b>. Aterrizó aquí, fuera.",
        "📛 Pinta de <b>{name}</b>: la conocemos de antes. Cerrado.",
    ],
    "learned_similarity": [
        "🎯 <b>{name}</b> mandando algo que ya catalogué como spam antes. Ban automático.",
        "📚 Tu mensaje coincide con un patrón aprendido como spam, <b>{name}</b>. Adiós.",
        "🤖 Aprendí a detectarte, <b>{name}</b>. Hasta lueguito.",
        "🧠 Mi memoria me dice que esto ya lo banneé antes. <b>{name}</b>, tú también.",
        "♻️ Mensaje reciclado de spam previo. <b>{name}</b> fuera.",
        "📖 Capítulo: 'spam que ya conocemos'. Protagonista: <b>{name}</b>. Final: ban.",
    ],
    "warns_limit": [
        "📣 <b>{name}</b> ha llegado al límite de warns. Ban federado. Hasta lueguito.",
        "⛔ Tres strikes, <b>{name}</b>. Estás fuera de los grupos. Adiós.",
        "⚠️ Aviso final ignorado por <b>{name}</b>. Federación cerrada.",
        "🛑 <b>{name}</b> agotó su crédito de avisos. Banneado en todos los grupos.",
    ],
}

# Mapeo de scripts Unicode a nombre coloquial en español.
_SCRIPT_NAMES = {
    "han": "chino",
    "hiragana": "japonés",
    "katakana": "japonés",
    "hangul": "coreano",
    "cyrillic": "cirílico",
    "arabic": "árabe",
    "hebrew": "hebreo",
    "greek": "griego",
    "devanagari": "hindi",
    "other": "ese idioma",
}


def _format_name(username: str | None, user_id: int | None, first_name: str | None = None) -> str:
    """Formatea identidad SIN crear link clicable al perfil.

    Razón: muchos spammers tienen contenido inapropiado en su perfil
    (porno, scams, etc.). Mostrar @username o un link tg://user?id=
    le daría visibilidad. Mostramos first_name + (id: N) que identifica
    al usuario sin abrir su perfil.
    """
    import html as _h
    nombre = (first_name or "user").strip()
    nombre = _h.escape(nombre[:40]) if nombre else "user"
    if user_id:
        return f"{nombre} (id: <code>{user_id}</code>)"
    return nombre


def _format_extra(rule: str, payload: dict | None) -> str:
    p = payload or {}
    if rule == "non_allowed_script":
        sub = p.get("non_allowed_script") or p
        dom = sub.get("dominant_script", "")
        return _SCRIPT_NAMES.get(dom, dom or "otro idioma")
    if rule == "reaction_farming":
        sub = p.get("reaction_farming") or p
        n = sub.get("reactions", "?")
        s = sub.get("window_s", "?")
        return f"{n} reacciones en {s}s"
    if rule == "url_blocklist":
        sub = p.get("url_blocklist") or p
        hosts = sub.get("hosts", [])
        return ", ".join(hosts) if hosts else "URLs acortadas"
    if rule == "external_mention_or_link":
        sub = p.get("external_mention_or_link") or p
        n = len(sub.get("external_mentions", [])) + len(sub.get("external_tg_links", []))
        return f"{n} mención(es)/enlace(s) externos"
    if rule in ("jfm_too_fast", "jfm_fast", "jfm_cron"):
        sub = p.get(rule) or p
        return str(sub.get("delta_s", "?"))
    return ""


def pick(
    rule: str,
    username: str | None,
    user_id: int | None,
    payload: dict | None,
    first_name: str | None = None,
) -> str | None:
    """Devuelve un quip ya formateado, o None si la regla no tiene catálogo.

    Para reglas compuestas (rule1+rule2), usa la primera reconocida.
    """
    name = _format_name(username, user_id, first_name)
    candidates = []
    for sub_rule in rule.split("+"):
        if sub_rule in _QUIPS_BY_RULE:
            candidates.append(sub_rule)
    if not candidates:
        return None
    chosen_rule = candidates[0]
    extra = _format_extra(chosen_rule, payload)
    template = random.choice(_QUIPS_BY_RULE[chosen_rule])
    return template.format(name=name, extra=extra)


_BATCH_HEADERS = {
    "cas_match": [
        "🛡️ <b>Limpieza CAS del día</b> , los siguientes usuarios estaban marcados globalmente como spammers y aquí también les decimos adiós:",
        "🌐 <b>Barrido CAS</b> , la lista federada anti-spam de Telegram los delató; baneados en todos los grupos del bot:",
        "🧹 <b>Limpieza automática</b> , CAS confirma que estos perfiles son spam, fuera todos:",
        "🚮 <b>Sacando la basura</b> , estos perfiles ya estaban baneados en miles de grupos. Hoy se suman nuestros:",
        "📋 <b>Lista negra del día</b> , CAS los marca, nosotros los rematamos:",
    ],
    "manual_admin_ban": [
        "🔨 <b>Limpieza manual del admin</b> , adiós a los siguientes:",
        "👮 <b>Operativo de limpieza</b> , los siguientes usuarios ya no volverán a molestar:",
        "📣 <b>Decisión administrativa</b> , baneados los siguientes en todos los grupos:",
        "⚖️ <b>Mazazo administrativo</b> , los siguientes ya están fuera:",
    ],
    "suspicious_profile": [
        "🚷 <b>Limpieza de perfiles sospechosos</b> (sin foto, sin nombre, perfiles fantasma):",
        "🧽 <b>Higiene del grupo</b> , adiós a estos perfiles que parecían bots:",
        "🤖 <b>Caza de perfiles fantasma</b> , los siguientes tenían toda la pinta de bots durmientes:",
        "👻 <b>Exorcismo de perfiles</b> , los espíritus fantasma fuera:",
    ],
}

_BATCH_OUTROS = [
    "Sin rencor, hasta lueguito spammers 👋",
    "Nos vemos en el próximo barrido 🧹",
    "Que tengáis mejor suerte spammeando en otro lado.",
    "A regalar likes y links a vuestra casa, no aquí.",
    "Auditados, condenados y federados. Hasta nunca.",
    "Hasta lueguito spammers, que os vaya bonito 👋",
    "Adiós muy buenas, no os echaremos de menos.",
    "Cerrado por hoy. Volved a vuestros agujeros oscuros.",
    "El grupo respira mejor sin vosotros 🌬️",
    "Limpieza terminada. Hasta el próximo barrido 🧽",
]


def _reason_summary(username: str | None, user_id: int, info: dict) -> str:
    name = _format_name(username, user_id, info.get("first_name"))
    if info.get("cas_offenses", 0) > 0:
        return f"{name} , CAS offenses={info['cas_offenses']}"
    reasons = info.get("reasons") or []
    if reasons:
        return f"{name} , {', '.join(reasons[:3])}"
    if info.get("rule"):
        return f"{name} , {info['rule']}"
    return name


def batch_summary(items: list[dict], category: str = "cas_match") -> str:
    """Construye un mensaje en batch listando todos los baneados.

    Si items contiene un solo elemento, usa el quip individual (en singular).
    """
    if not items:
        return ""
    if len(items) == 1:
        it = items[0]
        rule = it.get("rule") or category
        payload = {"cas_offenses": it.get("cas_offenses", 0)} if rule == "cas_match" else (it.get("payload") or {})
        msg = pick(rule=rule, username=it.get("username"), user_id=it.get("user_id"), payload=payload)
        if msg:
            return msg
        return _reason_summary(it.get("username"), it.get("user_id", 0), it)
    header = random.choice(_BATCH_HEADERS.get(category, _BATCH_HEADERS["cas_match"]))
    lines = [header, ""]
    for i, it in enumerate(items, 1):
        line = _reason_summary(it.get("username"), it.get("user_id", 0), it)
        lines.append(f"{i}. {line}")
    lines.append("")
    lines.append(f"<i>{random.choice(_BATCH_OUTROS)}</i>")
    lines.append(f"<i>Total baneados: {len(items)}</i>")
    return "\n".join(lines)
