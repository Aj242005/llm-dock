"""Docking Lab pitch deck engine - funky editorial edition.

Single source of truth: deck_spec.py defines every slide's geometry in 1920x1080
pixels. This module turns that spec into

  1. slides.html      - presentable HTML deck (keyboard nav, fullscreen)
  2. out/art/NN.jpg   - background art layer only (text + pictures hidden)
  3. out/full/NN.png  - composed slide, used for design QA
  4. Docking-Lab-Pitch.pptx - art as background + NATIVE editable text,
                              native picture placements, speaker notes

Two visual worlds share one system:
  paper - warm cream/sage ground, IBM Plex Serif display, colour-block shapes
  space - deep graphite ground, real photography from the project's dashboard

Coordinates are pixels on a 1920x1080 canvas. The PPTX is 13.333 x 7.5 in, so
144 px == 1 inch and 1 pt == 2 px. That single ratio keeps HTML and PPTX aligned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
W, H = 1920, 1080
PX_PER_IN = 144.0
PT_PER_PX = 72.0 / PX_PER_IN

FAMILIES = {"sans": "IBM Plex Sans", "serif": "IBM Plex Serif", "mono": "IBM Plex Mono"}

FONT_FILES = {
    ("sans", 400, False): ROOT / "assets" / "ibm-plex-sans-400.ttf",
    ("sans", 400, True): ROOT / "assets" / "ibm-plex-sans-italic-400.ttf",
    ("sans", 500, False): ROOT / "assets" / "ibm-plex-sans-500.ttf",
    ("sans", 600, False): ROOT / "assets" / "ibm-plex-sans-600.ttf",
    ("sans", 700, False): ROOT / "assets" / "ibm-plex-sans-700.ttf",
    ("serif", 400, False): ROOT / "assets" / "fonts" / "IBMPlexSerif-Regular.ttf",
    ("serif", 400, True): ROOT / "assets" / "fonts" / "IBMPlexSerif-Italic.ttf",
    ("serif", 500, False): ROOT / "assets" / "fonts" / "IBMPlexSerif-Medium.ttf",
    ("serif", 600, False): ROOT / "assets" / "fonts" / "IBMPlexSerif-SemiBold.ttf",
    ("serif", 700, False): ROOT / "assets" / "fonts" / "IBMPlexSerif-Bold.ttf",
    ("mono", 400, False): ROOT / "assets" / "ibm-plex-mono-400.ttf",
    ("mono", 500, False): ROOT / "assets" / "ibm-plex-mono-500.ttf",
}


def font_file(family: str, weight: int, italic: bool = False) -> Path:
    if italic:
        key = (family, 400, True)
        if key in FONT_FILES:
            return FONT_FILES[key]
    for w in (weight, 600, 500, 400):
        key = (family, w, False)
        if key in FONT_FILES:
            return FONT_FILES[key]
    return FONT_FILES[("sans", 400, False)]


# ---------------------------------------------------------------- design tokens
C = {
    # paper world
    "paper": "#F3EEE2",
    "sage": "#D8E1D3",
    "cream2": "#EAE1CE",
    "ink": "#1C241F",
    "ink2": "#3D473E",
    "faint": "#6E7A6D",
    "line": "#C6BFAC",
    "teal": "#1E6F5C",
    "amber": "#E29A2E",
    "coral": "#D8512F",
    "tealTint": "#BDD4C7",
    "amberTint": "#F2D9A9",
    "coralTint": "#F1C3B2",
    "paperOn": "#F3EEE2",
    # space world
    "space": "#0E1519",
    "space2": "#18222A",
    "cream": "#F4F1E8",
    "mint": "#8FD9C4",
    "mutedDark": "#9DB0AB",
    "lineDark": "#2C3A42",
    "amberDark": "#E9A23B",
    "coralDark": "#E4674A",
}


def _st(size, weight, lh, ls, colour, family="sans", italic=False, caps=False):
    return {"size": size, "weight": weight, "lh": lh, "ls": ls, "colour": colour,
            "family": family, "italic": italic, "caps": caps}


# style token -> metrics
S = {
    # sans
    "eyebrow": _st(20, 600, 1.2, 0.15, "teal", caps=True),
    "eyebrowMint": _st(20, 600, 1.2, 0.15, "mint", caps=True),
    "eyebrowCoral": _st(20, 600, 1.2, 0.15, "coral", caps=True),
    "eyebrowCream": _st(20, 600, 1.2, 0.15, "cream", caps=True),
    "mark": _st(17, 500, 1.2, 0.18, "faint", caps=True),
    "markDark": _st(17, 500, 1.2, 0.18, "mutedDark", caps=True),
    "label": _st(19, 600, 1.25, 0.14, "faint", caps=True),
    "labelInk": _st(19, 600, 1.25, 0.14, "ink2", caps=True),
    "labelTeal": _st(19, 600, 1.25, 0.14, "teal", caps=True),
    "labelCream": _st(19, 600, 1.25, 0.14, "cream", caps=True),
    "labelMint": _st(19, 600, 1.25, 0.14, "mint", caps=True),
    "lead": _st(29, 400, 1.48, -0.006, "ink2"),
    "leadDark": _st(29, 400, 1.48, -0.006, "mutedDark"),
    "body": _st(24, 400, 1.58, 0, "ink2"),
    "bodyInk": _st(24, 400, 1.58, 0, "ink"),
    "bodyDark": _st(24, 400, 1.58, 0, "mutedDark"),
    "bodySm": _st(21, 400, 1.5, 0, "ink2"),
    "bodySmDark": _st(21, 400, 1.5, 0, "mutedDark"),
    "bodySmInk": _st(21, 400, 1.5, 0, "ink"),
    "bodySmCream": _st(21, 400, 1.5, 0, "cream"),
    "caption": _st(17, 400, 1.4, 0.02, "faint"),
    "captionDark": _st(17, 400, 1.4, 0.02, "mutedDark"),
    "captionInk": _st(17, 400, 1.4, 0.02, "ink2"),
    "note": _st(19, 400, 1.45, 0, "faint"),
    "noteDark": _st(19, 400, 1.45, 0, "mutedDark"),
    "stat": _st(92, 700, 1.0, -0.03, "ink"),
    "statTeal": _st(92, 700, 1.0, -0.03, "teal"),
    "statCoral": _st(92, 700, 1.0, -0.03, "coral"),
    "statAmber": _st(92, 700, 1.0, -0.03, "amber"),
    "statMint": _st(92, 700, 1.0, -0.03, "mint"),
    "statCream": _st(92, 700, 1.0, -0.03, "cream"),
    "statXl": _st(128, 700, 1.0, -0.035, "cream"),
    "statXlInk": _st(128, 700, 1.0, -0.035, "ink"),
    "statSm": _st(58, 700, 1.02, -0.025, "ink"),
    "statSmTeal": _st(58, 700, 1.02, -0.025, "teal"),
    "statSmCoral": _st(58, 700, 1.02, -0.025, "coral"),
    "statSmMint": _st(58, 700, 1.02, -0.025, "mint"),
    "statSmCream": _st(58, 700, 1.02, -0.025, "cream"),
    "unit": _st(30, 400, 1.0, -0.01, "ink2"),
    "unitDark": _st(30, 400, 1.0, -0.01, "mutedDark"),
    "unitSm": _st(23, 400, 1.0, -0.01, "ink2"),
    "unitSmDark": _st(23, 400, 1.0, -0.01, "mutedDark"),
    "unitSmCream": _st(23, 400, 1.0, -0.01, "cream"),
    "mono": _st(20, 400, 1.5, 0, "ink", family="mono"),
    "monoSm": _st(17, 400, 1.5, 0, "ink2", family="mono"),
    "monoSmDark": _st(17, 400, 1.5, 0, "mutedDark", family="mono"),
    # serif display
    "h1": _st(84, 500, 1.06, -0.018, "ink", family="serif"),
    "h1xl": _st(96, 500, 1.04, -0.022, "ink", family="serif"),
    "h1Dark": _st(84, 500, 1.06, -0.018, "cream", family="serif"),
    "h1xlDark": _st(96, 500, 1.04, -0.022, "cream", family="serif"),
    "h2": _st(54, 500, 1.1, -0.014, "ink", family="serif"),
    "h2Dark": _st(54, 500, 1.1, -0.014, "cream", family="serif"),
    "h3": _st(31, 600, 1.16, -0.01, "ink", family="serif"),
    "h3Teal": _st(31, 600, 1.16, -0.01, "teal", family="serif"),
    "h3Dark": _st(31, 600, 1.16, -0.01, "cream", family="serif"),
    "kicker": _st(32, 400, 1.32, -0.005, "ink2", family="serif", italic=True),
    "kickerDark": _st(32, 400, 1.32, -0.005, "mutedDark", family="serif", italic=True),
    "kickerCoral": _st(32, 400, 1.32, -0.005, "coral", family="serif", italic=True),
    "kickerTeal": _st(32, 400, 1.32, -0.005, "teal", family="serif", italic=True),
    "quote": _st(35, 400, 1.4, -0.008, "cream", family="serif", italic=True),
    "attr": _st(18, 500, 1.4, 0.02, "mutedDark"),
    "chips": _st(18, 600, 1.2, 0.12, "ink", caps=True),
    "chipsCream": _st(18, 600, 1.2, 0.12, "cream", caps=True),
    "chipsTeal": _st(18, 600, 1.2, 0.12, "teal", caps=True),
}


def css() -> str:
    rules = []
    for name, s in S.items():
        rules.append(
            f".s-{name}{{font-size:{s['size']}px;font-weight:{s['weight']};"
            f"line-height:{s['lh']};letter-spacing:{s['ls']}em;color:{C[s['colour']]};"
            f"font-family:'{FAMILIES[s['family']]}',sans-serif;"
            f"{'font-style:italic;' if s['italic'] else ''}"
            f"{'text-transform:uppercase;' if s['caps'] else ''}}}"
        )
    return "\n".join(rules)


FONT_FACES = "\n".join(
    f"@font-face{{font-family:'{FAMILIES[fam]}';font-weight:{w};"
    f"{'font-style:italic;' if it else ''}src:url('{path.relative_to(ROOT).as_posix()}')}}"
    for (fam, w, it), path in FONT_FILES.items()
)

CSS = f"""\
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#0b0f12;font-family:'IBM Plex Sans',sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:geometricPrecision}}
{FONT_FACES}
.deck{{display:flex;flex-direction:column;align-items:center;gap:28px;padding:28px 0}}
.slide{{position:relative;width:{W}px;height:{H}px;overflow:hidden;
  background:{C['paper']};color:{C['ink']};flex:0 0 auto;
  font-variant-numeric:tabular-nums}}
