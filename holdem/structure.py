"""Blind structures: starting chips, blind levels, and when the levels go up.

Levels go up only between hands, never during one. A level lasts either a
fixed number of hands or a fixed number of minutes. If play runs past the last
listed level, the blinds keep doubling from the last level, so a match always
ends. A structure with no level length is a cash game: the blinds stay fixed.
"""

from dataclasses import dataclass, field, asdict


@dataclass
class BlindStructure:
    name: str
    starting_stack: int
    levels: list = field(default_factory=list)  # [(small, big), ...]
    hands_per_level: int | None = None
    minutes_per_level: float | None = None

    def __post_init__(self):
        self.levels = [tuple(int(x) for x in lvl) for lvl in self.levels]
        if not self.levels:
            raise ValueError("a structure needs at least one blind level")
        prev_bb = 0
        for sb, bb in self.levels:
            if not 0 < sb <= bb:
                raise ValueError(f"level {sb}/{bb}: need 0 < small blind <= big blind")
            if bb < prev_bb:
                raise ValueError(f"level {sb}/{bb}: blinds should not go down")
            prev_bb = bb
        if self.hands_per_level and self.minutes_per_level:
            raise ValueError("choose hands per level or minutes per level, not both")
        if self.hands_per_level is not None and self.hands_per_level < 1:
            raise ValueError("hands per level must be at least 1")
        if self.minutes_per_level is not None and self.minutes_per_level <= 0:
            raise ValueError("minutes per level must be positive")
        if self.starting_stack < self.levels[0][1]:
            raise ValueError("starting stack must cover the first big blind")

    @property
    def increases(self) -> bool:
        return bool(self.hands_per_level or self.minutes_per_level)

    def level_for(self, hand_no: int, elapsed_seconds: float = 0.0) -> int:
        """Zero-based level index for hand number `hand_no` (1-based)."""
        if self.hands_per_level:
            return (hand_no - 1) // self.hands_per_level
        if self.minutes_per_level:
            return int(elapsed_seconds // (self.minutes_per_level * 60))
        return 0

    def blinds(self, level: int) -> tuple:
        if level < len(self.levels):
            return self.levels[level]
        sb, bb = self.levels[-1]
        factor = 2 ** (level - len(self.levels) + 1)
        return (sb * factor, bb * factor)

    def until_next(self, hand_no: int, elapsed_seconds: float = 0.0):
        """How long until the level after the one `hand_no` is played at.

        Returns ("hands", n), ("seconds", s) or None for fixed blinds.
        """
        if self.hands_per_level:
            return ("hands", self.hands_per_level - (hand_no - 1) % self.hands_per_level)
        if self.minutes_per_level:
            per = self.minutes_per_level * 60
            return ("seconds", per - elapsed_seconds % per)
        return None

    def describe(self) -> str:
        if self.hands_per_level:
            n = self.hands_per_level
            pace = f"every {n} hand{'s' if n != 1 else ''}"
        elif self.minutes_per_level:
            m = self.minutes_per_level
            pace = f"every {m:g} minute{'s' if m != 1 else ''}"
        else:
            pace = "fixed blinds"
        lines = [f"{self.name}: {self.starting_stack} chips each, levels up {pace}"]
        for i, (sb, bb) in enumerate(self.levels, 1):
            lines.append(f"  level {i:>2}: {sb}/{bb}   ({self.starting_stack / bb:g} bb deep at the start)")
        if self.increases:
            lines.append("  after that: blinds double each level")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["levels"] = [list(lvl) for lvl in self.levels]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BlindStructure":
        return cls(**d)

    @classmethod
    def fixed(cls, small_blind: int, big_blind: int, starting_stack: int) -> "BlindStructure":
        return cls("Cash", starting_stack, [(small_blind, big_blind)])


def parse_levels(text: str) -> list:
    """'10/20, 15/30, 25/50' -> [(10, 20), (15, 30), (25, 50)]"""
    levels = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            sb, bb = part.split("/")
            levels.append((int(sb), int(bb)))
        except ValueError:
            raise ValueError(f"can't read level {part!r}; write levels like 10/20,15/30") from None
    return levels


PRESETS = {
    "turbo": BlindStructure(
        "Turbo", 1500,
        [(10, 20), (20, 40), (30, 60), (50, 100), (75, 150), (100, 200),
         (150, 300), (200, 400), (300, 600), (500, 1000)],
        hands_per_level=10),
    "standard": BlindStructure(
        "Standard", 1500,
        [(10, 20), (15, 30), (20, 40), (30, 60), (40, 80), (50, 100), (75, 150),
         (100, 200), (150, 300), (200, 400), (300, 600), (400, 800), (500, 1000),
         (700, 1400), (1000, 2000)],
        hands_per_level=20),
    "deep": BlindStructure(
        "Deep", 5000,
        [(10, 20), (15, 30), (20, 40), (25, 50), (30, 60), (40, 80), (50, 100),
         (60, 120), (80, 160), (100, 200), (125, 250), (150, 300), (200, 400),
         (250, 500), (300, 600), (400, 800), (500, 1000)],
        hands_per_level=25),
    "cash": BlindStructure("Cash", 200, [(1, 2)]),
}


def preset(name: str) -> BlindStructure:
    try:
        return BlindStructure.from_dict(PRESETS[name.lower()].to_dict())
    except KeyError:
        raise ValueError(f"unknown structure {name!r}; choose from {', '.join(PRESETS)}") from None
