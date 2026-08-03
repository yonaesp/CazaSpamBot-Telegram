"""Nombre en ideogramas chinos con cuenta antigua y foto: mudo hasta que decidas.

Caso real medido (1-ago-2026): entró 凎吙爪窝 con una cuenta de más de un año y con
foto. El detector de perfil obvio NO le baneó porque existe un salvoconducto para
no expulsar a chino-hablantes reales con cuenta asentada. Pasó a la verificación
normal, **pulsó el botón a los 3 segundos** y entró. Dos días después soltó el spam
y se le baneó por el idioma del mensaje. Telegram acabó eliminando la cuenta.

La lección: pulsar un botón no demuestra nada frente a un bot. Así que en ese caso
concreto no se banea (podría ser legítimo) ni se deja pasar: se queda MUDO y decide
el admin.
"""
import datetime as dt
from types import SimpleNamespace

from src import verification as v


def _cuenta(fotos, dias):
    return SimpleNamespace(photo_count=fotos, account_age_days=dias,
                           oldest_photo=dt.datetime(2023, 1, 1),
                           newest_photo=dt.datetime(2025, 1, 1))


def test_el_caso_real_ahora_queda_a_decision_del_admin():
    """Cuenta antigua con foto: ni ban automático ni pase libre."""
    sig = _cuenta(fotos=2, dias=800)
    assert v.han_requiere_decision(sig, None, "凎吙爪窝", None) is True
    # y sigue sin banear solo, que es lo que protege al chino-hablante real
    baneado, _ = v._is_obvious_spam_profile(sig, None, "凎吙爪窝", None)
    assert baneado is False


def test_cuenta_nueva_sin_foto_se_banea_como_siempre():
    """Ese ya caía antes y tiene que seguir cayendo: no se toca."""
    sig = _cuenta(fotos=0, dias=10)
    baneado, _ = v._is_obvious_spam_profile(sig, None, "凎吙爪窝", None)
    assert baneado is True
    assert v.han_requiere_decision(sig, None, "凎吙爪窝", None) is False, (
        "no puede pedir decisión de algo que ya se ha baneado")


def test_sin_telethon_no_pide_decision():
    """Sin señales de perfil el salvoconducto no aplica, así que `_is_obvious`
    ya banea solo. Pedir decisión aquí duplicaría el camino."""
    assert v.han_requiere_decision(None, None, "凎吙爪窝", None) is False


def test_un_nombre_latino_no_dispara_nada():
    assert v.han_requiere_decision(_cuenta(2, 800), "pepe", "Pepe", "López") is False


def test_el_cirilico_no_entra_por_aqui():
    """Esta puerta es SOLO para ideogramas Han. El ruso/ucraniano tiene usuarios
    legítimos de sobra y se trata por la vía normal."""
    assert v.han_requiere_decision(_cuenta(2, 800), "ivan", "Иван", None) is False


def test_el_boton_permitir_desmutea():
    """Si «Permitir» no desmuteara, dejaría a la persona muda para siempre tras
    haberla aprobado, que es el peor resultado posible."""
    from pathlib import Path
    fuente = Path("src/admin.py").read_text()
    i = fuente.index('if action == "allowu":')
    bloque = fuente[i:i + 700]
    assert "restrict_chat_member" in bloque, "el botón Permitir no desmutea"
    assert "VERIFIED_PERMISSIONS" in bloque


def test_la_regla_tiene_explicacion():
    from src.rule_explain import KNOWN_RULES, explain
    assert "han_pending_review" in KNOWN_RULES
    assert explain("han_pending_review") != "han_pending_review"
