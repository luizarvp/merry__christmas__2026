#!/usr/bin/env python3
"""
ASCII Christmas Tree
=====================
A rotating 3D point-cloud Christmas tree that grows, lights up and
decorates itself, rendered as colored ASCII glyphs in a real pygame
window (a monospace font atlas is pre-rendered once, then tinted and
blitted per character cell every frame -- same trick "ASCII art code"
videos use to get crisp, anti-aliased characters instead of raw
terminal text).

Reconstructed by watching a screen recording of a similar program
being typed; the overall structure, constant names and build-up
sequence (needles -> inner cone -> trunk -> tinsel garland -> baubles
-> fairy lights -> presents -> star -> "MERRY CHRISTMAS" banner)
follow what was visible on screen, re-implemented from scratch in a
clean single file. It will not be byte-for-byte identical to the
original source (a lot of it scrolled off-screen before it could be
read), but it reproduces the same technique, the same window layout
and constants, and the same overall look.

Controls:
    Space  - pause / resume
    R      - restart the growth animation
    S      - save a screenshot (PNG) next to this script
    Esc    - quit

Usage:
    pip install pygame numpy
    python3 christmas_tree.py
"""
import math
import os
import time

import numpy as np
import pygame

TAU = 2 * math.pi

# --------------------------------------------------------------- window --
TITLE = "ASCII Christmas Tree"
CW, CH, FONT_PX = 9, 14, 15
COLS, ROWS = 88, 74
W, H = COLS * CW, ROWS * CH
MONO = "consolas,menlo,dejavusansmono,couriernew,monospace"
HINT = "Space pause · R restart · S screenshot · Esc quit"
DIM, ACCENT, SIGN = (96, 104, 122), (255, 196, 90), (176, 168, 196)
FPS = 30
RAMP = " .:-=+*#%@"

# ---------------------------------------------------------------- scene --
Y0, Y1 = -1.05, 1.35          # tree base / tip, world units
GROUND = Y0
ASPECT = CW / CH

RED = (219, 58, 52)
GOLD = (255, 196, 61)
GREEN_BOX = (56, 142, 60)
WHITE = (255, 255, 255)
WARM = (255, 205, 120)
SNOW = (231, 240, 250)
BAUBLE_GOLD = (212, 175, 55)
SILVER = (205, 210, 220)
TRUNK = (107, 69, 41)
TINSEL = (255, 210, 90)
LIGHT = WARM
BALL = (255, 255, 255)        # tint multiplier placeholder (unused directly)

# build-up timeline (seconds) -- tuned to match the recording's pacing
T_GROW = (0.4, 7.6)            # needles: base->tip reveal window
T_GARLAND = (6.4, 9.0)
T_BALL = (7.2, 9.6)
T_LIGHTS = (8.2, 11.6)
T_STAR = 11.8
T_MSG = 12.6
POP_DUR = 0.45                 # seconds for a decoration to "pop" into view

MESSAGE = "  FELIZ NATAL 2026!!  "


def unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.clip(n, 1e-9, None)


def envelope(y):
    """Tree silhouette radius at height y: narrow tip, wide base."""
    u = np.clip((y - Y0) / (Y1 - Y0), 0, 1)
    return 0.95 * (1 - u) ** 1.15 + 0.03


def fib_sphere(n):
    """n points spread evenly over a unit sphere (lights / baubles)."""
    i = np.arange(n)
    phi = math.pi * (3 - math.sqrt(5))
    y = 1 - 2 * (i + 0.5) / n
    r = np.sqrt(np.clip(1 - y * y, 0, 1))
    theta = phi * i
    return np.stack([r * np.cos(theta), y, r * np.sin(theta)], axis=1)


def grow_time(y):
    return T_GROW[0] + (T_GROW[1] - T_GROW[0]) * np.clip(
        (y - GROUND) / (Y1 - GROUND), 0, 1)


rng = np.random.default_rng(7)


