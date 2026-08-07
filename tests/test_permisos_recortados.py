"""Que le quiten permisos al bot sin echarlo es el fallo MÁS silencioso que tiene.

Si lo expulsan de un grupo, ya avisaba. Pero si un admin le deja dentro y le quita
«borrar mensajes», el bot sigue apareciendo en `/chats`, sigue detectando el spam...
y no puede tocarlo. No te enteras hasta que se cuela algo, y entonces parece que el
bot está roto.

Se compara el ANTES contra el DESPUÉS, no el estado nuevo a secas: lo que hay que
avisar es el cambio. Un bot que nunca fue admin en un grupo no puede generar un
aviso cada vez que alguien toca cualquier otra cosa de ese chat.
"""
from types import SimpleNamespace

import pytest

from src.handlers import permisos_perdidos


def _miembro(status, *, borrar=True, restringir=True):
    return SimpleNamespace(
        status=status,
        can_delete_messages=borrar,
        can_restrict_members=restringir,
    )


ADMIN_PLENO = _miembro("administrator")


def test_le_quitan_borrar_mensajes():
    assert permisos_perdidos(ADMIN_PLENO, _miembro("administrator", borrar=False)) == ["borrar"]


def test_le_quitan_expulsar():
    assert permisos_perdidos(ADMIN_PLENO, _miembro("administrator", restringir=False)) == ["restringir"]


def test_le_quitan_los_dos():
    perdidos = permisos_perdidos(ADMIN_PLENO, _miembro("administrator", borrar=False, restringir=False))
    assert perdidos == ["borrar", "restringir"]


def test_le_quitan_el_admin_entero():
    """Un solo aviso que lo engloba: detallar qué permiso concreto ha perdido
    quien ya no es administrador no aporta nada."""
    assert permisos_perdidos(ADMIN_PLENO, _miembro("member", borrar=False, restringir=False)) == ["admin"]


@pytest.mark.parametrize("antes,despues", [
    # Nada ha cambiado.
    (ADMIN_PLENO, ADMIN_PLENO),
    # Le ASCIENDEN: no ha perdido nada.
    (_miembro("member", borrar=False, restringir=False), ADMIN_PLENO),
    # Nunca fue admin y sigue sin serlo: no hay nada que avisar, y sin esta guarda
    # llegaría un aviso cada vez que alguien tocara algo del chat.
    (_miembro("member", borrar=False, restringir=False),
     _miembro("member", borrar=False, restringir=False)),
    # Acaba de entrar: no había un «antes» del que perder nada.
    (None, ADMIN_PLENO),
    (_miembro("left", borrar=False, restringir=False), ADMIN_PLENO),
])
def test_no_avisa_cuando_no_toca(antes, despues):
    assert permisos_perdidos(antes, despues) == []


def test_si_le_echan_no_lo_cuenta_como_recorte():
    """De que le expulsen ya avisa el otro aviso; dos avisos por lo mismo es ruido."""
    assert permisos_perdidos(ADMIN_PLENO, _miembro("left", borrar=False, restringir=False)) == []
    assert permisos_perdidos(ADMIN_PLENO, _miembro("kicked", borrar=False, restringir=False)) == []


def test_el_dueno_del_grupo_no_pierde_nada():
    """`creator` no lleva los flags de permisos y sin tratarlo aparte parecería
    que los ha perdido todos."""
    assert permisos_perdidos(_miembro("creator", borrar=False, restringir=False),
                             _miembro("creator", borrar=False, restringir=False)) == []
