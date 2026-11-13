"""Upgrade saved brains to the current input layout, once.

When new inputs are added to the drivers (see brain.INPUT_VERSIONS), every
saved brain is rewired with zero-strength connections for the new inputs, so
it drives exactly as before and further training can learn to use them.

Runs automatically when the game, train.py, compare.py or the stable trainer
starts.  It only touches files whose layout is older than the current one.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .brain import INPUT_VERSION, input_version, upgrade
from .evolve import PROJECT


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def _upgrade_npz(path: Path, arch: dict) -> bool:
    with np.load(path) as data:
        arrays = {k: data[k] for k in data.files}
    pop = arrays["pop"]
    from .brain import n_weights
    if pop.shape[-1] != n_weights(arch):
        return False                      # already upgraded (or not this layout)
    new, _ = upgrade(pop.astype(np.float64), arch)
    arrays["pop"] = new.astype(np.float32)
    np.savez_compressed(path, **arrays)
    return True


def _upgrade_run(run_dir: Path) -> int:
    """A training run: its config's arch and every generation file."""
    config_path = run_dir / "config.json"
    config = _read(config_path)
    arch = config.get("arch")
    if not arch or input_version(arch) == INPUT_VERSION:
        return 0
    count = sum(_upgrade_npz(p, arch) for p in sorted(run_dir.glob("gen_*.npz")))
    config["arch"] = dict(arch, inputs=INPUT_VERSION)
    config["inputs"] = len(__import__("ai.brain", fromlist=["INPUT_NAMES"]).INPUT_NAMES)
    _write(config_path, config)
    return count + 1


def _upgrade_card(card_path: Path, npz_path: Path) -> int:
    card = _read(card_path)
    arch = card.get("arch")
    if not arch or input_version(arch) == INPUT_VERSION:
        return 0
    if npz_path.exists():
        _upgrade_npz(npz_path, arch)
    card["arch"] = dict(arch, inputs=INPUT_VERSION)
    _write(card_path, card)
    return 1


def ensure(project: Path = PROJECT) -> int:
    """Upgrade everything that needs it.  Returns the number of files changed."""
    project = Path(project)
    changed = 0
    house = project / "house"
    grad_card = house / "graduate.json"
    old_grad_arch = _read(grad_card).get("arch") if grad_card.exists() else None
    if grad_card.exists():
        changed += _upgrade_card(grad_card, house / "graduate.npz")
    for card in sorted((house / "rivals").glob("*.json")) if (house / "rivals").exists() else []:
        changed += _upgrade_card(card, card.with_suffix(".npz"))
    for root in ("training", "stable", "workshop", "dynasty"):
        base = project / root
        if not base.exists():
            continue
        for config in sorted(base.glob("**/config.json")):
            if "litter" in config.parts:
                continue
            changed += _upgrade_run(config.parent)
        # Bred foals keep the brain they were picked as.
        if old_grad_arch and input_version(old_grad_arch) != INPUT_VERSION:
            for foal in sorted(base.glob("*/foal.npz")):
                changed += _upgrade_npz(foal, old_grad_arch)
    return changed


if __name__ == "__main__":
    print(f"upgraded {ensure()} file(s)")