# ------------------------------------------------------------- geometry --
class Parts:
    """Accumulates every drawable point: position, normal, colour, the
    time it's 'born' at, an ambient brightness base, and (for things
    that pop into existence, like baubles and lights) the centre they
    grow outward from."""

    def __init__(self):
        self.pos, self.nrm, self.col, self.t0 = [], [], [], []
        self.base, self.centre, self.pop, self.phase = [], [], [], []

    def add(
        self, pos, nrm, col, t0, base: float | np.ndarray = 1.0,
        centre=None, pop=False, phase=None
    ):
        pos = np.atleast_2d(np.asarray(pos, dtype=float))
        n = pos.shape[0]
        nrm = np.atleast_2d(np.asarray(nrm, dtype=float))
        if nrm.shape[0] == 1:
            nrm = np.tile(nrm, (n, 1))
        col = np.atleast_2d(np.asarray(col, dtype=float))
        if col.shape[0] == 1:
            col = np.tile(col, (n, 1))
        t0 = np.broadcast_to(np.asarray(t0, dtype=float), (n,)).copy()
        base = np.broadcast_to(np.asarray(base, dtype=float), (n,)).copy()
        centre = pos.copy() if centre is None else np.tile(
            np.asarray(centre, dtype=float), (n, 1))
        phase = np.broadcast_to(
            np.asarray(rng.random() if phase is None else phase, dtype=float),
            (n,)).copy()

        self.pos.append(pos)
        self.nrm.append(nrm)
        self.col.append(col)
        self.t0.append(t0)
        self.base.append(base)
        self.centre.append(centre)
        self.pop.append(np.full(n, bool(pop)))
        self.phase.append(phase)

    def finalize(self):
        if not self.pos:
            z = np.zeros((0, 3))
            return dict(pos=z, nrm=z, col=z, t0=np.zeros(0), base=np.zeros(0),
                        centre=z, pop=np.zeros(0, bool), phase=np.zeros(0))
        return dict(
            pos=np.concatenate(self.pos), nrm=np.concatenate(self.nrm),
            col=np.concatenate(self.col), t0=np.concatenate(self.t0),
            base=np.concatenate(self.base), centre=np.concatenate(self.centre),
            pop=np.concatenate(self.pop), phase=np.concatenate(self.phase))


