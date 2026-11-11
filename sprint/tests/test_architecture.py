"""sim/ must be usable with no pygame at all."""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "sim"
FORBIDDEN = {"pygame", "game", "time", "datetime"}


def test_sim_sources_do_not_import_pygame_or_clocks():
    files = sorted(SIM.glob("**/*.py"))
    assert files, "sim package not found"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN, f"{path.name} imports {name}"


def test_importing_and_running_sim_never_loads_pygame():
    code = (
        "import sys, pkgutil, importlib, sim\n"
        "for m in pkgutil.walk_packages(sim.__path__, 'sim.'):\n"
        "    importlib.import_module(m.name)\n"
        "from sim.world import World; from sim.track import Track\n"
        "from sim.driver import create_driver\n"
        "w = World(Track.load('speedway'), 2); d = create_driver('scripted')\n"
        "for _ in range(300): w.step([d.act(w, 0), d.act(w, 1)])\n"
        "assert 'pygame' not in sys.modules, 'pygame was imported'\n"
        "print('ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_unseeded_random_is_not_used_in_sim():
    for path in SIM.glob("**/*.py"):
        text = path.read_text(encoding="utf-8")
        for bad in ("random.random(", "random.uniform(", "random.choice(", "np.random.rand"):
            assert bad not in text, f"{path.name} uses module-level randomness: {bad}"
