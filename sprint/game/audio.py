"""Sound synthesised in code: no audio files.

If no audio device can be opened the Audio object goes quiet and every method
becomes a no-op, so the game runs the same with or without sound.

Engine pitch: pygame cannot change the pitch of a playing sound, so each car
has a ladder of short engine loops at rising pitches and cross-fades between
the two nearest rungs on two mixer channels.
"""
from __future__ import annotations

import numpy as np
import pygame

from sim import tuning

SAMPLE_RATE = 22050
ENGINE_STEPS = 14
MAX_CARS = 4
SQUEAL_CHANNEL = 2 * MAX_CARS
RESERVED = SQUEAL_CHANNEL + 1


class Audio:
    def __init__(self, enabled: bool = True, volume: float = 0.7):
        self.ok = False
        self.volume = volume
        if not enabled:
            return
        try:
            pygame.mixer.init(SAMPLE_RATE, -16, 2, 512)
            self.rate, _, self.channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(20)
            pygame.mixer.set_reserved(RESERVED)
            self._build()
            self.ok = True
        except Exception as exc:  # no device, no mixer module, odd format...
            print(f"audio: disabled ({exc}); the game will run silently")
            self.ok = False

    # ------------------------------------------------------------ synthesis

    def _sound(self, wave: np.ndarray) -> pygame.mixer.Sound:
        data = (np.clip(wave, -1.0, 1.0) * 32000).astype("<i2")
        if self.channels > 1:
            data = np.repeat(data[:, None], self.channels, axis=1)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _tone(self, freq: float, seconds: float, shape: float = 0.0) -> np.ndarray:
        t = np.arange(int(self.rate * seconds)) / self.rate
        wave = np.sin(2 * np.pi * freq * t)
        if shape:
            wave = np.tanh(wave * (1 + 4 * shape))      # squarer = more "arcade"
        env = np.minimum(1.0, np.minimum(t / 0.005, (seconds - t) / 0.04))
        return wave * env

    def _engine_loop(self, freq: float) -> pygame.mixer.Sound:
        cycles = max(2, 2 * round(0.15 * freq))          # even, so the sub-octave loops too
        n = int(round(cycles * self.rate / freq))
        phase = np.arange(n) * (cycles / n) * 2 * np.pi
        wave = np.zeros(n)
        for h, amp in ((1, 1.0), (2, 0.55), (3, 0.38), (4, 0.22), (5, 0.16), (6, 0.1)):
            wave += amp * np.sin(h * phase + 0.4 * h)
        wave += 0.5 * np.sin(0.5 * phase)
        return self._sound(np.tanh(wave * 0.9) * 0.7)

    def _build(self) -> None:
        rng = np.random.default_rng(1986)
        self.engine_loops = [self._engine_loop(46.0 * (4.4 ** (k / (ENGINE_STEPS - 1))))
                             for k in range(ENGINE_STEPS)]

        # Tyre squeal: band-limited noise.  Filtering in the frequency domain
        # makes the result periodic, so it loops without a click.
        n = int(self.rate * 0.6)
        spectrum = np.fft.rfft(rng.standard_normal(n))
        freqs = np.fft.rfftfreq(n, 1 / self.rate)
        spectrum *= np.exp(-((freqs - 1900.0) / 420.0) ** 2)
        squeal = np.fft.irfft(spectrum, n)
        squeal /= np.max(np.abs(squeal))
        self.squeal = self._sound(squeal * 0.8)

        t = np.arange(int(self.rate * 0.3)) / self.rate
        sweep = np.sin(2 * np.pi * (120 * t - 110 * t * t))
        noise = rng.standard_normal(len(t))
        noise = np.convolve(noise, np.ones(24) / 24, mode="same") * 3
        self.thump = self._sound((sweep * 0.9 + noise * 0.6) * np.exp(-t * 16))

        self.beep = self._sound(self._tone(440, 0.16, 0.5) * 0.5)
        self.go = self._sound(self._tone(880, 0.55, 0.5) * 0.5)
        self.blip = self._sound(self._tone(660, 0.05, 0.3) * 0.3)
        self.select = self._sound(np.concatenate([self._tone(660, 0.06, 0.3), self._tone(990, 0.09, 0.3)]) * 0.35)
        self.lap = self._sound(np.concatenate([self._tone(784, 0.08, 0.2), self._tone(1175, 0.14, 0.2)]) * 0.4)
        self.fanfare = self._sound(np.concatenate(
            [self._tone(f, d, 0.4) for f, d in ((523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.35))]) * 0.45)
        self._engine_step = [[-1, -1] for _ in range(MAX_CARS)]
        self._squeal_on = False

    # ------------------------------------------------------------- one-shots

    def _play(self, sound, volume: float = 1.0) -> None:
        if not self.ok:
            return
        channel = pygame.mixer.find_channel(True)
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume * self.volume)))
            channel.play(sound)

    def play(self, name: str, volume: float = 1.0) -> None:
        """name: beep, go, blip, select, lap, fanfare, thump."""
        if self.ok:
            self._play(getattr(self, name), volume)

    def handle_events(self, events) -> None:
        """Turn sim events into sound."""
        if not self.ok:
            return
        for event in events:
            kind = event[0]
            if kind in ("wall", "car"):
                self._play(self.thump, min(1.0, 0.25 + event[-1] / 28.0))
            elif kind == "count":
                self._play(self.beep)
            elif kind == "go":
                self._play(self.go)
            elif kind == "lap":
                self._play(self.lap)
            elif kind == "race_over":
                self._play(self.fanfare)

    # -------------------------------------------------- continuous sounds

    def update_race(self, world, running: bool = True) -> None:
        """Call once per frame: engine pitch follows speed, squeal follows slip."""
        if not self.ok:
            return
        if not running:
            self.silence()
            return
        count = len(world.cars)
        level = self.volume * 0.55 / (count ** 0.5)
        squeal = 0.0
        for i, car in enumerate(world.cars[:MAX_CARS]):
            frac = min(abs(car.forward_speed) / car.params.top_speed, 1.0)
            # Three pretend gears: the pitch climbs, drops back, climbs again.
            gear = min(int(frac * 3), 2)
            within = frac * 3 - gear
            pitch = min(0.12 * gear + 0.76 * within, 1.0)
            pos = pitch * (ENGINE_STEPS - 1)
            low = min(int(pos), ENGINE_STEPS - 2)
            mix = pos - low
            loud = level * (0.45 + 0.55 * car.throttle)
            for step, weight in ((low, 1.0 - mix), (low + 1, mix)):
                parity = step % 2
                channel = pygame.mixer.Channel(2 * i + parity)
                if self._engine_step[i][parity] != step:
                    channel.play(self.engine_loops[step], loops=-1)
                    self._engine_step[i][parity] = step
                channel.set_volume(loud * weight)
            if car.surface == 0 and car.speed > 4.0:
                over = (car.slip - car.params.slide_threshold * 0.6) / 7.0
                squeal = max(squeal, min(1.0, over))
        channel = pygame.mixer.Channel(SQUEAL_CHANNEL)
        if squeal > 0.0:
            if not self._squeal_on:
                channel.play(self.squeal, loops=-1)
                self._squeal_on = True
            channel.set_volume(squeal * self.volume * 0.5)
        elif self._squeal_on:
            channel.set_volume(0.0)

    def silence(self) -> None:
        """Mute engines and squeal (pause, menus)."""
        if not self.ok:
            return
        for i in range(RESERVED):
            pygame.mixer.Channel(i).stop()
        self._engine_step = [[-1, -1] for _ in range(MAX_CARS)]
        self._squeal_on = False
