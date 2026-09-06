"""Señales de pura FORMA no bastan para castigar cuando el texto está limpio.

Caso real que lo destapó (7-sep-2026, Windows 11): «Kleo» (8409186137) entró, se
verificó en 10 segundos y reenvió un mensaje SUYO con la captura de una compra y
165 caracteres preguntando si la licencia que acababa de comprar era retail.
Saltaron `forward_first_msg` (80, origen `user` = él mismo) y `first_msg_media`
(70, con `is_suspicious: false` en su propio payload) = **150 exactos**, que es a
la vez el umbral de ban y el de reporte: acabó **baneado en los cuatro grupos por
federación y reportado dos veces a Telegram**, sin que una sola regla de contenido
hubiera disparado. Una pregunta sobre licencias de Windows, en un grupo de Windows.

Medido sobre los 15 casos del histórico de `moderation_log`: todos los bans
acertados llevaban además una señal de contenido (`commercial_ad`,
`non_allowed_script`, `external_mention_or_link`, `inline_buttons_from_user`) o un
perfil marcado sospechoso. El de Kleo es el único sin ninguna de las dos, así que
este perdón no habría cambiado ni uno de los aciertos.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from src import handlers
from src.detectors import Hit

FUENTE = Path("src/handlers.py").read_text(encoding="utf-8")


def _hit(rule: str, score: int, **payload) -> Hit:
    return Hit(rule=rule, score=score, reason=rule, payload=payload or None)


# El caption real de Kleo, tal cual quedó en `seen_users.last_msg_text`.
TEXTO_KLEO = (
    "intente comprar una licencia retail directamente de la tienda de windows "
    "pero me tiene confundido y quiero sabes si es retail o no los es para "
    "solicitar un reembolso"
)


def _perdon(real, texto=TEXTO_KLEO, con_foto=True, hits_imagen=(), monkeypatch=None):
    msg = SimpleNamespace(photo=[object()] if con_foto else None, document=None)
    msg_txt = SimpleNamespace(text=None, caption=texto)
    if monkeypatch is not None:
        async def _falso(*a, **kw):
            return list(hits_imagen)
        monkeypatch.setattr(handlers, "_hits_de_la_imagen", _falso)
    return asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, SimpleNamespace(), msg, msg_txt, SimpleNamespace(id=1), real))


def test_el_caso_de_kleo_no_se_castiga(monkeypatch):
    real = [_hit("forward_first_msg", 80, origin_type="user", origin_name="kakermalicioso"),
            _hit("first_msg_media", 70, is_suspicious=False, caption_len=165)]
    assert _perdon(real, monkeypatch=monkeypatch)


def test_una_sola_senal_de_contenido_cancela_el_perdon(monkeypatch):
    """Basta con que alguien haya mirado lo que el mensaje DICE."""
    real = [_hit("forward_first_msg", 80, origin_type="user"),
            _hit("first_msg_media", 70),
            _hit("commercial_ad", 100)]
    assert _perdon(real, monkeypatch=monkeypatch) == ""


def test_el_forward_desde_un_canal_no_se_perdona(monkeypatch):
    """El patrón fuerte y el único que ha acertado (7 de 7 en el histórico).

    El caption lo escribe el spammer y le sale gratis, así que un texto limpio no
    puede comprar el perdón aquí.
    """
    real = [_hit("forward_first_msg", 100, origin_type="channel", origin_name="miesbonosecu2026"),
            _hit("first_msg_media", 70)]
    assert _perdon(real, monkeypatch=monkeypatch) == ""


def test_el_forward_desde_un_bot_tampoco(monkeypatch):
    real = [_hit("forward_first_msg", 95, origin_type="bot")]
    assert _perdon(real, monkeypatch=monkeypatch) == ""


def test_sin_texto_propio_no_hay_nada_que_perdonar(monkeypatch):
    """Foto con caption corto o vacío: el patrón de spam descrito, intacto."""
    real = [_hit("first_msg_media", 90)]
    assert _perdon(real, texto="", monkeypatch=monkeypatch) == ""
    assert _perdon(real, texto="mira esto 👇", monkeypatch=monkeypatch) == ""


def test_el_cartel_de_spam_con_caption_inocente_no_se_perdona(monkeypatch):
    """El hueco que cierra el OCR: texto propio limpio y publicidad DENTRO."""
    real = [_hit("first_msg_media", 70), _hit("forward_first_msg", 80, origin_type="user")]
    assert _perdon(real, hits_imagen=[_hit("commercial_ad", 120)],
                   monkeypatch=monkeypatch) == ""


def test_si_la_imagen_no_se_puede_leer_no_se_perdona(monkeypatch):
    """Ante la duda se mantiene lo que decidieron las reglas."""
    async def _revienta(*a, **kw):
        raise RuntimeError("Telegram no da el fichero")
    monkeypatch.setattr(handlers, "_hits_de_la_imagen", _revienta)
    real = [_hit("first_msg_media", 70), _hit("forward_first_msg", 80, origin_type="user")]
    msg = SimpleNamespace(photo=[object()], document=None)
    msg_txt = SimpleNamespace(text=None, caption=TEXTO_KLEO)
    assert asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, SimpleNamespace(), msg, msg_txt, SimpleNamespace(id=1), real)) == ""


def test_un_mensaje_sin_imagen_no_paga_el_ocr():
    """Solo se lee la imagen cuando puede cambiar el veredicto."""
    def _no_debe_llamarse(*a, **kw):
        raise AssertionError("se ha leído una imagen que no existe")
    real = [_hit("forward_first_msg", 80, origin_type="user")]
    msg = SimpleNamespace(photo=None, document=None)
    msg_txt = SimpleNamespace(text=TEXTO_KLEO, caption=None)
    guardado = handlers._hits_de_la_imagen
    handlers._hits_de_la_imagen = _no_debe_llamarse
    try:
        assert asyncio.run(handlers._perdon_por_contenido_limpio(
            None, None, SimpleNamespace(), msg, msg_txt, SimpleNamespace(id=1), real))
    finally:
        handlers._hits_de_la_imagen = guardado


def test_umbrales_de_texto_propio():
    def _t(txt):
        return handlers._texto_propio_sustantivo(SimpleNamespace(text=txt, caption=None))
    assert _t(TEXTO_KLEO)
    assert _t("hola") == ""
    assert _t("compra ya barato mira 👇") == ""          # 6 palabras pero < 40 chars
    assert _t("a" * 80) == ""                            # largo pero una sola palabra


def test_las_reglas_de_forma_no_incluyen_ninguna_de_contenido():
    """Invariante: si una regla que MIRA el contenido entra en la lista, este
    perdón dejaría de exigir evidencia y empezaría a tapar spam real."""
    de_contenido = {
        "commercial_ad", "investment_scam", "url_blocklist", "non_allowed_script",
        "external_mention_or_link", "learned_similarity", "obvious_spam_profile",
        "bio_spam", "personal_channel_spam", "cas_match", "lols_match",
        "federation_known_ban", "inline_buttons_from_user",
    }
    assert not (handlers._REGLAS_DE_FORMA & de_contenido)


def test_el_perdon_se_evalua_ANTES_de_preguntarle_al_modelo():
    """Es determinista y no necesita clave de API: si perdona, no se consulta.

    Se compara por número de línea con `ast` y no buscando texto en el fuente: un
    `index()` casa con comentarios y docstrings (pasó tres veces en este repo).
    """
    arbol = ast.parse(FUENTE)
    perdon = [n.lineno for n in ast.walk(arbol)
              if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_perdon_por_contenido_limpio"]
    veto = [n.lineno for n in ast.walk(arbol)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "veta"]
    assert perdon and veto, (perdon, veto)
    assert min(perdon) < min(veto)