def build():
    rng_local = np.random.default_rng(7)
    q = Parts()
    tips = []

    # needles: whorls of drooping branches, denser and longer at the bottom
    for i, y in enumerate(np.linspace(Y0 + 0.02, Y1 - 0.06, 26)):
        u = (y - Y0) / (Y1 - Y0)
        R = envelope(y) + 0.05
        nb = int(7 + 13 * (1 - u))
        for b in range(nb):
            a = TAU * (b + 0.5 * rng_local.random()) / nb + i * 0.77
            L = R * rng_local.uniform(0.85, 1.08)
            n = int(26 + 260 * L)
            s = rng_local.random(n) ** 0.65            # 0 trunk .. 1 tip
            d = np.array([math.cos(a), 0, math.sin(a)])
            side = np.array([-math.sin(a), 0, math.cos(a)])
            spread = (0.025 + 0.09 * s) * rng_local.normal(0, 1, n)
            sl = s * L
            p = d * sl[:, None] + side * spread[:, None]
            p[:, 1] = y + 0.06 * sl - 0.20 * sl ** 2 + 0.012 * rng_local.normal(0, 1, n)
            nrm = unit(d * 0.75 + np.array([0, 0.55, 0]) +
                       0.3 * rng_local.normal(0, 1, (n, 3)))
            ao = (0.45 + 0.70 * s ** 1.3) * rng_local.uniform(0.85, 1.15, n)
            snow = (s > 0.5) & (rng_local.random(n) < 0.06 * s) & (nrm[:, 1] > 0.5)
            green = np.array([0.32, 0.80, 0.32]) + np.array([0.18, 0.55, 0.20]) * \
                rng_local.random((n, 1))
            col = np.where(snow[:, None], np.array(WHITE), np.clip(green * 255, 0, 255))
            t0 = grow_time(y) + 0.45 * s
            q.add(p, nrm, col, t0, base=np.where(snow, 1.0, ao))
            if n:
                k = int(np.argmax(s))
                tips.append([p[k, 0], p[k, 1], p[k, 2]])

    # dark inner cone so the starfield never shows through the gaps
    m = 6000
    y = Y0 + (Y1 - 0.1 - Y0) * rng_local.random(m)
    phi = rng_local.random(m) * TAU
    r = 0.6 * envelope(y)
    pos = np.stack([np.cos(phi) * r, y, np.sin(phi) * r], axis=1)
    out = np.stack([np.cos(phi), np.full(m, 0.3), np.sin(phi)], axis=1)
    q.add(pos, out, np.full((m, 3), [10, 42, 16]), grow_time(y), base=0.75)

    # trunk
    m = 1500
    y = GROUND + rng_local.random(m) * (Y0 + 0.1 - GROUND)
    phi = rng_local.random(m) * TAU
    bark = 0.75 + 0.25 * np.sign(np.sin(phi * 30 + y * 5))
    n = np.stack([np.cos(phi), np.zeros(m), np.sin(phi)], axis=1)
    pos = n * 0.08
    pos[:, 1] = y
    col = np.array(TRUNK) * bark[:, None] / 255 * 255
    q.add(pos, n, col, grow_time(y))

    # tinsel garland: a gold spiral drooping in swags between hanging points
    u = np.linspace(0, 1, 2600)
    turns = 3.6
    yg = Y0 + 0.15 + (Y1 - Y0 - 0.45) * u
    ag = TAU * turns * u + 0.9
    swag = -0.07 * np.abs(np.sin(ag * 2.5))
    rg = envelope(yg) + 0.07
    line = np.stack([np.cos(ag) * rg, yg + swag, np.sin(ag) * rg], axis=1)
    for _ in range(4):
        nrm = np.stack([np.cos(ag), np.full_like(u, 0.3), np.sin(ag)], axis=1)
        jitter = line + 0.016 * rng_local.normal(0, 1, line.shape)
        t0 = T_GARLAND[0] + u * (T_GARLAND[1] - T_GARLAND[0])
        q.add(jitter, nrm, np.full((len(u), 3), TINSEL), t0,
              base=0.9, phase=rng_local.random())

    # baubles: mostly red, some gold
    sphere = fib_sphere(160)
    for k in range(34):
        u1 = (k + rng_local.random()) / 34
        y = Y0 + 0.08 + u1 * (Y1 - Y0 - 0.38)
        a = k * 2.39996 + rng_local.random() * 0.4   # golden-angle spiral
        c = np.array([math.cos(a), 0, math.sin(a)]) * envelope(y) + \
            np.array([0, y - 0.03, 0])
        rad = 0.058 + 0.032 * (1 - u1)
        col = RED if k % 3 != 0 else (BAUBLE_GOLD if k % 2 == 0 else SILVER)
        t0 = T_BALL[0] + rng_local.random() * (T_BALL[1] - T_BALL[0])
        q.add(c + sphere * rad, sphere, np.full((len(sphere), 3), col), t0,
              base=1.0, centre=c, pop=True)

    # fairy lights on the branch tips
    tips = np.array(tips)
    bulb = fib_sphere(16)
    if len(tips):
        pick = rng_local.choice(len(tips), min(170, len(tips)), replace=False)
        light_t0 = T_LIGHTS[0] + rng_local.random(len(pick)) * \
            (T_LIGHTS[1] - T_LIGHTS[0])
        for c, t0 in zip(tips[pick], light_t0):
            col = WARM if rng_local.random() < 0.8 else (255, 240, 215)
            q.add(c + bulb * 0.03, bulb, np.full((len(bulb), 3), col), t0,
                  base=1.0, centre=c, pop=True, phase=rng_local.random() * TAU)

    # presents: boxes with a crossed ribbon
    gifts = [(-0.55, 1.12, 0.30, 0.24, 0.28, RED, GOLD),
             (0.50, 1.18, 0.26, 0.30, 0.24, GOLD, RED),
             (0.05, 1.10, 0.34, 0.18, 0.26, GOLD, RED),
             (0.80, 1.18, 0.24, 0.26, 0.22, GREEN_BOX, RED)]
    for x0, z0, w, h, d, body, rib in gifts:
        m = 1400
        face = rng_local.integers(0, 3, m)
        fa, fb = rng_local.random(m) - 0.5, rng_local.random(m) - 0.5
        lx = np.select([face == 0, face == 1, face == 2],
                        [fa * w, np.full(m, w / 2) * np.sign(fb), fa * w])
        ly = np.where(face == 0, h, (fb + 0.5) * h)
        lz = np.select([face == 0, face == 1, face == 2],
                        [fb * d, fa * d, np.full(m, d / 2) * np.sign(fa)])
        pos = np.stack([lx + x0, ly + GROUND - h, lz + z0], axis=1)
        n = np.zeros((m, 3))
        n[face == 0] = [0, 1, 0]
        n[face == 1] = [1, 0, 0]
        n[face == 2] = [0, 0, 1]
        ribbon = (np.abs(lx) < 0.025 * w / 0.26) | (np.abs(lz) < 0.025 * d / 0.26)
        col = np.where(ribbon[:, None], np.array(WHITE if rib == RED else rib),
                        np.array(body))
        t0 = T_BALL[1] + 0.3 + rng_local.random(m) * 0.6
        q.add(pos, n, col, t0, base=0.85 + 0.15 * rng_local.random(m))

    return q.finalize()


