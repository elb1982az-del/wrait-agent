#!/usr/bin/env python3
"""Generate the Wraith launcher icon as a hand-built vector SVG."""

from math import cos, pi, sin
from pathlib import Path

OUT = Path("/opt/wrait-agent/assets/wraith_cyber_skull_vector.svg")

BG = "#020806"
VOID = "#000604"
DARK = "#075029"
BONE = "#0D7A43"
MID = "#0E5A30"
GREEN = "#39FF88"
LIGHT = "#C8FFE2"
CYAN = "#00E5FF"

parts: list[str] = []


def add(s: str) -> None:
    parts.append(s)


def poly_path(points: list[tuple[float, float]], close: bool = True) -> str:
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    return d + (" Z" if close else "")


def mirror(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(1024 - x, y) for x, y in points]


def poly(points, fill="none", stroke="none", sw=1, opacity=1.0, extra="") -> None:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    add(
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{sw}" opacity="{opacity}" {extra}/>'
    )


def line(x1, y1, x2, y2, stroke=MID, sw=2, opacity=0.6) -> None:
    add(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>'
    )


def glow(d: str, color=GREEN, widths=(24, 14, 7, 3), opacities=(0.025, 0.05, 0.1, 1.0)) -> None:
    for w, o in zip(widths, opacities):
        add(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" '
            f'opacity="{o}" stroke-linejoin="miter" stroke-linecap="square"/>'
        )


def trace(points, color=GREEN) -> None:
    d = poly_path(points, close=False)
    glow(d, color, (26, 14, 7, 3), (0.025, 0.05, 0.1, 0.95))
    add(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" '
        f'stroke-linejoin="miter" stroke-linecap="square"/>'
    )


def node(x: float, y: float, r=7, color=GREEN, opacity=1.0) -> None:
    pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
    poly(pts, fill=BG, stroke=color, sw=3, opacity=opacity)


def hex_node(cx: float, cy: float, r=12, color=MID, opacity=0.55) -> None:
    pts = [
        (cx + r * cos(i * pi / 3), cy + r * sin(i * pi / 3))
        for i in range(6)
    ]
    poly(pts, fill="none", stroke=color, sw=2, opacity=opacity)


def mirrored_pair(points, **kw) -> None:
    poly(points, **kw)
    poly(mirror(points), **kw)


def mirrored_trace(points, color=GREEN) -> None:
    trace(points, color)
    trace(mirror(points), color)


add('<?xml version="1.0" encoding="UTF-8"?>')
add('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">')

# Background: deep cyber black with faint technical grid and rings.
add(f'<rect width="1024" height="1024" fill="{BG}"/>')
add(f'<ellipse cx="512" cy="520" rx="330" ry="380" fill="#041A0E" opacity="0.55"/>')
for r, op in ((440, 0.20), (380, 0.16), (320, 0.12)):
    add(
        f'<circle cx="512" cy="512" r="{r}" fill="none" stroke="{MID}" '
        f'stroke-width="2" opacity="{op}"/>'
    )
for x in range(0, 1024, 64):
    line(x, 0, x, 1024, "#0C3A20", 1, 0.16)
for y in range(0, 1024, 64):
    line(0, y, 1024, y, "#0C3A20", 1, 0.16)

# Corner HUD brackets.
for pts in (
    [(104, 176), (104, 104), (176, 104)],
    [(920, 176), (920, 104), (848, 104)],
    [(104, 848), (104, 920), (176, 920)],
    [(920, 848), (920, 920), (848, 920)],
):
    glow(poly_path(pts, close=False), MID, (16, 8, 4), (0.02, 0.05, 0.55))

# Angular outer skull silhouette with layered neon halo.
OUTER = [
    (512, 92), (630, 112), (722, 166), (788, 250), (816, 348),
    (802, 438), (762, 528), (704, 596), (690, 664), (704, 736),
    (680, 812), (620, 866), (512, 892), (404, 866), (344, 812),
    (320, 736), (334, 664), (320, 596), (262, 528), (222, 438),
    (208, 348), (236, 250), (302, 166), (394, 112),
]
outer_d = poly_path(OUTER)
glow(outer_d, GREEN, (80, 52, 28, 14, 6), (0.04, 0.08, 0.14, 0.25, 1.0))
add(
    f'<path d="{outer_d}" fill="{BONE}" stroke="{GREEN}" stroke-width="8" '
    f'stroke-linejoin="miter"/>'
)

# Faceted cranium plates: sharp, asymmetric shading for a high-tech bone shell.
mirrored_pair(
    [(512, 92), (394, 112), (302, 166), (236, 250), (320, 262), (390, 214), (512, 182)],
    fill="#12A85F", stroke=MID, sw=2, opacity=0.45,
)
mirrored_pair(
    [(512, 182), (390, 214), (320, 262), (262, 528), (330, 560), (392, 430), (448, 330)],
    fill="#03150C", stroke=MID, sw=2, opacity=0.40,
)
mirrored_pair(
    [(512, 892), (404, 866), (344, 812), (320, 736), (390, 740), (440, 824), (512, 852)],
    fill="#02110A", stroke=MID, sw=2, opacity=0.45,
)

# Crown plate and seams.
CROWN = [
    (512, 128), (596, 164), (640, 236), (600, 300),
    (512, 332), (424, 300), (384, 236), (428, 164),
]
poly(CROWN, fill="none", stroke=MID, sw=3, opacity=0.8)
line(512, 128, 512, 332, LIGHT, 4, 0.75)
line(428, 164, 424, 300, MID, 2, 0.4)
line(596, 164, 600, 300, MID, 2, 0.4)
line(384, 236, 640, 236, MID, 2, 0.3)