.slide .art{{position:absolute;inset:0}}
.slide .lay{{position:absolute;inset:0}}
.el{{position:absolute;white-space:pre-wrap;word-break:normal;line-height:0;
  transform-origin:center center}}
.plate{{position:absolute;transform-origin:center center}}
.hair{{position:absolute}}
.num{{position:absolute;font-variant-numeric:tabular-nums}}
{css()}
/* presentation shell */
body.app .deck{{display:block;padding:0;gap:0;height:100vh;overflow:hidden}}
body.app .slide{{position:absolute;left:50%;top:50%;transform-origin:center center;
  display:none;box-shadow:0 40px 120px #0006}}
body.app .slide.on{{display:block}}
body.app{{display:grid;place-items:center;height:100vh;overflow:hidden}}
.hint{{position:fixed;right:14px;bottom:10px;color:#8b8578;font-size:12px;
  font-family:'IBM Plex Sans',sans-serif;letter-spacing:.1em;z-index:9}}
body.shot .deck{{padding:0;gap:0}}
body[data-mode="art"] .el,body[data-mode="art"] .pic,body[data-mode="art"] .note{{visibility:hidden}}
"""


# ------------------------------------------------------------------- HTML build
def _rot_style(el: dict) -> str:
    rot = el.get("rot", 0)
    return f"transform:rotate({rot}deg);" if rot else ""


def element_html(el: dict) -> str:
    x, y, w, h = el["box"]
    style = el.get("style", "body")
    align = el.get("align", "left")
    cls = f"el s-{style}"
    inner = []
    for run in el["runs"]:
        txt = run["t"]
        # every run carries its own metrics: the block strut is zeroed below so a
        # large element font can never inflate the height of a small-text line.
        rs = S[run.get("s", style)]
        inner.append(
            f'<span style="font-family:\'{FAMILIES[rs["family"]]}\',sans-serif;'
            f'font-size:{rs["size"]}px;font-weight:{rs["weight"]};line-height:{rs["lh"]};'
            f'letter-spacing:{rs["ls"]}em;color:{C[rs["colour"]]};'
            f'{"font-style:italic;" if rs["italic"] else ""}'
            f'{"text-transform:uppercase;" if rs["caps"] else ""}">{txt}</span>'
        )
    valign = el.get("valign", "top")
    flex = "flex" if valign in ("middle", "bottom") else "block"
    justify = {"middle": "center", "bottom": "flex-end", "top": "flex-start"}[valign]
    return (
        f'<div class="{cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
        f'text-align:{align};display:{flex};flex-direction:column;line-height:0;'
        f'justify-content:{justify};{_rot_style(el)}">{"".join(inner)}</div>'
    )


def plate_html(p: dict) -> str:
    x, y, w, h = p["box"]
    fill = p.get("fill", "cream2")
    op = p.get("opacity", 1)
    radius = p.get("radius", 0)
    extra = ""
    if p.get("border"):
        extra = f"border:1px solid {C[p['border']]};"
    rot = p.get("rot", 0)
    return (
        f'<div class="plate" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
        f'background:{C[fill]};opacity:{op};border-radius:{radius}px;{extra}'
        f'{"transform:rotate(%sdeg);" % rot if rot else ""}"></div>'
    )


def picture_html(p: dict) -> str:
    x, y, w, h = p["box"]
    radius = p.get("radius", 0)
    rot = p.get("rot", 0)
    return (
        f'<img class="pic" src="{p["render"]}" style="position:absolute;left:{x}px;top:{y}px;'
        f'width:{w}px;height:{h}px;object-fit:cover;border-radius:{radius}px;'
        f'{"transform:rotate(%sdeg);" % rot if rot else ""}">'
    )


def slide_html(slide: dict) -> str:
    parts = [f'<section class="slide" id="slide-{slide["id"]}" '
             f'style="background:{C[slide.get("bg", "paper")]}">']
    parts.append(f'<div class="art">{slide.get("art", "")}</div>')
    parts.append('<div class="lay">')
    for plate in slide.get("plates", []):
        parts.append(plate_html(plate))
    for pic in slide.get("pictures", []):
        parts.append(picture_html(pic))
    for el in slide.get("elements", []):
        parts.append(element_html(el))
    parts.append("</div></section>")
    return "\n".join(parts)


def build_html(slides: list[dict]) -> str:
    body = "\n".join(slide_html(s) for s in slides)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Docking Lab - pitch</title>
<link rel="stylesheet" href="slides.css">
</head><body data-mode="full">
<div class="deck">{body}</div>
<div class="hint">arrows / space to advance · f fullscreen</div>
<script src="slides.js"></script>
</body></html>
"""


JS = """
// Presentation shell only. Screenshot runs load the page without ?present so the
// slides stay in plain document flow and element captures line up exactly.
const PRESENT = location.search.includes('present');
const slides=[...document.querySelectorAll('.slide')];
let i=0;
function fit(){
  if(!PRESENT) return;
  const s=Math.min(innerWidth/1920,(innerHeight-0)/1080);
  slides.forEach(el=>{el.style.transform=`translate(-50%,-50%) scale(${s})`;});
}
function show(n){
  if(!PRESENT) return;
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((el,k)=>el.classList.toggle('on',k===i));
  location.hash=String(i+1);
}
if(PRESENT){
document.body.classList.add('app');
addEventListener('resize',fit);
addEventListener('keydown',e=>{
  if(['ArrowRight','ArrowDown',' ','PageDown','n'].includes(e.key)){show(i+1);e.preventDefault();}
  if(['ArrowLeft','ArrowUp','PageUp','p'].includes(e.key)){show(i-1);e.preventDefault();}
  if(e.key==='f'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}
  if(e.key==='Home'){show(0);} if(e.key==='End'){show(slides.length-1);}
});
fit();
show((parseInt(location.hash.replace('#',''))||1)-1);
}
"""


# --------------------------------------------------------------------- rendering
def prepare_pictures(slides: list[dict]) -> None:
    """Crop each evidence image to its placement aspect ratio, once, so the HTML
    and the PPTX frame the plate identically."""
    img_dir = OUT / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    for si, slide in enumerate(slides):
        for pi, pic in enumerate(slide.get("pictures", [])):
            x, y, w, h = pic["box"]
            target = w / h
            src = ROOT / pic["src"]
            im = Image.open(src).convert("RGB")
            sw, sh = im.size
            if abs(sw / sh - target) > 0.002:
                if pic.get("fit", "cover") == "cover":
                    if sw / sh > target:
                        nw = int(round(sh * target))
                        left = int((sw - nw) * pic.get("focusX", 0.5))
                        im = im.crop((left, 0, left + nw, sh))
                    else:
                        nh = int(round(sw / target))
                        top = int((sh - nh) * pic.get("focusY", 0.5))
                        im = im.crop((0, top, sw, top + nh))
                else:
                    # contain: letterbox onto the pad colour so the placed image
                    # already matches the box aspect and never distorts.
                    pad_hex = C[pic.get("pad", "paper")].lstrip("#")
                    bg = tuple(int(pad_hex[i:i + 2], 16) for i in (0, 2, 4))
                    canvas = Image.new("RGB", (int(w * 2), int(h * 2)), bg)
                    scale = min(canvas.width / sw, canvas.height / sh)
                    fitted = im.resize((max(1, int(sw * scale)), max(1, int(sh * scale))),
                                       Image.LANCZOS)
                    canvas.paste(fitted, ((canvas.width - fitted.width) // 2,
                                          (canvas.height - fitted.height) // 2))
                    im = canvas
            name = f"{si:02d}-{pi}-{Path(pic['src']).stem}.jpg"
            im.save(img_dir / name, quality=94, subsampling=0)
            pic["render"] = f"out/img/{name}"
    return


OVERFLOW_JS = """
() => {
  const out = [];
  document.querySelectorAll('.slide').forEach((s) => {
    s.querySelectorAll('.el').forEach((e, ei) => {
      const dh = e.scrollHeight - e.clientHeight;
      const dw = e.scrollWidth - e.clientWidth;
      if (dh > 10 || dw > 2) out.push(`${s.id} el#${ei} +${dh}h +${dw}w :: ${e.textContent.slice(0, 46)}`);
    });
  });
  return out;
}
"""


def render(slides: list[dict], dsf: float = 2.0) -> list[str]:
    """Render art + composed layers, and measure text overflow in the real layout."""
    from playwright.sync_api import sync_playwright

    (OUT / "art").mkdir(parents=True, exist_ok=True)
    (OUT / "full").mkdir(parents=True, exist_ok=True)
    url = (ROOT / "slides.html").as_uri()
    overflows: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=dsf)
        page.goto(url)
        page.wait_for_function("document.fonts.status === 'loaded'")
        page.wait_for_timeout(600)
        overflows = page.evaluate(OVERFLOW_JS)
        for mode in ("art", "full"):
            page.evaluate(f"document.body.dataset.mode = '{mode}'")
            page.wait_for_timeout(150)
            for i, slide in enumerate(slides):
                el = page.locator(f"#slide-{slide['id']}")
                dest = OUT / mode / f"{i + 1:02d}-{slide['id']}.png"
                el.screenshot(path=str(dest))
        browser.close()
    return overflows


def downsample_art() -> None:
    """Art layer ships as q92 JPEG at 1920x1080 - photos need no transparency and
    the PPTX stays small enough for a clean Adobe Express import."""
    for png in sorted((OUT / "art").glob("*.png")):
        im = Image.open(png).convert("RGB").resize((W, H), Image.LANCZOS)
        im.save(png.with_suffix(".jpg"), quality=92, subsampling=0)
        png.unlink()


# ------------------------------------------------------------------- pptx write
def _emu(px: float) -> int:
    return int(round(px / PX_PER_IN * 914400))


def _set_alpha(shape, opacity: float) -> None:
    """python-pptx has no fill-transparency API, so write the alpha element directly."""
    if opacity >= 0.999:
        return
    from lxml import etree
    from pptx.oxml.ns import qn

    solid = shape._element.spPr.find(qn("a:solidFill"))
    if solid is None:
        return
    clr = solid.find(qn("a:srgbClr"))
    if clr is None:
        return
    alpha = etree.SubElement(clr, qn("a:alpha"))
    alpha.set("val", str(int(round(opacity * 100000))))


def write_pptx(slides: list[dict], path: Path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Pt

    prs = Presentation()
    prs.slide_width = Emu(_emu(W))
    prs.slide_height = Emu(_emu(H))
    blank = prs.slide_layouts[6]

    align_map = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
    anchor_map = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}

    for si, spec in enumerate(slides):
        slide = prs.slides.add_slide(blank)

        # 1. background art layer
        art = OUT / "art" / f"{si + 1:02d}-{spec['id']}.jpg"
        pic = slide.shapes.add_picture(str(art), 0, 0, Emu(_emu(W)), Emu(_emu(H)))
        pic.name = f"art-{spec['id']}"

        # 2. plates (cards, panels, chips)
        for pi, p in enumerate(spec.get("plates", [])):
            x, y, w, h = p["box"]
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE if p.get("radius") else MSO_SHAPE.RECTANGLE,
                Emu(_emu(x)), Emu(_emu(y)), Emu(_emu(w)), Emu(_emu(h)),
            )
            if p.get("radius"):
                shape.adjustments[0] = min(0.5, p["radius"] / min(w, h))
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(C[p.get("fill", "cream2")][1:])
            _set_alpha(shape, p.get("opacity", 1))
            if p.get("border"):
                shape.line.color.rgb = RGBColor.from_string(C[p["border"]][1:])
                shape.line.width = Pt(0.75)
            else:
                shape.line.fill.background()
            shape.shadow.inherit = False
            shape.text_frame.text = ""
            if p.get("rot"):
                shape.rotation = p["rot"]
            shape.name = f"plate-{spec['id']}-{pi}"

        # 3. evidence pictures
        for pi, p in enumerate(spec.get("pictures", [])):
            x, y, w, h = p["box"]
            img = ROOT / p["render"]
            shape = slide.shapes.add_picture(str(img), Emu(_emu(x)), Emu(_emu(y)),
                                             Emu(_emu(w)), Emu(_emu(h)))
            if p.get("rot"):
                shape.rotation = p["rot"]
            shape.name = f"img-{spec['id']}-{pi}"

        # 4. native, editable text
        for ei, el in enumerate(spec.get("elements", [])):
            x, y, w, h = el["box"]
            box = slide.shapes.add_textbox(Emu(_emu(x)), Emu(_emu(y)), Emu(_emu(w)), Emu(_emu(h)))
            if el.get("rot"):
                box.rotation = el["rot"]
            box.name = f"txt-{spec['id']}-{ei}"
            tf = box.text_frame
            tf.word_wrap = el.get("wrap", True)
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = anchor_map[el.get("valign", "top")]
            first = True
            for run in el["runs"]:
                rs = S[run.get("s", el.get("style", "body"))]
                size, weight, lh, ls = rs["size"], rs["weight"], rs["lh"], rs["ls"]
                for li, line in enumerate(run["t"].split("\n")):
                    para = tf.paragraphs[0] if (first and li == 0) else tf.add_paragraph()
                    first = False
                    para.alignment = align_map[el.get("align", "left")]
                    para.line_spacing = lh
                    para.space_after = Pt(0)
                    piece = para.add_run()
                    text = line.upper() if rs.get("caps") else line
                    piece.text = text
                    piece.font.size = Pt(round(size * PT_PER_PX, 1))
                    piece.font.bold = weight >= 600
                    piece.font.italic = rs.get("italic", False)
                    piece.font.name = FAMILIES[rs["family"]]
                    piece.font.color.rgb = RGBColor.from_string(C[rs["colour"]][1:])
                    if abs(ls) > 1e-9:
                        rPr = piece._r.get_or_add_rPr()
                        rPr.set("spc", str(int(round(ls * size * PT_PER_PX * 100))))

        if spec.get("notes"):
            slide.notes_slide.notes_text_frame.text = spec["notes"]

    prs.save(str(path))


# --------------------------------------------------------------- fit assertions
def check_fit(slides: list[dict]) -> list[str]:
    """Guard against text that would overflow its box in PowerPoint: measure the
    real Plex metrics, wrapping across runs the way a single paragraph does
    (a stat and its unit share one line, not two)."""
    problems = []
    cache: dict[tuple, ImageFont.FreeTypeFont] = {}
    for si, spec in enumerate(slides):
        for ei, el in enumerate(spec.get("elements", [])):
            x, y, w, h = el["box"]
            # flatten runs into word tokens carrying their own metrics
            tokens = []  # (text, font, track, size, lh, is_break)
            for run in el["runs"]:
                rs = S[run.get("s", el.get("style", "body"))]
                size, weight, lh, ls = rs["size"], rs["weight"], rs["lh"], rs["ls"]
                key = (rs["family"], size, weight, rs.get("italic", False))
                if key not in cache:
                    cache[key] = ImageFont.truetype(
                        str(font_file(rs["family"], weight, rs.get("italic", False))), size)
                font, track = cache[key], ls * size
                parts = run["t"].split("\n")
                for pi, part in enumerate(parts):
                    if pi > 0:
                        tokens.append((None, font, track, size, lh, "hard"))
                    for word in part.split(" "):
                        tokens.append((word, font, track, size, lh, None))
            # wrap: a line closes when the next token no longer fits
            total_h = 0.0
            line_w = 0.0
            line_h = 0.0
            pending = 0.0  # width of the space that precedes the next word
            for text, font, track, size, lh, kind in tokens:
                if kind == "hard":
                    total_h += max(line_h, size * lh)
                    line_w, line_h, pending = 0.0, 0.0, 0.0
                    continue
                if text == "":
                    pending = 0.0
                    continue
                word_w = font.getlength(text) + max(0, len(text) - 1) * track
                if line_w > 0 and line_w + pending + word_w > w:
                    total_h += line_h
                    line_w, line_h, pending = 0.0, 0.0, 0.0
                line_w += pending + word_w
                line_h = max(line_h, size * lh)
                pending = track + font.getlength(" ")
            total_h += line_h
            if total_h > h + 2:
                problems.append(
                    f"slide {si + 1} ({spec['id']}) element {ei}: needs {total_h:.0f}px, box is {h}px"
                )
    return problems


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import deck_spec

    slides = deck_spec.SLIDES
    OUT.mkdir(exist_ok=True)
    prepare_pictures(slides)
    (ROOT / "slides.html").write_text(build_html(slides), encoding="utf-8")
    (ROOT / "slides.css").write_text(CSS, encoding="utf-8")
    (ROOT / "slides.js").write_text(JS, encoding="utf-8")
    problems = render(slides)
    downsample_art()

    pptx = ROOT / "Docking-Lab-Pitch.pptx"
    write_pptx(slides, pptx)

    report = {
        "slides": len(slides),
        "pptx": str(pptx.relative_to(ROOT.parent)),
        "pptx_mb": round(pptx.stat().st_size / 1e6, 1),
        "overflow": problems,
    }
    (OUT / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
