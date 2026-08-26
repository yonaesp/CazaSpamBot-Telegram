"""`/scan` mira también a QUIEN escribió, no solo el texto.

Lo pidió el admin: el informe cubría el contenido y avisaba en una nota de que
«no cubre reglas por perfil/listas (CAS, lols, obvious_profile) que dependen de
quién lo envía». La nota era honesta pero dejaba el trabajo a medias: el mismo
texto («Buenos día guapa») es inocuo de un vecino y sospechoso de una cuenta
recién hecha con un canal de spam en el perfil.

Ahora el informe acaba con una línea de usuario: ✅ si no hay nada, o el detalle
de lo que se ha encontrado.
"""
from types import SimpleNamespace as NS

import pytest

from src import scan_cmd


def _autor(uid=1, nombre="Ana", username=None, es_bot=False):
    return NS(id=uid, first_name=nombre, last_name=None, username=username, is_bot=es_bot)


def _msg(autor=None, forward=None):
    return NS(from_user=autor, forward_origin=forward, chat=NS(id=-100), chat_id=-100)


# ------------------------------------------------- de quién se analiza el perfil

def test_en_un_mensaje_del_grupo_el_autor_es_quien_escribio():
    u = _autor()
    assert scan_cmd._autor_de(_msg(autor=u))[0] is u


def test_en_un_reenvio_se_usa_el_autor_ORIGINAL():
    """Si no, se analizaría al admin que reenvía en vez de al sospechoso."""
    original = _autor(uid=99, nombre="Sospechoso")
    reenviado = _msg(autor=_autor(uid=1, nombre="Admin"),
                     forward=NS(sender_user=original))
    assert scan_cmd._autor_de(reenviado)[0] is original


def test_si_el_reenvio_oculta_la_cuenta_se_dice():
    """Telegram solo da el autor original si esa persona no lo oculta. Inventarse
    un veredicto sobre el remitente equivocado sería peor que no dar ninguno."""
    oculto = _msg(autor=_autor(uid=1, nombre="Admin"),
                  forward=NS(sender_user=None, sender_user_name="Alguien"))
    autor, motivo = scan_cmd._autor_de(oculto)
    assert autor is None and motivo


def test_un_mensaje_sin_autor_no_revienta():
    autor, motivo = scan_cmd._autor_de(_msg(autor=None))
    assert autor is None and motivo


# ------------------------------------------------------------- el veredicto

def _ctx(db, http=None, reporter=None):
    return NS(bot_data={"db": db, "http": http, "reporter": reporter})


def _cfg(**extra):
    base = dict(lols_enabled=False, cas_enabled=False, cas_cache_ttl_seconds=3600,
                allowed_scripts=["latin"], non_latin_ratio_threshold=0.5)
    base.update(extra)
    return NS(**base)


class _DB:
    def __init__(self, baneado=False):
        self.baneado = baneado

    def is_banned(self, uid):
        return self.baneado

    def get_chat_settings(self, cid):
        return None


@pytest.mark.asyncio
async def test_usuario_limpio_sale_con_la_v_verde():
    lineas = await scan_cmd._revisar_autor(_ctx(_DB()), _cfg(), _DB(), _msg(_autor()))
    texto = "\n".join(lineas)
    assert "✅" in texto and "Ana" in texto


@pytest.mark.asyncio
async def test_sin_telethon_no_se_firma_en_verde_lo_no_comprobado():
    """No se puede decir «sin hallazgos en perfil» si el perfil no se ha leído."""
    lineas = await scan_cmd._revisar_autor(_ctx(_DB()), _cfg(), _DB(), _msg(_autor()))
    assert "sin comprobar" in "\n".join(lineas)


@pytest.mark.asyncio
async def test_un_baneado_en_federacion_se_dice():
    db = _DB(baneado=True)
    lineas = await scan_cmd._revisar_autor(_ctx(db), _cfg(), db, _msg(_autor()))
    texto = "\n".join(lineas)
    assert "⚠️" in texto and "baneado" in texto


@pytest.mark.asyncio
async def test_un_nombre_de_spam_evidente_se_detalla():
    """Mismos criterios que el join, sin umbrales propios."""
    chino = _autor(uid=7, nombre="李大哥")
    lineas = await scan_cmd._revisar_autor(_ctx(_DB()), _cfg(), _DB(), _msg(chino))
    assert "⚠️" in "\n".join(lineas)


@pytest.mark.asyncio
async def test_a_un_bot_no_se_le_aplican_los_criterios_de_perfil():
    lineas = await scan_cmd._revisar_autor(
        _ctx(_DB()), _cfg(), _DB(), _msg(_autor(es_bot=True)))
    assert "bot" in "\n".join(lineas).lower()


@pytest.mark.asyncio
async def test_las_listas_externas_se_consultan_si_estan_activas(monkeypatch):
    async def falso_lols(uid, session):
        return object()
    monkeypatch.setattr(scan_cmd.lols_det, "check", falso_lols)
    lineas = await scan_cmd._revisar_autor(
        _ctx(_DB(), http=object()), _cfg(lols_enabled=True), _DB(), _msg(_autor()))
    assert "lols" in "\n".join(lineas)


@pytest.mark.asyncio
async def test_un_fallo_de_red_no_deja_el_informe_sin_veredicto(monkeypatch):
    async def revienta(uid, session):
        raise RuntimeError("sin red")
    monkeypatch.setattr(scan_cmd.lols_det, "check", revienta)
    lineas = await scan_cmd._revisar_autor(
        _ctx(_DB(), http=object()), _cfg(lols_enabled=True), _DB(), _msg(_autor()))
    assert lineas, "el bloque de usuario tiene que salir igualmente"


# ----------------------------------------------------------------- el enganche

def test_el_informe_incluye_al_autor_y_ya_no_se_excusa():
    """La nota de «no cubre reglas por perfil» sobra si ahora sí las cubre."""
    from pathlib import Path
    fuente = Path("src/scan_cmd.py").read_text()
    i = fuente.index("async def _responder_scan(")
    cuerpo = fuente[i:]
    assert "_revisar_autor(" in cuerpo
    assert 'scan.profile_note' not in cuerpo, "la excusa vieja sigue puesta"


def test_un_fallo_analizando_al_autor_no_impide_enviar_el_informe():
    from pathlib import Path
    fuente = Path("src/scan_cmd.py").read_text()
    i = fuente.index("autor_lineas = await _revisar_autor(")
    assert "except Exception" in fuente[i:i + 400]