# Forehead data bus: mirrored W circuitry, no facial-hair shapes.
mirrored_trace([(512, 200), (512, 268), (448, 326), (392, 286), (360, 330)])
node(512, 268, 8, LIGHT)
node(448, 326, 7, GREEN)
node(392, 286, 7, GREEN)
node(360, 330, 6, CYAN, 0.8)

# Temple routing.
mirrored_trace([(224, 330), (276, 350), (330, 350), (360, 380)])
mirrored_trace([(246, 410), (270, 450), (270, 500), (302, 540)])

# Angular eye sockets: empty, anonymous, glowing rims.
LEFT_EYE = [
    (300, 430), (404, 392), (486, 436),
    (468, 526), (376, 548), (312, 500),
]
for pts in (LEFT_EYE, mirror(LEFT_EYE)):
    d = poly_path(pts)
    glow(d, GREEN, (40, 24, 12, 5), (0.05, 0.10, 0.20, 1.0))
    add(
        f'<path d="{d}" fill="{VOID}" stroke="{LIGHT}" stroke-width="5" '
        f'stroke-linejoin="miter"/>'
    )
    inner = [
        (pts[0][0] + 18, pts[0][1] + 12),
        (pts[1][0] - 10, pts[1][1] + 20),
        (pts[2][0] - 26, pts[2][1] + 8),
        (pts[3][0] - 18, pts[3][1] - 20),
    ]
    line(inner[0][0], inner[0][1], inner[2][0], inner[2][1], MID, 3, 0.65)
    line(inner[1][0], inner[1][1], inner[3][0], inner[3][1], MID, 3, 0.45)

# Socket scan bars (data texture, not eyes).
for yy, xx1, xx2 in ((452, 338, 452), (478, 346, 458), (504, 354, 450)):
    line(xx1, yy, xx2, yy - 8, GREEN, 3, 0.45)
    line(1024 - xx2, yy - 8, 1024 - xx1, yy, GREEN, 3, 0.45)

# Nose cavity: triangular vent, deliberately separate from the jaw.
NOSE = [(512, 566), (468, 646), (512, 668), (556, 646)]
nose_d = poly_path(NOSE)
glow(nose_d, GREEN, (34, 20, 10, 4), (0.05, 0.10, 0.18, 1.0))
add(
    f'<path d="{nose_d}" fill="{VOID}" stroke="{LIGHT}" stroke-width="5" '
    f'stroke-linejoin="miter"/>'
)
line(512, 590, 512, 648, MID, 3, 0.7)

# Cheek armour with vent slats.
LEFT_CHEEK = [
    (270, 514), (320, 558), (366, 634),
    (330, 690), (276, 656), (244, 586),
]
for pts in (LEFT_CHEEK, mirror(LEFT_CHEEK)):
    d = poly_path(pts)
    glow(d, GREEN, (26, 14, 7, 3), (0.025, 0.05, 0.11, 0.85))
    add(
        f'<path d="{d}" fill="{BONE}" stroke="{GREEN}" stroke-width="5" '
        f'stroke-linejoin="miter"/>'
    )
for a, b, c, d in ((286, 574, 334, 606), (294, 600, 340, 630), (306, 624, 344, 650)):
    line(a, b, c, d, GREEN, 3, 0.6)
    line(1024 - c, d, 1024 - a, b, GREEN, 3, 0.6)

# Mandible shell and segmented teeth.
JAW = [
    (348, 690), (408, 812), (512, 858), (616, 812), (676, 690),
    (636, 676), (600, 744), (424, 744), (388, 676),
]
jaw_d = poly_path(JAW)
glow(jaw_d, GREEN, (38, 22, 11, 5), (0.025, 0.05, 0.1, 0.85))
add(
    f'<path d="{jaw_d}" fill="{DARK}" stroke="{GREEN}" stroke-width="6" '
    f'stroke-linejoin="miter"/>'
)
line(420, 748, 604, 748, LIGHT, 4, 0.9)
for i in range(8):
    x0 = 420 + i * 23
    x1 = x0 + 18
    poly(
        [(x0, 750), (x1, 750), (x1 - 4, 826), (x0 + 4, 826)],
        fill="#0E934F", stroke=GREEN, sw=2, opacity=0.9,
    )
line(430, 834, 594, 834, MID, 3, 0.7)
for x, y in ((360, 700), (664, 700), (400, 790), (624, 790)):
    node(x, y, 7, GREEN, 0.85)

# Lower circuit routing and micro nodes.
mirrored_trace([(292, 650), (336, 690), (372, 690)])
mirrored_trace([(330, 760), (370, 800), (404, 800)])
trace([(512, 700), (512, 740), (512, 836)], GREEN)

# Subtle scan lines inside the skull field.
for yy in (300, 360, 640, 700):
    line(280, yy, 744, yy, MID, 2, 0.14)

# Hexagonal micro-processors scattered across the shell.
for hx, hy in (
    (330, 350), (694, 350), (360, 380), (664, 380),
    (276, 350), (748, 350), (270, 500), (754, 500),
    (336, 690), (688, 690), (448, 326), (576, 326),
):
    hex_node(hx, hy, 11, MID, 0.5)

# Fine cyan accent at the crown and socket corners.
line(496, 148, 512, 132, CYAN, 3, 0.8)
line(512, 132, 528, 148, CYAN, 3, 0.8)
for pts in (
    [(300, 430), (320, 410)],
    [(724, 430), (704, 410)],
    [(312, 500), (292, 520)],
    [(712, 500), (732, 520)],
):
    line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], CYAN, 3, 0.7)

add("</svg>")
OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(OUT)
