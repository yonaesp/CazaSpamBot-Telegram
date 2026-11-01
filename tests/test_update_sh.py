"""`update.sh`: instala la última versión y, si el bot no arranca, vuelve a la anterior (L51).

Se ensaya contra un repo «origin» de mentira y un compose falso: el de verdad
recrearía el contenedor de producción (`container_name` es fijo). El compose falso
hace de bot: al arrancar toca `data/heartbeat`, salvo en una versión marcada como
rota (`BROKEN`, versionado) o si todo está roto (`ALWAYS_BROKEN`, sin versionar).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "update.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("flock") is None,
                                reason="hace falta git y flock")

FAKE_COMPOSE = r"""#!/bin/bash
echo "$*" >> "$FAKE_LOG"
case "$1" in
  up)
    [ -f ALWAYS_BROKEN ] && exit 0
    if [ -n "$FAKE_STATE" ]; then
      cp "$FAKE_STATE/tagged" "$FAKE_STATE/running"
      [ "$(cat "$FAKE_STATE/running")" = broken ] && exit 0
    elif [ -f BROKEN ]; then
      exit 0
    fi
    (sleep 1; touch data/heartbeat) >/dev/null 2>&1 &
    ;;
  exec) echo preupdate-test.db ;;
  ps) echo cid123 ;;
  pull) cp "$FAKE_STATE/remote" "$FAKE_STATE/tagged" ;;
esac
exit 0
"""

# Motor de contenedores falso para el modo imagen: el estado vive en ficheros.
FAKE_ENGINE = r"""#!/bin/bash
echo "engine $*" >> "$FAKE_LOG"
case "$1 $2" in
  "inspect -f")
    case "$3" in
      *Config.Image*) echo ghcr.io/example/cazaspambot:1 ;;
      *) cat "$FAKE_STATE/running" ;;
    esac ;;
  "image inspect")
    case "$4" in
      *Labels*) cat "$FAKE_STATE/label-$5" 2>/dev/null ;;
      *) cat "$FAKE_STATE/tagged" ;;
    esac ;;
  "tag "*) echo "$2" > "$FAKE_STATE/tagged" ;;
esac
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def _ejecutable(ruta: Path, texto: str) -> Path:
    ruta.write_text(texto)
    ruta.chmod(0o755)
    return ruta