# -------------------------------------------------------------- render --
def rotate_y(pos, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
    return np.stack([x * c + z * s, y, -x * s + z * c], axis=1)


def project(pos, cols, rows, aspect):
    scale = rows * 0.35
    sx = cols / 2 + pos[:, 0] * scale / aspect
    sy = rows * 0.546 - pos[:, 1] * scale
    return sx, sy, pos[:, 2]


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)          # smoothstep "pop"


def star_cells(cx, cy, t, flash):
    """Yield (row, col, char, colour) cells for the twinkling star on top."""
    cells = []
    tint = tuple(int(g + (w - g) * flash) for g, w in zip(GOLD, WHITE))
    power = 1 + 1.6 * flash
    for k in range(10):
        ang = k * TAU / 10 + 0.1 * math.sin(t * 0.7)
        if math.sin(ang) < -0.35:
            continue
        reach = power * (2.4 + 0.8 * math.sin(t * 3 + k * 1.3)) * \
            (1.0 if k % 2 == 0 else 0.55)
        glyph_set = "-|/\\"
        ch = glyph_set[int(round(math.degrees(ang) % 180 / 45)) % 4]
        for s in np.arange(0.6, reach, 0.55):
            y = int(round(cy - math.sin(ang) * s))
            x = int(round(cx + math.cos(ang) * s * ASPECT))
            cells.append((y, x, ch, tint))
    cells.append((int(round(cy)), int(round(cx)), "@" if flash > 0.5 else "*", tint))
    return cells


