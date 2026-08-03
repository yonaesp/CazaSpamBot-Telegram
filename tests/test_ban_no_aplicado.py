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