class Banco:
    """Un origin con ramas stable y main, una copia instalada y el compose falso."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.log = tmp / "compose.log"
        self.origin = tmp / "origin.git"
        self.seed = tmp / "seed"
        self.work = tmp / "work"
        _git(tmp, "init", "-q", "--bare", "-b", "stable", str(self.origin))
        self.seed.mkdir()
        _git(self.seed, "init", "-q", "-b", "stable")
        _git(self.seed, "config", "user.email", "t@t")
        _git(self.seed, "config", "user.name", "t")
        (self.seed / "src").mkdir()
        (self.seed / "docker-compose.yml").write_text("services: {}\n")
        (self.seed / ".gitignore").write_text("data/\n.update-failed\n.update.lock\n.env\n")
        shutil.copy(SCRIPT, self.seed / "update.sh")
        self.publicar("1.0.0")
        _git(self.seed, "remote", "add", "origin", str(self.origin))
        _git(self.seed, "push", "-q", "origin", "stable", "stable:main")
        _git(tmp, "clone", "-q", "-b", "stable", str(self.origin), str(self.work))
        (self.work / "data").mkdir()
        self.compose = _ejecutable(tmp / "fakecompose", FAKE_COMPOSE)

    def publicar(self, version: str, rota: bool = False, empujar: bool = False) -> str:
        (self.seed / "src" / "version.py").write_text(f'__version__ = "{version}"\n')
        rotura = self.seed / "BROKEN"
        if rota:
            rotura.write_text("x")
        elif rotura.exists():
            rotura.unlink()
        _git(self.seed, "add", "-A")
        _git(self.seed, "commit", "-q", "-m", f"v{version}")
        if empujar:
            _git(self.seed, "push", "-q", "origin", "stable")
        return _git(self.seed, "rev-parse", "HEAD")

    def correr(self, *args: str, env: dict | None = None, cwd: Path | None = None):
        entorno = {**os.environ, "COMPOSE": str(self.compose), "FAKE_LOG": str(self.log),
                   "HEALTH_MIN_UP": "0", "HEALTH_POLL": "0.2", "HEALTH_TIMEOUT": "3",
                   "LANG": "C", "LC_ALL": "", "LC_MESSAGES": ""}
        entorno.update(env or {})
        destino = cwd or self.work
        return subprocess.run([str(destino / "update.sh"), *args], cwd=destino, env=entorno,
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)

    def head(self) -> str:
        return _git(self.work, "rev-parse", "HEAD")

    def llamadas(self) -> str:
        return self.log.read_text() if self.log.exists() else ""


@pytest.fixture
def banco(tmp_path) -> Banco:
    return Banco(tmp_path)


def test_ya_al_dia_no_reinicia_nada(banco):
    r = banco.correr("--yes")
    assert r.returncode == 0, r.stderr
    assert "Already up to date (v1.0.0, branch stable)" in r.stdout
    assert "up " not in banco.llamadas()


def test_check_dice_que_hay_version_y_no_toca_nada(banco):
    antes = banco.head()
    banco.publicar("1.1.0", empujar=True)
    r = banco.correr("--check")
    assert r.returncode == 10
    assert "v1.0.0 → v1.1.0" in r.stdout
    assert banco.head() == antes and "up " not in banco.llamadas()


def test_actualiza_copia_la_base_y_espera_al_latido(banco):
    nueva = banco.publicar("1.1.0", empujar=True)
    r = banco.correr("--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert banco.head() == nueva
    llamadas = banco.llamadas()
    # La copia y la nota para el bot, antes de reiniciar; el reinicio, forzado.
    assert llamadas.index("exec -T antispam-bot python -c") < llamadas.index(
        "up -d --build --force-recreate antispam-bot")
    assert "v1.0.0 v1.1.0" in llamadas  # de dónde viene y adónde va
    assert "Done: running v1.1.0" in r.stdout
    assert not (banco.work / ".update-failed").exists()


def test_sin_terminal_y_sin_yes_no_instala(banco):
    antes = banco.head()
    banco.publicar("1.1.0", empujar=True)
    r = banco.correr()
    assert r.returncode == 1 and "use --yes" in r.stderr
    assert banco.head() == antes


def test_si_no_arranca_vuelve_a_la_anterior_y_no_la_repite_de_noche(banco):
    antes = banco.head()
    rota = banco.publicar("1.1.0", rota=True, empujar=True)
    r = banco.correr("--yes")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "going back to v1.0.0" in r.stdout
    assert banco.head() == antes
    assert not (banco.work / "BROKEN").exists()
    assert (banco.work / ".update-failed").read_text().strip() == rota
    assert banco.llamadas().count("up -d --build --force-recreate") == 2
    # La automática no vuelve a intentar la misma versión...
    r = banco.correr("--unattended")
    assert r.returncode == 0 and "already failed" in r.stdout
    assert banco.llamadas().count("up -d") == 2
    # ...pero sí la siguiente, y al salir bien olvida el fallo.
    arreglada = banco.publicar("1.1.1", empujar=True)
    r = banco.correr("--unattended")
    assert r.returncode == 0, r.stdout + r.stderr
    assert banco.head() == arreglada
    assert not (banco.work / ".update-failed").exists()


def test_la_automatica_no_salta_de_version_mayor(banco):
    antes = banco.head()
    mayor = banco.publicar("2.0.0", empujar=True)
    r = banco.correr("--unattended")
    assert r.returncode == 0 and "major version" in r.stdout
    assert banco.head() == antes
    assert banco.correr("--yes").returncode == 0
    assert banco.head() == mayor


def test_no_pisa_cambios_en_ficheros_del_bot(banco):
    banco.publicar("1.1.0", empujar=True)
    (banco.work / "docker-compose.yml").write_text("editado a mano\n")
    antes = banco.head()
    r = banco.correr("--yes")
    assert r.returncode == 1 and "git stash" in r.stderr
    assert banco.head() == antes
    assert (banco.work / "docker-compose.yml").read_text() == "editado a mano\n"


def test_una_copia_por_delante_o_con_commits_propios(banco):
    _git(banco.work, "config", "user.email", "t@t")
    _git(banco.work, "config", "user.name", "t")
    (banco.work / "mio.txt").write_text("x")
    _git(banco.work, "add", "mio.txt")
    _git(banco.work, "commit", "-q", "-m", "mío")
    r = banco.correr("--yes")
    assert r.returncode == 0 and "Already up to date" in r.stdout
    banco.publicar("1.1.0", empujar=True)
    r = banco.correr("--yes")
    assert r.returncode == 1 and "update it by hand" in r.stderr


def test_si_tampoco_arranca_la_anterior_avisa_sin_poner_el_token_en_la_linea(banco, tmp_path):
    banco.publicar("1.1.0", empujar=True)
    (banco.work / "ALWAYS_BROKEN").write_text("x")
    (banco.work / ".env").write_text("TELEGRAM_BOT_TOKEN=123:SECRETO\nADMIN_USER_ID=42\n")
    binarios = tmp_path / "bin"
    binarios.mkdir()
    _ejecutable(binarios / "curl", '#!/bin/bash\necho "$*" > "$CURL_ARGS"\ncat > "$CURL_STDIN"\n')
    args, stdin = tmp_path / "args", tmp_path / "stdin"
    r = banco.correr("--yes", env={"PATH": f"{binarios}:{os.environ['PATH']}",
                                   "CURL_ARGS": str(args), "CURL_STDIN": str(stdin)})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "SECRETO" not in args.read_text()
    assert "chat_id=42" in args.read_text() and "the bot is down" in args.read_text().lower()
    assert "SECRETO" in stdin.read_text()


def test_auto_solo_sigue_las_versiones_estables(banco, tmp_path):
    _git(banco.work, "checkout", "-q", "-b", "main", "origin/main")
    r = banco.correr("--auto")
    assert r.returncode == 1 and "git checkout stable" in r.stderr
    _git(banco.work, "checkout", "-q", "stable")
    unidades = tmp_path / "units"
    unidades.mkdir()
    entorno = {"UNIT_DIR": str(unidades), "SYSTEMCTL": "true"}
    r = banco.correr("--auto", env=entorno)
    assert r.returncode == 0, r.stderr
    servicio = (unidades / "cazaspambot-update.service").read_text()
    assert f"ExecStart={banco.work}/update.sh --unattended" in servicio
    assert "RandomizedDelaySec" in (unidades / "cazaspambot-update.timer").read_text()
    r = banco.correr("--no-auto", env=entorno)
    assert r.returncode == 0 and not list(unidades.iterdir())


# ------------------------------------------------------------------ modo imagen

@pytest.fixture
def imagen(tmp_path):
    """Una carpeta sin git, como la de quien usa la imagen publicada."""
    carpeta, estado = tmp_path / "bot", tmp_path / "state"
    carpeta.mkdir()
    estado.mkdir()
    shutil.copy(SCRIPT, carpeta / "update.sh")
    (carpeta / "docker-compose.yml").write_text("services: {}\n")
    (carpeta / "data").mkdir()
    for nombre, valor in (("running", "sha-old"), ("tagged", "sha-old"), ("remote", "sha-new"),
                          ("label-sha-old", "1.0.0"), ("label-sha-new", "1.1.0")):
        (estado / nombre).write_text(valor + "\n")
    return carpeta, estado


def _correr_imagen(banco: Banco, carpeta: Path, estado: Path, *args: str):
    motor = _ejecutable(banco.tmp / "fakeengine", FAKE_ENGINE)
    return banco.correr(*args, cwd=carpeta, env={"ENGINE": str(motor), "FAKE_STATE": str(estado)})


def test_imagen_actualiza(banco, imagen):
    carpeta, estado = imagen
    r = _correr_imagen(banco, carpeta, estado, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "v1.0.0 → v1.1.0" in r.stdout
    assert (estado / "running").read_text().strip() == "sha-new"
    assert "up -d --force-recreate antispam-bot" in banco.llamadas()
    r = _correr_imagen(banco, carpeta, estado, "--yes")
    assert "Already up to date (v1.1.0)" in r.stdout


def test_imagen_rota_vuelve_a_la_anterior(banco, imagen):
    carpeta, estado = imagen
    (estado / "remote").write_text("broken\n")
    r = _correr_imagen(banco, carpeta, estado, "--yes")
    assert r.returncode == 2, r.stdout + r.stderr
    assert (estado / "running").read_text().strip() == "sha-old"
    assert "engine tag sha-old ghcr.io/example/cazaspambot:1" in banco.llamadas()
