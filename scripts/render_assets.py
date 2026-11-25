#!/usr/bin/env python3
"""Render the profile's SVG assets from profile.toml.

    scripts/render_assets.py            write assets/{banner,toolbelt}-{dark,light}.svg
    scripts/render_assets.py --check    exit 1 if a committed SVG differs from what
                                        profile.toml would produce (used by CI)

Standard library only. Output is deterministic, so the --check comparison is
an exact byte match. Every SVG is parsed back as XML before it is written.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

# Brand palette: navy + electric cyan, matching rajeshshukla.pages.dev.
# Light values are darkened until text and strokes clear WCAG AA on white.
THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0f121a",
        "border": "#21262d",
        "grid": "#4dd2ff",
        "grid_opacity": "0.06",
        "glow_opacity": "0.22",
        "glow": "#4dd2ff",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "accent": "#4dd2ff",
        "grad_from": "#4dd2ff",
        "grad_to": "#9db7ff",
        "stage_off": "#30363d",
        "ok": "#3fb950",
        "chip_fill": "#161b22",
        "chip_stroke": "#30363d",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "grid": "#0969da",
        "grid_opacity": "0.07",
        "glow_opacity": "0.16",
        "glow": "#22d3ee",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#0369a1",
        "grad_from": "#0369a1",
        "grad_to": "#4f46e5",
        "stage_off": "#d0d7de",
        "ok": "#1a7f37",
        "chip_fill": "#f6f8fa",
        "chip_stroke": "#d0d7de",
    },
}


def num(x: float) -> str:
    """Compact, stable number formatting for SVG attributes."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def text_width(s: str, size: float) -> float:
    """Generous width estimate for proportional sans text.

    SVG rendered through <img> cannot measure text, so chips are sized from a
    per-glyph table that errs wide: a little spare padding is invisible,
    text spilling out of its pill is not.
    """
    narrow, wide = set("fijlrtI|.,:;'!() "), set("mwMW@")
    em = 0.0
    for ch in s:
        if ch in narrow:
            em += 0.32
        elif ch in wide:
            em += 0.90
        elif ch.isupper() or ch.isdigit():
            em += 0.68
        else:
            em += 0.55
    return em * size


# --------------------------------------------------------------------------
# Banner
# --------------------------------------------------------------------------

BANNER_W, BANNER_H = 1000, 280
CYCLE_S = 6  # one full pipeline run, seconds
STAGE_W, STAGE_H, STAGE_GAP = 92, 48, 14
PULSE_END = 80.0  # % of the cycle at which the pulse reaches the last stage
HOLD_UNTIL, RESET_AT = 92.0, 97.0  # all stages stay green, then reset


