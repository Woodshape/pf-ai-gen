#!/usr/bin/env python3
"""Draw tactical 5-ft-grid plans from the hand-drawn Green Rest sketches."""
from html import escape
from pathlib import Path
from weasyprint import HTML

OUT = Path(__file__).resolve().parents[1] / "docs/encounters/embernight"
S = 48  # 5 ft per square
STYLE = """<style>
text{font-family:DejaVu Sans,sans-serif;fill:#24221e}.title{font-size:26px;font-weight:bold}
.room{font-size:15px;font-weight:bold}.small{font-size:11px}.tiny{font-size:9px}
.outer{fill:#f3ead8;stroke:#292724;stroke-width:8}.wall{stroke:#292724;stroke-width:6;fill:none;stroke-linecap:square}
.grid{stroke:#a89f8d;stroke-width:.8;opacity:.48}.furn{fill:#d1b992;stroke:#776047;stroke-width:2}
.fire{fill:#efba82;stroke:#a83d20;stroke-width:3}.door{stroke:#806548;stroke-width:3;fill:none}
</style>"""

def make_svg(level, cols, rows, wall_paths, fires, labels, furniture=(), note="", fire_offset=0, doors=()):
    left, top = 100, 140
    width, height = cols * S, rows * S
    grid = [f'<path class="grid" d="M{left+x*S} {top}V{top+height}"/>' for x in range(1, cols)]
    grid += [f'<path class="grid" d="M{left} {top+y*S}H{left+width}"/>' for y in range(1, rows)]
    walls = ''.join(f'<path class="wall" d="{p}"/>' for p in wall_paths)
    door_marks = ''.join(f'<path class="door" d="{p}"/>' for p in doors)
    fl = ''.join(f'<g><rect class="fire" x="{left+x*S+8}" y="{top+y*S+8}" width="32" height="32"/><text class="small" x="{left+x*S+12}" y="{top+y*S+29}">F{i}</text></g>' for i,(x,y) in enumerate(fires,fire_offset+1))
    labs = ''.join(f'<text class="room" x="{left+x*S}" y="{top+y*S}">{escape(text)}</text>' for x,y,text in labels)
    furn = ''.join(f'<rect class="furn" x="{left+x*S}" y="{top+y*S}" width="{w*S}" height="{h*S}"/>' for x,y,w,h in furniture)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850" role="img" aria-labelledby="green-{level}-title green-{level}-desc">
