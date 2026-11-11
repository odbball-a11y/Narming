"""Record a race's per-tick controls and play them back exactly.

A recording is: which track, which slots, how many laps, the seed, and the
Controls applied to every car on every racing tick.  Because the sim is
deterministic, feeding those controls back reproduces the race bit for bit;
the stored state hash lets playback prove it.

A recording only replays exactly with the physics values and track file it
was made with; both are fingerprinted so a mismatch can be reported.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from . import tuning
from .driver import Controls, Driver, NO_INPUT
from .race import Race
from .track import Track

FORMAT = 1


def track_fingerprint(track: Track) -> str:
    data = (track.control_points.tolist(), track.verge, len(track.checkpoints),
            track.racing_offset.tolist())
    return hashlib.sha256(repr(data).encode()).hexdigest()[:16]


class Recording:
    def __init__(self, track: str, slots, laps: int, seed: int, controls,
                 drivers=None, final_hash=None, results=None,
                 tuning_id=None, track_id=None, tick_rate=tuning.TICK_RATE):
        self.track = track
        self.slots = list(slots)
        self.laps = laps
        self.seed = seed
        self.controls = [tuple(row) for row in controls]   # per tick: s,t,b per car
        self.drivers = list(drivers or [])
        self.final_hash = final_hash
        self.results = results or []
        self.tuning_id = tuning_id
        self.track_id = track_id
        self.tick_rate = tick_rate

    @classmethod
    def from_race(cls, race: Race) -> "Recording":
        return cls(
            track=race.track.key, slots=race.slots, laps=race.laps, seed=race.seed,
            controls=race.controls_log, drivers=[d.label for d in race.drivers],
            final_hash=race.final_hash, results=race.results(),
            tuning_id=tuning.physics_fingerprint(), track_id=track_fingerprint(race.track),
        )

    # ----------------------------------------------------------------- I/O

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "format": FORMAT, "track": self.track, "slots": self.slots, "laps": self.laps,
            "seed": self.seed, "tick_rate": self.tick_rate, "drivers": self.drivers,
            "tuning_id": self.tuning_id, "track_id": self.track_id,
            "final_hash": self.final_hash, "results": self.results,
            "controls": self.controls,
        }
        raw = json.dumps(data, separators=(",", ":")).encode()
        # No name and mtime=0 keep the file bytes identical for identical races.
        with open(path, "wb") as fh:
            with gzip.GzipFile(filename="", fileobj=fh, mode="wb", mtime=0) as gz:
                gz.write(raw)
        return path

    @classmethod
    def load(cls, path) -> "Recording":
        with gzip.open(path, "rb") as fh:
            data = json.loads(fh.read().decode())
        if data.get("format") != FORMAT:
            raise ValueError(f"unsupported replay format {data.get('format')!r}")
        return cls(
            track=data["track"], slots=data["slots"], laps=data["laps"], seed=data["seed"],
            controls=data["controls"], drivers=data.get("drivers"),
            final_hash=data.get("final_hash"), results=data.get("results"),
            tuning_id=data.get("tuning_id"), track_id=data.get("track_id"),
            tick_rate=data.get("tick_rate", tuning.TICK_RATE),
        )

    # ------------------------------------------------------------ playback

    def make_race(self) -> Race:
        """A Race whose drivers replay this recording."""
        entries = []
        for i, slot in enumerate(self.slots):
            label = self.drivers[i] if i < len(self.drivers) else "Replay"
            entries.append((slot, ReplayDriver(self, i, label)))
        return Race(self.track, entries, laps=self.laps, seed=self.seed)

    def compatibility_problems(self, track: Track | None = None) -> list[str]:
        """Reasons this recording may not replay exactly (empty = none)."""
        problems = []
        if self.tick_rate != tuning.TICK_RATE:
            problems.append("tick rate differs")
        if self.tuning_id and self.tuning_id != tuning.physics_fingerprint():
            problems.append("physics tuning has changed")
        track = track or Track.load(self.track)
        if self.track_id and self.track_id != track_fingerprint(track):
            problems.append("track file has changed")
        return problems

    def verify(self) -> bool:
        """Replay headless and compare the final state hash."""
        race = self.make_race().run()
        return self.final_hash is not None and race.final_hash == self.final_hash


class ReplayDriver(Driver):
    """Feeds back the recorded controls for one car, tick by tick."""

    def __init__(self, recording: Recording, car_index: int, label: str = "Replay"):
        self.recording = recording
        self.car_index = car_index
        self.label = label

    def act(self, world, car_index: int) -> Controls:
        log = self.recording.controls
        if world.tick >= len(log):
            return NO_INPUT
        row = log[world.tick]
        k = self.car_index * 3
        return Controls(row[k], row[k + 1], row[k + 2])