def banner(cfg: dict, t: dict[str, str]) -> str:
    b = cfg["banner"]
    stages: list[str] = b["stages"]
    n = len(stages)
    total = n * STAGE_W + (n - 1) * STAGE_GAP
    x0 = BANNER_W - 48 - total
    cy = 142
    top = cy - STAGE_H / 2

    # Percent of the cycle at which the pulse crosses each stage's centre.
    rail_y = top + STAGE_H + 12  # progress rail under the stages; the pulse rides it
    lit_at = [round((i * (STAGE_W + STAGE_GAP) + STAGE_W / 2) / total * PULSE_END, 1) for i in range(n)]
    done_at = round(lit_at[-1] + 4, 1)

    keyframes = []
    for i, p in enumerate(lit_at):
        keyframes.append(
            f"@keyframes box{i}{{0%,{num(p - 0.1)}%{{stroke:{t['stage_off']};fill-opacity:0}}"
            f"{num(p)}%,{num(HOLD_UNTIL)}%{{stroke:{t['accent']};fill-opacity:.12}}"
            f"{num(RESET_AT)}%,100%{{stroke:{t['stage_off']};fill-opacity:0}}}}"
            f"@keyframes dot{i}{{0%,{num(p - 0.1)}%{{fill:{t['muted']}}}"
            f"{num(p)}%,{num(HOLD_UNTIL)}%{{fill:{t['ok']}}}"
            f"{num(RESET_AT)}%,100%{{fill:{t['muted']}}}}}"
            f".box{i}{{animation:box{i} {CYCLE_S}s linear infinite}}"
            f".dot{i}{{animation:dot{i} {CYCLE_S}s linear infinite}}"
        )

    css = (
        f".sans{{font-family:{SANS}}}.mono{{font-family:{MONO}}}"
        f"@keyframes pulse{{0%{{transform:translateX(0);opacity:0}}3%{{opacity:1}}"
        f"{num(PULSE_END)}%{{transform:translateX({num(total)}px);opacity:1}}"
        f"{num(PULSE_END + 4)}%,100%{{transform:translateX({num(total)}px);opacity:0}}}}"
        f".pulse{{animation:pulse {CYCLE_S}s linear infinite}}"
        f"@keyframes progress{{0%{{transform:scaleX(0);opacity:1}}{num(PULSE_END)}%,{num(HOLD_UNTIL)}%"
        f"{{transform:scaleX(1);opacity:1}}{num(RESET_AT)}%,100%{{transform:scaleX(1);opacity:0}}}}"
        f".progress{{transform-box:fill-box;transform-origin:0 50%;animation:progress {CYCLE_S}s linear infinite}}"
        f"@keyframes status{{0%,{num(done_at - 0.1)}%{{opacity:0}}{num(done_at)}%,{num(HOLD_UNTIL)}%{{opacity:1}}"
        f"{num(RESET_AT)}%,100%{{opacity:0}}}}"
        f".status{{animation:status {CYCLE_S}s linear infinite}}"
        f"@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}"
        f".cursor{{animation:blink 1.1s steps(1) infinite}}"
        + "".join(keyframes)
        # Without motion, show the finished run: every stage green, status visible.
        + "@media (prefers-reduced-motion:reduce){.pulse{display:none}"
        ".pulse,.progress,.status,.cursor,[class*=box],[class*=dot]{animation:none}}"
    )

    prompt = b["prompt"]
    cursor_x = 48 + len(prompt) * 15 * 0.6 + 4

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{BANNER_W}" height="{BANNER_H}" '
        f'viewBox="0 0 {BANNER_W} {BANNER_H}" role="img" aria-labelledby="t d">',
        f'<title id="t">{escape(b["name"])} — {escape(b["title"])}</title>',
        f'<desc id="d">{escape(b["tagline"])}. A delivery pipeline runs through the stages '
        f'{escape(", ".join(stages))}.</desc>',
        f"<style>{css}</style>",
        "<defs>",
        f'<clipPath id="frame"><rect width="{BANNER_W}" height="{BANNER_H}" rx="18"/></clipPath>',
        '<pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">'
        f'<path d="M28 0H0V28" fill="none" stroke="{t["grid"]}" stroke-opacity="{t["grid_opacity"]}"/></pattern>',
        f'<radialGradient id="glow" cx="{num((x0 + total / 2) / BANNER_W)}" cy="0.5" r="0.6">'
        f'<stop offset="0" stop-color="{t["glow"]}" stop-opacity="{t["glow_opacity"]}"/>'
        f'<stop offset="1" stop-color="{t["glow"]}" stop-opacity="0"/></radialGradient>',
        '<linearGradient id="name" x1="0" x2="1" y1="0" y2="0">'
        f'<stop offset="0" stop-color="{t["grad_from"]}"/><stop offset="1" stop-color="{t["grad_to"]}"/>'
        "</linearGradient>",
        "</defs>",
        '<g clip-path="url(#frame)">',
        f'<rect width="{BANNER_W}" height="{BANNER_H}" fill="{t["bg"]}"/>',
        f'<rect width="{BANNER_W}" height="{BANNER_H}" fill="url(#grid)"/>',
        f'<rect width="{BANNER_W}" height="{BANNER_H}" fill="url(#glow)"/>',
        "</g>",
        f'<rect x="0.5" y="0.5" width="{BANNER_W - 1}" height="{BANNER_H - 1}" rx="17.5" '
        f'fill="none" stroke="{t["border"]}"/>',
        # Identity, left column.
        f'<text class="mono" x="48" y="86" font-size="15" fill="{t["accent"]}">{escape(prompt)}</text>',
        f'<rect class="cursor" x="{num(cursor_x)}" y="74" width="8" height="15" fill="{t["accent"]}"/>',
        f'<text class="sans" x="46" y="146" font-size="54" font-weight="700" letter-spacing="-1" '
        f'fill="url(#name)">{escape(b["name"])}</text>',
        f'<text class="sans" x="48" y="186" font-size="22" font-weight="500" fill="{t["text"]}">'
        f"{escape(b['title'])}</text>",
        f'<text class="mono" x="48" y="222" font-size="13" fill="{t["muted"]}">{escape(b["tagline"])}</text>',
        # Pipeline, right column.
        f'<text class="mono" x="{num(x0)}" y="{num(top - 16)}" font-size="11" letter-spacing="1.5" '
        f'fill="{t["muted"]}">DELIVERY PIPELINE</text>',
        f'<line x1="{num(x0)}" y1="{cy}" x2="{num(x0 + total)}" y2="{cy}" stroke="{t["stage_off"]}" '
        f'stroke-width="2" stroke-dasharray="4 4"/>',
    ]
    for i, name in enumerate(stages):
        x = x0 + i * (STAGE_W + STAGE_GAP)
        parts += [
            # Opaque backing hides the dashed connector; the tinted box sits on top.
            f'<rect x="{num(x)}" y="{num(top)}" width="{STAGE_W}" height="{STAGE_H}" rx="10" fill="{t["bg"]}"/>',
            f'<rect class="box{i}" x="{num(x)}" y="{num(top)}" width="{STAGE_W}" height="{STAGE_H}" rx="10" '
            f'fill="{t["accent"]}" fill-opacity=".12" stroke="{t["accent"]}" stroke-width="1.5"/>',
            f'<circle class="dot{i}" cx="{num(x + 16)}" cy="{cy}" r="4" fill="{t["ok"]}"/>',
            f'<text class="mono" x="{num(x + 28)}" y="{cy + 4}" font-size="12" letter-spacing="0.5" '
            f'fill="{t["text"]}">{escape(name.upper())}</text>',
        ]
    parts += [
        f'<line x1="{num(x0)}" y1="{num(rail_y)}" x2="{num(x0 + total)}" y2="{num(rail_y)}" '
        f'stroke="{t["stage_off"]}" stroke-width="2" stroke-linecap="round"/>',
        f'<rect class="progress" x="{num(x0)}" y="{num(rail_y - 1)}" width="{num(total)}" height="2" rx="1" '
        f'fill="{t["accent"]}"/>',
        f'<circle class="pulse" cx="{num(x0)}" cy="{num(rail_y)}" r="4.5" fill="{t["accent"]}"/>',
        f'<g class="status"><circle cx="{num(x0 + 4)}" cy="{num(rail_y + 24)}" r="4" fill="{t["ok"]}"/>'
        f'<text class="mono" x="{num(x0 + 16)}" y="{num(rail_y + 28)}" font-size="12" fill="{t["muted"]}">'
        f"main · {n}/{n} stages passed</text></g>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# Toolbelt
# --------------------------------------------------------------------------

TB_W = 1000
ROW_H, CHIP_H, CHIP_GAP = 52, 36, 10
CHIP_X0 = 170
ICON = 18
FONT = 15


def hexagon(cx: float, cy: float, r: float) -> str:
    pts = []
    for k in range(6):
        # Pointy-top hexagon, vertices every 60 degrees from -90.
        a = math.radians(-90 + 60 * k)
        pts.append(f"{num(cx + r * math.cos(a))},{num(cy + r * math.sin(a))}")
    return " ".join(pts)


def toolbelt(cfg: dict, icons: dict, t: dict[str, str]) -> str:
    rows = cfg["toolbelt"]
    height = len(rows) * ROW_H + 4
    names = ", ".join(f'{r["label"]}: ' + ", ".join(i["name"] for i in r["items"]) for r in rows)
    body: list[str] = []
    for r_i, row in enumerate(rows):
        y = 4 + r_i * ROW_H
        body.append(
            f'<text class="mono" x="0" y="{num(y + CHIP_H / 2 + 4)}" font-size="12" letter-spacing="1.5" '
            f'fill="{t["muted"]}">{escape(row["label"].upper())}</text>'
        )
        x = CHIP_X0
        for item in row["items"]:
            label = item["name"]
            w = 14 + ICON + 8 + text_width(label, FONT) + 14
            ix, iy = x + 14, y + (CHIP_H - ICON) / 2
            body.append(
                f'<rect x="{num(x + 0.5)}" y="{num(y + 0.5)}" width="{num(w - 1)}" height="{CHIP_H - 1}" '
                f'rx="{CHIP_H / 2 - 0.5}" fill="{t["chip_fill"]}" stroke="{t["chip_stroke"]}"/>'
            )
            slug = item.get("icon")
            if slug:
                if slug not in icons:
                    raise SystemExit(f"profile.toml: icon {slug!r} for {label!r} is not in assets/icons.json")
                body.append(
                    f'<path transform="translate({num(ix)} {num(iy)}) scale({num(ICON / 24)})" '
                    f'fill="{t["accent"]}" d="{icons[slug]["path"]}"/>'
                )
            else:
                body.append(
                    f'<polygon points="{hexagon(ix + ICON / 2, iy + ICON / 2, 7.5)}" fill="none" '
                    f'stroke="{t["accent"]}" stroke-width="1.6" stroke-linejoin="round"/>'
                )
            body.append(
                f'<text class="sans" x="{num(ix + ICON + 8)}" y="{num(y + CHIP_H / 2 + 5)}" font-size="{FONT}" '
                f'fill="{t["text"]}">{escape(label)}</text>'
            )
            x += w + CHIP_GAP
        if x - CHIP_GAP > TB_W:
            raise SystemExit(f"profile.toml: toolbelt row {row['label']!r} is {num(x - CHIP_GAP)}px wide (max {TB_W})")

    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TB_W}" height="{height}" '
        f'viewBox="0 0 {TB_W} {height}" role="img" aria-labelledby="t">',
        f'<title id="t">Toolbelt — {escape(names)}</title>',
        f"<style>.sans{{font-family:{SANS}}}.mono{{font-family:{MONO}}}</style>",
    ]
    return "\n".join(head + body + ["</svg>"]) + "\n"


# --------------------------------------------------------------------------


def render_all() -> dict[Path, str]:
    cfg = tomllib.loads((ROOT / "profile.toml").read_text(encoding="utf-8"))
    icons = json.loads((ASSETS / "icons.json").read_text(encoding="utf-8"))["icons"]
    out: dict[Path, str] = {}
    for theme, t in THEMES.items():
        out[ASSETS / f"banner-{theme}.svg"] = banner(cfg, t)
        out[ASSETS / f"toolbelt-{theme}.svg"] = toolbelt(cfg, icons, t)
    for path, svg in out.items():
        try:
            ET.fromstring(svg)
        except ET.ParseError as e:
            raise SystemExit(f"{path.name}: generated SVG is not well-formed XML: {e}") from e
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if committed assets are stale")
    args = ap.parse_args()

    stale = []
    for path, svg in render_all().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == svg:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")

    if stale:
        print("Stale assets (run `make assets` and commit):", *stale, sep="\n  ", file=sys.stderr)
        return 1
    if args.check:
        print("assets are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