<title id="green-{level}-title">The Green Rest — {level}</title><desc id="green-{level}-desc">Battlemap des {level} von The Green Rest mit Fünf-Fuß-Raster, Türen, Räumen und markierten Kaminen.</desc>{STYLE}
<rect width="1000" height="760" fill="#faf7ee"/><text x="48" y="48" class="title">THE GREEN REST · {level.upper()}</text>
<text x="48" y="74" class="small">Kampfraster: 1 Feld = 5 ft · Außenmaße aus der Skizze angenähert, nicht vermessen</text>
<text x="{left}" y="112" class="small">OBEN WIE IN DER SKIZZE</text>
<rect class="outer" x="{left}" y="{top}" width="{width}" height="{height}"/>{''.join(grid)}{furn}{walls}{door_marks}{fl}{labs}
<g transform="translate(900 620)"><rect class="fire" width="32" height="32"/><text x="42" y="20" class="small">Kamin / Feuerstelle</text>
<path d="M0 70H96 M0 64V76 M96 64V76" stroke="#292724" stroke-width="2"/><text x="22" y="94" class="small">10 ft</text>
<text x="0" y="140" class="tiny">{escape(note[:34])}</text><text x="0" y="156" class="tiny">Details nach Skizze angenähert.</text></g></svg>'''

# The sketches show a broad, subdivided ground floor, a smaller upper floor,
# and a second level. Walls are redrawn on a 5-ft grid; measurements are approximate.
# Co-ordinates below are grid intersections, not pixels.
plans = {
    "ground": make_svg(
        "Erdgeschoss", 16, 12,
        [
            "M340 140V380 M340 428V716",              # west wing / main room openings
            "M100 284H340 M196 140V236",              # west service rooms
            "M340 332H580 M580 140V332 M580 380V716",# middle-room divisions
            "M580 428H868 M724 428V572 M724 620V716",# public room / east subrooms
            "M868 284V716 M724 572H868",
            # stair and short partitions visible in the sketch
            "M580 524H628 M676 524H724 M628 524V668 M676 524V668",
        ],
        [(4,2),(10,2),(10,8),(14,8)],
        [(1,1,"Nebenraum"),(0,4,"Küche / Service"),(7,1,"Gastraum"),(11,5,"Schankraum")],
        [(1,2,2,1),(7,4,2,1),(12,7,2,1)],
        "Wände, Türlücken, Möbel und F-Positionen nach Erdgeschoss-Skizze übertragen; Details angenähert.",
        doors=("M340 428L388 428", "M580 332L628 332", "M724 620L772 620", "M485 476L533 476"),
    ),
    "first": make_svg(
        "1. Obergeschoss", 8, 14,
        [
            "M292 140V284 M292 332V716",              # central circulation
            "M100 332H292 M340 332H484",              # room doors/gaps
            "M100 476H292 M340 476H484",
            "M100 572H196 M244 572H484",              # stair landing split
            "M196 476V620 M388 332V476 M388 524V716",
            "M292 524H388 M292 668H388",
        ],
        [(3,4)],
        [(0,1,"Zimmer"),(4,1,"Zimmer"),(0,5,"Zimmer"),(5,5,"Zimmer"),(3,10,"Flur / Treppe"),(0,11,"Zimmer"),(5,11,"Zimmer")],
        [(0,2,2,1),(5,2,2,1),(0,7,2,1),(5,7,2,1)],
        "Obergeschoss-Grundriss mit zentraler Erschließung; Außenform und Zimmermaße angenähert.",
        fire_offset=4,
        doors=("M292 332L340 332", "M292 284L340 284", "M292 476L340 476", "M388 476L388 524"),
    ),
    "second": make_svg(
        "2. Obergeschoss", 12, 10,
        [
            "M340 140V284 M436 140V284 M532 140V284",   # upper room partitions
            "M100 284H676 M292 284V428 M484 284V428",
            "M100 428H292 M484 428H676",
            "M292 428V620 M484 428V620",
            "M292 524H340 M388 524H484",               # landing/stair opening
        ],
        [(9,3)],
        [(1,1,"Zimmer"),(5,1,"Zimmer"),(9,1,"Zimmer"),(1,4,"Zimmer"),(9,4,"Zimmer"),(1,8,"Zimmer"),(9,8,"Zimmer"),(7,6,"Flur")],
        [(1,2,2,1),(9,2,2,1),(1,5,2,1),(9,5,2,1),(1,8,2,1),(9,8,2,1)],
        "Zweiter Obergeschoss-Grundriss aus der separaten Skizze; Raummaße angenähert.",
        fire_offset=5,
        doors=("M292 284L340 284", "M436 284L484 284", "M292 428L340 428", "M484 524L532 524"),
    ),
}

for name, svg in plans.items():
    if name != "ground":
        (OUT / f"floorplan-{name}.svg").write_text(svg, encoding="utf-8")
(OUT / "floorplan.svg").write_text(plans["ground"], encoding="utf-8")

# Build a 3-page A4-landscape PDF from the standalone SVGs.
html = '<!doctype html><html lang="de"><meta charset="utf-8"><style>@page{size:A3 landscape;margin:0}html,body{margin:0;padding:0}section{width:420mm;height:297mm;page-break-after:always;display:flex;align-items:center;justify-content:center}section:last-child{page-break-after:auto}img{width:420mm;height:297mm}</style>'
html += ''.join(f'<section><img src="{(OUT / f"floorplan-{name}.svg").as_uri()}"></section>' for name in plans)
html += '</html>'
HTML(string=html, base_url=str(OUT)).write_pdf(OUT / "floorplan.pdf")

# Keep visible fireplace markers tied to the hand-drawn source count.
assert sum(svg.count('class="fire"') - 1 for svg in plans.values()) == 6  # subtract each legend symbol
assert all('<title' in svg and '<desc' in svg for svg in plans.values())
print("wrote three 5-ft-grid SVG battlemaps and the 3-page PDF")
