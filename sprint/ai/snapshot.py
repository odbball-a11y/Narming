"""Save and reload a whole stable: racers, ratings, records, seasons, the lot.

    python -m ai.snapshot save NAME [--root stable]     # -> saves/NAME.zip
    python -m ai.snapshot load NAME [--root stable]     # puts it back (the old stable is kept aside)
    python -m ai.snapshot list

A save keeps every file of the stable except that old generations of each
training run are cut down to their best four drivers (the last generation of
a run is kept whole, so training can carry on); this keeps a save small.
Loading never deletes: the stable it replaces is renamed `<root>.before-<name>`.
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
SAVES = PROJECT / "saves"
STUB_ROWS = 4


def _generation_files(root: Path) -> set[Path]:
    """Every gen_*.npz that is not the last of its run."""
    old = set()
    for run in {p.parent for p in root.rglob("gen_*.npz")}:
        files = sorted(run.glob("gen_*.npz"))
        old.update(files[:-1])
    return old


def _stub(path: Path) -> bytes:
    with np.load(path) as data:
        n = len(data["pop"])
        arrays = {k: (data[k][:STUB_ROWS] if data[k].ndim and len(data[k]) == n else data[k]) for k in data.files}
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    return buf.getvalue()


def save(name: str, root: Path | str | None = None, out_dir: Path | None = None) -> Path:
    root = Path(root) if root else PROJECT / "stable"
    if not root.exists():
        raise FileNotFoundError(f"no stable at {root}")
    out_dir = Path(out_dir) if out_dir else SAVES
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.zip"
    tmp = target.with_suffix(".tmp")
    old = _generation_files(root)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix in (".tmp", ".log") or "litter" in p.parts:
                continue
            arc = p.relative_to(root).as_posix()
            if p in old:
                zf.writestr(arc, _stub(p))
            else:
                zf.write(p, arc)
        zf.writestr("SAVE.txt", f"stable save {name!r} from {root.name}, {time.strftime('%Y-%m-%d %H:%M')}\n"
                                f"source folder: {root.relative_to(PROJECT).as_posix() if root.is_relative_to(PROJECT) else root.name}\n")
    tmp.replace(target)
    return target


def load(name: str, root: Path | str | None = None, save_dir: Path | None = None) -> Path:
    root = Path(root) if root else PROJECT / "stable"
    source = (Path(save_dir) if save_dir else SAVES) / f"{name}.zip"
    if not source.exists():
        raise FileNotFoundError(f"no save called {name!r} ({source})")
    staging = root.with_name(root.name + ".loading")
    if staging.exists():
        shutil.rmtree(staging)
    with zipfile.ZipFile(source) as zf:
        for member in zf.namelist():
            if member.startswith(("/", "..")) or ".." in Path(member).parts:
                raise ValueError(f"unsafe path in save: {member}")
        zf.extractall(staging)
    origin = ""
    note = staging / "SAVE.txt"
    if note.exists():
        for line in note.read_text(encoding="utf-8").splitlines():
            if line.startswith("source folder:"):
                origin = line.split(":", 1)[1].strip().rstrip("/")
        note.unlink()
    here = root.relative_to(PROJECT).as_posix() if root.is_relative_to(PROJECT) else root.name
    if origin and origin != here:
        for f in staging.rglob("*.json"):                      # paths stored inside refer to the old folder
            text = f.read_text(encoding="utf-8")
            if origin + "/" in text:
                f.write_text(text.replace(origin + "/", here + "/"), encoding="utf-8")
    if root.exists():
        aside = root.with_name(f"{root.name}.before-{name}")
        n = 1
        while aside.exists():
            n += 1
            aside = root.with_name(f"{root.name}.before-{name}-{n}")
        root.rename(aside)
    staging.rename(root)
    return root


def names(save_dir: Path | None = None) -> list[str]:
    d = Path(save_dir) if save_dir else SAVES
    return sorted(p.stem for p in d.glob("*.zip")) if d.exists() else []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["save", "load", "list"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--root", default=None, help="stable folder (default: stable)")
    args = ap.parse_args(argv)
    if args.action == "list":
        print("\n".join(names()) or "no saves yet")
        return 0
    if not args.name:
        ap.error("give the save a name")
    if args.action == "save":
        print("saved", save(args.name, args.root))
    else:
        print("loaded into", load(args.name, args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
