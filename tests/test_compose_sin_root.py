"""El contenedor corre sin root y con un uid que no es de nadie en el host.

10-oct-2026 (orden del user: «que todo esté bien aislado»): `cazaspam-bot` corría
como root, así que escapar del contenedor era ser root del servidor. Ahora usa el
uid 10112 del registro `/home/docs/uids-contenedores.md`.

Al hacerlo salió un fallo que ya estaba: `config/` va en solo lectura y las
palabras que se añaden desde Telegram se guardan en `config/blacklist/custom/`, así
que guardarlas fallaba siempre. Esa carpeta, y solo esa, se monta con escritura.
"""
from pathlib import Path

COMPOSE = Path("docker-compose.yml").read_text()


def test_corre_con_un_uid_propio_y_no_como_root():
    assert 'user: "${APP_UID:-10112}:${APP_GID:-10112}"' in COMPOSE


def test_el_codigo_y_la_config_son_de_solo_lectura():
    for montaje in ("./src:/app/src:ro", "./scripts:/app/scripts:ro", "./config:/app/config:ro"):
        assert montaje in COMPOSE, montaje


def test_la_lista_personalizada_se_puede_escribir():
    linea = next(lin.strip() for lin in COMPOSE.splitlines()
                 if "config/blacklist/custom" in lin and lin.strip().startswith("-"))
    assert linea == "- ./config/blacklist/custom:/app/config/blacklist/custom", linea


def test_la_guia_dice_como_dar_las_carpetas():
    """Sin este paso, una instalación nueva no puede abrir su base de datos."""
    paso = "sudo install -d -o 10112 -g 10112 data config/blacklist/custom"
    for f in ("README.md", "README.es.md", "scripts/setup.py"):
        assert paso in Path(f).read_text(), f