class Renderer:
    def __init__(self, cols=COLS, rows=ROWS, cw=CW, ch=CH, font_px=FONT_PX, hud_px=16):
        self.cols, self.rows, self.cw, self.ch = cols, rows, cw, ch
        self.w, self.h = cols * cw, rows * ch
        font = pygame.font.SysFont(MONO, font_px)
        atlas = []
        for code in range(32, 127):
            s = pygame.Surface((cw, ch))
            g = font.render(chr(code), True, (255, 255, 255))
            s.blit(g, ((cw - g.get_width()) // 2, (ch - g.get_height()) // 2))
            atlas.append(pygame.surfarray.array3d(s).transpose(1, 0, 2))
        self.atlas = np.stack(atlas)                     # glyph, CH, CW, 3
        self.hud_font = pygame.font.SysFont(MONO, hud_px)
        self.art = pygame.Surface((self.w, self.h))

    def draw(self, surf, char_grid, rgb_grid, origin=(0, 0)):
        art = pygame.surfarray.pixels3d(self.art)
        art[:] = 0
        idx = np.clip(np.frombuffer("".join(char_grid).encode("latin-1", "replace"),
                                     dtype=np.uint8).astype(int) - 32, 0, 94)
        idx = idx.reshape(self.rows, self.cols)
        glyphs = self.atlas[idx]                           # rows, cols, CH, CW, 3
        tinted = (glyphs.astype(np.float32) / 255.0) * rgb_grid[:, :, None, None, :]
        tinted = tinted.astype(np.uint8)
        full = tinted.transpose(0, 2, 1, 3, 4).reshape(self.rows * self.ch,
                                                         self.cols * self.cw, 3)
        art_view = full.transpose(1, 0, 2)
        art[:, :, :] = art_view
        del art
        surf.blit(self.art, origin)


def starfield_layer(cols, rows, t, srng):
    buf = [" "] * (cols * rows)
    rgb = np.zeros((rows, cols, 3))
    n = (cols * rows) // 10
    xs = srng.integers(0, cols, n)
    ys = srng.integers(0, max(1, int(rows * 0.62)), n)
    for x, y, ph in zip(xs, ys, srng.random(n)):
        twinkle = 0.5 + 0.5 * math.sin(t * 2 + ph * TAU)
        ch = "+" if twinkle > 0.72 else ("." if twinkle > 0.35 else "`")
        buf[y * cols + x] = ch
        rgb[y, x] = np.array([150, 165, 205]) * (0.35 + 0.55 * twinkle)
    return buf, rgb


def composite(pos, rgb, cols, rows, extra_cells=None):
    char = [" "] * (cols * rows)
    rgb_grid = np.zeros((rows, cols, 3))
    depth = np.full((rows, cols), 1e9)
    lit = np.zeros((rows, cols), dtype=bool)

    sx, sy, dep = project(pos, cols, rows, ASPECT)
    xi, yi = np.round(sx).astype(int), np.round(sy).astype(int)
    ok = (xi >= 0) & (xi < cols) & (yi >= 0) & (yi < rows)
    xi, yi, dep, rgb = xi[ok], yi[ok], dep[ok], rgb[ok]

    order = np.argsort(-dep)
    for k in order:
        r, c = int(yi[k]), int(xi[k])
        if dep[k] <= depth[r, c] + 0.035:
            depth[r, c] = dep[k]
            lum = (0.299 * rgb[k, 0] + 0.587 * rgb[k, 1] + 0.114 * rgb[k, 2]) / 255
            b = float(np.clip(lum, 0, 1))
            char[r * cols + c] = RAMP[min(len(RAMP) - 1, int(b * len(RAMP)))]
            rgb_grid[r, c] = rgb[k]
            lit[r, c] = True

    if extra_cells:
        for r, c, ch, col in extra_cells:
            if 0 <= r < rows and 0 <= c < cols:
                char[r * cols + c] = ch
                rgb_grid[r, c] = col
                lit[r, c] = True
    return char, rgb_grid, lit


def main():
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()
    pygame.display.set_caption(TITLE)
    hud_h = 64
    screen = pygame.display.set_mode((W, H + hud_h))
    clock = pygame.time.Clock()
    renderer = Renderer()
    star_rng = np.random.default_rng(3)

    scene = build()
    pos0 = np.asarray(scene["pos"], dtype=float)
    nrm0 = np.asarray(scene["nrm"], dtype=float)
    col0 = np.asarray(scene["col"], dtype=float)
    t0arr = np.asarray(scene["t0"], dtype=float)
    base0 = np.asarray(scene["base"], dtype=float)
    centre0 = np.asarray(scene["centre"], dtype=float)
    pop0 = np.asarray(scene["pop"], dtype=bool)
    phase0 = np.asarray(scene["phase"], dtype=float)

    paused = False
    t_start = time.time()
    t_pause_accum = 0.0
    frame_no = 0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    t_start = time.time()
                    t_pause_accum = 0.0
                elif event.key == pygame.K_s:
                    fname = f"christmas_tree_{int(time.time())}.png"
                    pygame.image.save(screen, fname)
                    print("saved", fname)

        now = time.time()
        if paused:
            t_pause_accum += clock.get_time() / 1000.0
        t = now - t_start - t_pause_accum
        deg = (t * 22.0) % 360

        # growth: a point is visible once t >= t0, pops in over POP_DUR
        age = t - t0arr
        alive = age >= 0
        scale = np.where(pop0, ease(age / POP_DUR), 1.0)
        fade = np.where(pop0, 1.0, np.clip(age / POP_DUR, 0, 1))

        world = np.where(pop0[:, None],
                          centre0 + (pos0 - centre0) * scale[:, None],
                          pos0)
        rotated = rotate_y(world[alive], deg)

        nrm_r = rotate_y(nrm0[alive], deg)
        light_dir = unit(np.array([0.35, 0.8, 0.5]))
        diffuse = 0.55 + 0.45 * np.clip(nrm_r @ light_dir, 0, 1)
        twinkle = np.where(
            phase0[alive] >= 0,
            0.6 + 0.4 * np.sin(t * 3.2 + phase0[alive] * TAU), 1.0)
        shade = (base0[alive] * diffuse * fade[alive] *
                 np.where(pop0[alive], twinkle, 1.0))
        shaded_rgb = np.clip(col0[alive] * shade[:, None], 0, 255)

        star_t = t - T_STAR
        extra = []
        n_lit = 0
        if star_t > -0.3:
            flash = float(np.clip(1 - max(star_t, 0) / 1.0, 0, 1) ** 2)
            apex = rotate_y(np.array([[0.0, Y1 + 0.09, 0.0]]), deg)
            sx, sy, _ = project(apex, COLS, ROWS, ASPECT)
            extra += star_cells(sx[0], sy[0], t, flash)

        char, rgb_grid, lit = composite(rotated, shaded_rgb, COLS, ROWS, extra)
        sbuf, srgb = starfield_layer(COLS, ROWS, t, star_rng)
        for i in range(COLS * ROWS):
            if not lit.flat[i] and sbuf[i] != " ":
                char[i] = sbuf[i]
        rgb_grid = np.where(lit[:, :, None], rgb_grid, srgb)

        if t > T_MSG:
            row = ROWS - 9
            x0 = (COLS - len(MESSAGE)) // 2
            shown = min(len(MESSAGE), int((t - T_MSG) * 10))
            for i, ch in enumerate(MESSAGE[:shown]):
                c = x0 + i
                if ch != " " and 0 <= c < COLS:
                    tint = (RED, GOLD, GREEN_BOX)[(i // 2 + int(t * 1.5)) % 3]
                    bright = 0.85 + 0.25 * math.sin(t * 5 + i)
                    char[row * COLS + c] = ch
                    rgb_grid[row, c] = np.clip(np.array(tint) * bright, 0, 255)

        n_lit = int(np.sum((base0[alive] > 0) & pop0[alive] & (twinkle > 0.8)))
        letters = int(sum(1 for ch in char if ch != " "))

        screen.fill((6, 8, 14))
        renderer.draw(screen, char, rgb_grid, origin=(0, 0))

        hud = renderer.hud_font
        y = H + 6
        screen.blit(hud.render(f"rotation {deg:7.2f}°     lights  {n_lit}",
                                True, ACCENT), (14, y))
        screen.blit(hud.render(f"letters {letters:,}", True, SIGN), (14, y + 20))
        screen.blit(hud.render(HINT, True, DIM),
                    (W - hud.size(HINT)[0] - 14, y + 10))

        pygame.display.flip()
        clock.tick(FPS)
        frame_no += 1

    pygame.quit()


if __name__ == "__main__":
    main()