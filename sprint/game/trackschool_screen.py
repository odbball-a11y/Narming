"""Track school: watch a car learn a track.

Pick a driver and a track; a practice copy of the driver then trains for pure
speed on that track in the background (`ai/trackschool.py`).  Meanwhile the
best driver of the newest finished generation runs a stint of STINT_LAPS laps
alone (the first from a rolling start); then the newest generation by then
runs the next stint, so generations tick over while you watch.  Every lap
shows a live delta to the session's best lap; the scoreboard lists each stint
and compares with the best lap ever driven on the track by this kind of car.
"""
from __future__ import annotations

import pygame

from ai import championship, evolve, stable, telemetry, trackschool
from ai.brain import NeuralDriver
from sim import tuning
from sim.track import Track
from sim.world import World

from .render import (C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK, HUD_H, WORLD_H, WORLD_W,
                     format_time)
from .screens import ACCEPT, BACK, DOWN, LEFT, MAX_FRAME_TIME, RIGHT, UP, Screen

C_GOOD = (60, 220, 110)
C_BAD = (240, 90, 90)
STINT_LAPS = 3            # laps per stint; the first starts rolling
STUCK_SECONDS = 3.0       # a car this long without moving ends its stint
LAP_LIMIT = 3.0           # ... and so does one this many scripted laps into a lap


class TrackSchoolScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.options = trackschool.options(app.stable_root)
        self.tracks = list(championship.TRACK_ORDER)
        self.pick = [0, 1]               # driver, track
        self.row = 0
        self.mode = "pick"
        self.message = ""
        self.confirm = False

    # ------------------------------------------------------------ choosing

    def rows(self) -> list[str]:
        """DRIVER, TRACK, then what can be done with this driver and track."""
        option, track = self.options[self.pick[0]], self.tracks[self.pick[1]]
        last = trackschool.existing(option, track)
        out = ["driver", "track", "continue" if last is not None else "start"]
        if last is not None:
            out.append("fresh")
            if option["key"].startswith("house:"):
                out.append("house")
        return out

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if self.mode == "watch":
            if event.key in BACK:
                self.stop()
            elif event.key == pygame.K_r:
                self.restart_car()
            elif event.key == pygame.K_h and self.info["key"].startswith("house:"):
                self.save_house()
            return
        rows = self.rows()
        self.row = min(self.row, len(rows) - 1)
        if event.key in BACK:
            from .screens import MainMenu
            self.app.show(MainMenu(self.app))
        elif event.key in UP + DOWN:
            self.row = (self.row + (1 if event.key in DOWN else -1)) % len(rows)
            self.confirm = False
        elif event.key in LEFT + RIGHT and self.row < 2:
            size = len(self.options) if self.row == 0 else len(self.tracks)
            self.pick[self.row] = (self.pick[self.row] + (1 if event.key in RIGHT else -1)) % size
            self.message, self.confirm = "", False
        elif event.key in ACCEPT:
            what = rows[self.row]
            if what in ("start", "continue"):
                self.begin()
            elif what == "fresh":
                self.begin(fresh=True)
            elif what == "house":
                option, track = self.options[self.pick[0]], self.tracks[self.pick[1]]
                self.dir = trackschool.folder(option, track)
                self.save_house()

    def save_house(self) -> None:
        """Press twice: the trained copy becomes the house car (the old one is kept)."""
        if not getattr(self, "confirm", False):
            best = trackschool.best_generation(self.dir)
            if best is None:
                self.message = "No clean test lap yet: let it train a little longer."
                return
            self.confirm = True
            self.message = (f"Press again to make gen {best['gen']} (test lap {best['lap']:.2f} s) the house "
                            f"{trackschool.meta(self.dir)['name']}. The old one is kept.")
            return
        self.confirm = False
        try:
            done = trackschool.save_to_house(self.dir)
            from ai import stable as _stable
            _stable.register(self.app.stable_root)
            self.message = f"{done['name']} is now generation {done['gen']} and will race in championships."
        except ValueError as e:
            self.message = str(e)

    def begin(self, fresh: bool = False) -> None:
        if self.app.training_dir():
            self.message = "Something is already training: stop it first (on its racer card)."
            return
        option, track = self.options[self.pick[0]], self.tracks[self.pick[1]]
        self.dir = trackschool.start(option, track, fresh=fresh)
        self.message, self.confirm = "", False
        self.info = trackschool.meta(self.dir)
        self.run_dir = trackschool.run_path(self.dir)
        trackschool.touch(self.dir)
        self.beat = 0.0
        self.app.start_trackschool(self.dir)
        self.track = Track.load(track)
        self.renderer = self.app.renderer_for(self.track)
        self.params = trackschool.car_params(self.dir)
        self.scripted = evolve.LAP_SECONDS.get(track, 20.0)
        ever = telemetry.best(track, self.params)          # best lap ever by this kind of car
        self.ever = ever["time"] if ever else None
        self.ever_by = ever.get("driver", "?") if ever else None
        self.history: list[dict] = []
        self.stints: list[dict] = []                       # {"gen", "laps": [...]}, newest last
        self.best = None                                   # session best: (time, gen, lap number)
        self.best_trace = None                             # [(distance, time)] of the session-best lap
        self.gen = 0
        self.weights = trackschool.load_start(self.dir)
        self.new_stint()
        self.mode = "watch"

    def stop(self) -> None:
        self.app.stop_training()
        self.mode = "pick"

    # ------------------------------------------------------------ watching

    def new_stint(self) -> None:
        """The newest generation's best driver goes out for STINT_LAPS laps."""
        gen = self.newest()
        if gen is not None:
            try:
                self.weights = evolve.load_generation(self.run_dir, gen)["pop"][0].astype(float)
                self.gen = gen
            except (OSError, ValueError, EOFError, KeyError):
                pass                                       # still being written: next time
            try:
                self.history = evolve.load_history(self.run_dir)
            except (OSError, ValueError):
                pass
        self.world = World(self.track, 1, params=[self.params], ghost=True, rolling=True, laps=10 ** 6)
        self.renderer.clear_skids()
        self.driver = NeuralDriver(self.weights, self.info["arch"], self.info["name"])
        self.driver.car_params = self.params
        self.driver.reset(self.world, 0)
        self.stints.append({"gen": self.gen, "laps": []})
        self.trace: list[tuple[float, float]] = []
        self.accumulator = 0.0
        self.alpha = 1.0
        self.still = 0.0

    def on_resize(self) -> None:
        """Full screen or a new window size: redraw the track at the new size."""
        if self.mode == "watch":
            self.renderer = self.app.renderer_for(self.track)

    def restart_car(self) -> None:
        self.stints.pop()
        self.new_stint()

    def newest(self) -> int | None:
        gens = evolve.list_generations(self.run_dir) if self.run_dir.exists() else []
        later = [g for g in gens if g > self.gen]
        return later[-1] if later else None

    def lap_time_now(self) -> float:
        car = self.world.cars[0]
        return self.world.time - car.lap_start_time

    def live_delta(self) -> float | None:
        """This lap against the session-best lap at the same point of the track."""
        car = self.world.cars[0]
        ref = self.best_trace
        if not ref or not car.crossed_start or car.laps < 1:
            return None
        d = self.trace[-1][0] if self.trace else 0.0
        lo, hi = 0, len(ref) - 1
        if d <= ref[0][0] or d >= ref[-1][0]:
            return None
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ref[mid][0] <= d:
                lo = mid
            else:
                hi = mid
        (d0, t0), (d1, t1) = ref[lo], ref[hi]
        t_ref = t0 + (t1 - t0) * (d - d0) / max(1e-6, d1 - d0)
        return self.lap_time_now() - t_ref

    def update(self, seconds: float) -> None:
        if self.mode != "watch":
            return
        self.beat += seconds
        if self.beat > 1.0:
            self.beat = 0.0
            trackschool.touch(self.dir)                    # keeps the trainer going
        self.accumulator += min(seconds, MAX_FRAME_TIME)
        car = self.world.cars[0]
        length = self.track.length
        while self.accumulator >= tuning.DT:
            events = self.world.step([self.driver.act(self.world, 0)])
            self.renderer.on_tick(self.world, events)
            self.accumulator -= tuning.DT
            if car.crossed_start:                          # distance into this lap, for the live delta
                d = car.s if not self.trace or car.s >= self.trace[-1][0] - length / 2 else car.s + length
                if not self.trace or d >= self.trace[-1][0]:
                    self.trace.append((d, self.lap_time_now()))
            for ev in events:
                if ev[0] != "lap":
                    continue
                n = car.laps
                flying = n >= 2                            # lap 1 started rolling, from behind the line
                self.stints[-1]["laps"].append(ev[2])
                if flying and (self.best is None or ev[2] < self.best[0]):
                    self.best = (ev[2], self.gen, n)
                    self.best_trace = self.trace[:]
                self.trace = [(0.0, 0.0)]
                if n >= STINT_LAPS:
                    self.new_stint()
                    return
            self.still = self.still + tuning.DT if car.speed < 1.0 else 0.0
        if self.still > STUCK_SECONDS or self.lap_time_now() > self.scripted * LAP_LIMIT:
            self.new_stint()
            return
        self.alpha = self.accumulator / tuning.DT

    # ------------------------------------------------------------- drawing

    def draw(self, screen) -> None:
        if self.mode == "pick":
            self.draw_pick(screen)
        else:
            self.draw_watch(screen)

    def draw_pick(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "TRACK SCHOOL", C_HUD_ACCENT, 6, 4, shadow=True)
        ui.text(screen, "small", "Watch a car learn a track. A practice copy trains for pure speed on one track; "
                "the real car is never changed.", C_HUD_DIM, 6, 13)
        rows = [("DRIVER", self.options[self.pick[0]]["name"]),
                ("TRACK", stable.TRACK_NAMES[self.tracks[self.pick[1]]])]
        y = 24
        for i, (label, value) in enumerate(rows):
            colour = C_HUD_ACCENT if self.row == i else C_HUD_TEXT
            ui.text(screen, "mid", label, C_HUD_DIM, 10, y)
            ui.text(screen, "mid", f"<  {value}  >", colour, 40, y)
            y += 8
        option, track = self.options[self.pick[0]], self.tracks[self.pick[1]]
        last = trackschool.existing(option, track)
        labels = {"start": "START", "continue": f"CONTINUE  (it has trained {last} generations here)",
                  "fresh": "START AGAIN FROM SCRATCH", "house": "MAKE THIS THE HOUSE CAR  (its fastest clean generation)"}
        for i, what in enumerate(self.rows()[2:], start=2):
            sel = self.row == i
            ui.text(screen, "mid", ("> " if sel else "") + labels[what], C_HUD_ACCENT if sel else C_HUD_TEXT, 10, y + 2)
            y += 6
        y -= 12
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 10, y + 14)
        ui.text(screen, "small", f"Each stint the newest generation's best car runs {STINT_LAPS} laps (the first "
                "rolling); meanwhile training moves on.", C_HUD_DIM, 10, 70)
        ui.text(screen, "small", "Up/Down choose   Left/Right change   Enter start   Esc back", C_HUD_DIM, 10, 84)

    def draw_watch(self, screen) -> None:
        ui = self.app.ui
        screen.fill((0, 0, 0))
        self.renderer.draw_world(screen, self.world, self.alpha, liveries=[self.info.get("livery")])
        strip = ui.rect(0, 0, WORLD_W, HUD_H)
        pygame.draw.rect(screen, (12, 8, 28), strip)
        pygame.draw.line(screen, C_HUD_ACCENT, strip.bottomleft, strip.bottomright, max(1, int(ui.unit * 0.3)))
        car = self.world.cars[0]
        trained = evolve.list_generations(self.run_dir) if self.run_dir.exists() else []
        ui.text(screen, "small", self.info["name"].upper()[:18], C_HUD_DIM, 3, 0.8)
        ui.text(screen, "big", f"GEN {self.gen}" if self.gen else "START", C_HUD_ACCENT, 3, 3.4)
        ui.text(screen, "small", f"{stable.TRACK_NAMES[self.info['track']]}, training gen "
                f"{(trained[-1] if trained else 0) + 1}", C_HUD_DIM, 3, 8.3)
        lap_no = min(car.laps + 1, STINT_LAPS)
        ui.text(screen, "small", f"LAP {lap_no} OF {STINT_LAPS}" + ("  (rolling)" if lap_no == 1 else ""),
                C_HUD_DIM, 30, 0.8)
        ui.text(screen, "big", format_time(self.lap_time_now()), C_HUD_TEXT, 30, 3.4)
        delta = self.live_delta() if lap_no > 1 else None
        if delta is not None:
            ui.text(screen, "mid", f"{delta:+.2f}", C_GOOD if delta < 0 else C_BAD, 30, 7.6)
            ui.text(screen, "small", "v session best", C_HUD_DIM, 39, 8.3)
        laps = [t for st in self.stints for t in st["laps"]]
        ui.text(screen, "small", "LAST LAP", C_HUD_DIM, 58, 0.8)
        ui.text(screen, "mid", format_time(laps[-1] if laps else None), C_HUD_TEXT, 58, 3.6)
        ui.text(screen, "small", "SESSION BEST", C_HUD_DIM, 76, 0.8)
        if self.best:
            ui.text(screen, "mid", format_time(self.best[0]), C_PINK, 76, 3.6)
            ui.text(screen, "small", f"gen {self.best[1]}" if self.best[1] else "start", C_HUD_DIM, 76, 8.3)
        ui.text(screen, "small", "BEST EVER (THIS CAR TYPE)", C_HUD_DIM, 92, 0.8)
        if self.ever:
            ui.text(screen, "mid", format_time(self.ever), C_HUD_TEXT, 92, 3.6)
            if self.best:
                gap = self.best[0] - self.ever
                ui.text(screen, "small", f"session {gap:+.2f}  ({self.ever_by[:12]})",
                        C_GOOD if gap < 0 else C_HUD_DIM, 92, 8.3)
        else:
            ui.text(screen, "small", "none yet", C_HUD_DIM, 92, 4.4)
        self.draw_chart(screen)
        self.draw_scoreboard(screen)
        keys = "R restart the stint   ESC stop training and go back"
        if self.info["key"].startswith("house:"):
            keys = "H make this the house car (twice)   " + keys
        ui.text(screen, "small", self.message or keys, C_PINK if self.message else C_HUD_TEXT,
                WORLD_W / 2, WORLD_H - 0.8, "midbottom", shadow=True)

    def draw_chart(self, screen) -> None:
        """Each generation's test lap (from training), lower is better."""
        ui = self.app.ui
        track = self.info["track"]
        laps = [(h["gen"], h["exam"][track].get("solo_best_lap")) for h in self.history if track in h.get("exam", {})]
        laps = [(g, t) for g, t in laps if t]
        x0, x1, y0, y1 = 124.0, 154.0, 3.0, 9.6
        ui.text(screen, "small", "TEST LAP BY GEN", C_HUD_DIM, x0, 0.8)
        if len(laps) < 2:
            ui.text(screen, "small", "(soon)", C_HUD_DIM, x0, 5.0)
            return
        times = [t for _, t in laps]
        lo, hi = min(times), max(times)
        span = max(hi - lo, 0.05)
        pts = [ui.px(x0 + (x1 - x0) * k / (len(laps) - 1), y0 + (y1 - y0) * (t - lo) / span)
               for k, (_, t) in enumerate(laps)]
        pygame.draw.lines(screen, C_CYAN, False, pts, max(1, int(ui.unit * 0.25)))
        k = next((k for k, (g, _) in enumerate(laps) if g == self.gen), None)
        if k is not None:
            pygame.draw.circle(screen, C_PINK, pts[k], max(2, int(ui.unit * 0.6)))
        ui.text(screen, "small", f"{times[-1]:.2f}", C_HUD_TEXT, x1 + 0.4, y0 + (y1 - y0) * (times[-1] - lo) / span,
                "midleft")

    def draw_scoreboard(self, screen) -> None:
        """One row per stint: its generation, its laps, its best and the gap to the session best."""
        ui = self.app.ui
        rows = self.stints[-7:]
        x, w = 2.0, 50.0
        h = 3.0 + 2.6 * (len(rows) + 1)
        y = WORLD_H - 3.0 - h
        panel = pygame.Surface(ui.rect(0, 0, w, h).size, pygame.SRCALPHA)
        panel.fill((12, 8, 28, 190))
        screen.blit(panel, ui.px(x, y))
        cols = (1.0, 10.0, 20.0, 29.0, 38.5)
        heads = ("GEN", "LAP 1", "LAP 2", "LAP 3", "V BEST")
        for cx, head in zip(cols, heads):
            ui.text(screen, "small", head, C_HUD_DIM, x + cx, y + 0.6)
        best = self.best[0] if self.best else None
        for r, st in enumerate(rows):
            ry = y + 0.6 + 2.6 * (r + 1)
            live = st is self.stints[-1]
            ui.text(screen, "small", (f"{st['gen']}" if st["gen"] else "start") + (" >" if live else ""),
                    C_HUD_ACCENT if live else C_HUD_TEXT, x + cols[0], ry)
            for k in range(STINT_LAPS):
                if k < len(st["laps"]):
                    t = st["laps"][k]
                    colour = C_PINK if best is not None and k > 0 and abs(t - best) < 1e-9 else (
                        C_HUD_DIM if k == 0 else C_HUD_TEXT)
                    ui.text(screen, "small", f"{t:.2f}", colour, x + cols[k + 1], ry)
            flying = st["laps"][1:]
            if flying and best is not None:
                gap = min(flying) - best
                ui.text(screen, "small", "best" if gap < 1e-9 else f"{gap:+.2f}",
                        C_PINK if gap < 1e-9 else C_HUD_TEXT, x + cols[4], ry)
