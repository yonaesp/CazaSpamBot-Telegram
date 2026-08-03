"""Un ban federado tiene que CUMPLIRSE, no solo apuntarse.

Caso real (3-ago-2026): el admin baneó a un usuario el día 2. El ban se aplicó en
dos de los tres grupos y en el tercero no. En la base de datos constaba baneado; en
el grupo seguía escribiendo, con 156 mensajes acumulados. Nadie se enteró porque
`/ban` entonces ni contestaba ni dejaba registro.

Dos agujeros encadenados:
  1. La lista de baneados solo se consultaba al ENTRAR, así que quien ya estaba
     dentro podía escribir indefinidamente.
  2. El barrido nocturno solo sabía REVOCAR bans (si ya no estaba expulsado en
     ningún sitio), nunca re-aplicarlos.
"""
from pathlib import Path


def test_un_baneado_que_escribe_se_re_banea():
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "db.is_banned(user.id)" in cuerpo, (
        "on_message no comprueba la lista de baneados: quien se libre del ban en un "
        "chat puede seguir escribiendo para siempre"
    )
    j = cuerpo.index("db.is_banned(user.id)")
    assert "federation_known_ban" in cuerpo[j:j + 600], "no re-aplica el ban"


def test_la_comprobacion_va_despues_de_la_lista_blanca():
    """Si el admin marcó a alguien como inmune, eso manda: un registro viejo de ban
    no puede volver a expulsarlo."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert cuerpo.index("is_whitelisted") < cuerpo.index("db.is_banned(user.id)"), (
        "la comprobación de baneados se adelanta a la lista blanca")


def test_y_despues_del_admin():
    """Nunca re-banear al propio administrador del bot."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert cuerpo.index("user.id == cfg.admin_user_id") < cuerpo.index("db.is_banned(user.id)")


def test_el_barrido_detecta_los_bans_a_medias():
    """Expulsado en unos grupos y dentro en otros: hay que re-aplicarlo, no ignorarlo."""
    fuente = Path("src/maintenance.py").read_text()
    i = fuente.index("async def _reconcile_banned_users")
    cuerpo = fuente[i:i + 4000]
    assert "dentro_en" in cuerpo, "el barrido no mira en qué grupos sigue dentro"
    assert "ban_chat_member" in cuerpo, "el barrido no re-aplica el ban"


def test_el_barrido_respeta_el_modo_shadow():
    fuente = Path("src/maintenance.py").read_text()
    i = fuente.index("if kicked_anywhere and dentro_en")
    assert "not cfg.shadow" in fuente[i:i + 120], "re-banearía de verdad en modo prueba"


def test_el_barrido_sigue_sin_revocar_a_ciegas():
    """La guarda que ya existía: si NINGUNA consulta respondió, no se toca nada.
    Revocar ahí borraría un ban real por un corte de red."""
    fuente = Path("src/maintenance.py").read_text()
    i = fuente.index("if not lookup_ok:")
    assert "continue" in fuente[i:i + 100]


# ------------------------- readmisión por otro admin -------------------------

def test_se_detecta_que_otro_admin_readmita_a_un_baneado():
    """El bot solo vigilaba las transiciones HACIA ban o expulsión. La contraria,
    que alguien levante el ban, no la miraba nadie: por eso el usuario del caso
    volvió a estar dentro y nadie se enteró en día y medio."""
    fuente = Path("src/handlers.py").read_text()
    assert "_readmitido" in fuente, "no se detecta la readmisión"
    i = fuente.index("_readmitido = (")
    bloque = fuente[i:i + 500]
    assert "ChatMemberStatus.BANNED" in bloque, "no parte del estado baneado"
    assert "MEMBER" in bloque and "RESTRICTED" in bloque, (
        "no cubre readmitir silenciado, que es justo lo que pasó")


def test_la_readmision_re_aplica_el_ban_y_avisa():
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("if _readmitido and db.is_banned(")
    bloque = fuente[i:i + 1200]
    assert "ban_chat_member" in bloque, "no re-aplica el ban"
    assert "_avisar_readmision" in bloque, "no avisa al admin"
    assert "not cfg.shadow" in bloque, "banearía de verdad en modo prueba"


def test_el_aviso_deja_aceptar_la_decision_del_otro_admin():
    """Sin una salida, el bot y la persona se pelearían cada vez que escriba. El
    botón permite levantar el ban de verdad si el otro admin tenía razón."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_readmision_callback")
    bloque = fuente[i:i + 1200]
    assert "revoke_ban" in bloque, "no permite levantar el ban de la lista"
    assert "unban_chat_member" in bloque, "lo quita de la lista pero lo deja expulsado"
