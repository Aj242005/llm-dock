"""Docking Lab - investor pitch. One spec drives the HTML deck and the PPTX.

Every figure traces to a file under proofs/ or src/. Nothing is rounded up and
nothing is illustrative. Copy is written for investors and a general audience:
a plain-language claim first, the number that proves it second, the artifact
third, the limit always stated.

Design language: funky editorial. Two worlds on one system -
  paper  warm cream / sage ground, IBM Plex Serif display, colour-block cards,
         sticker chips with a degree of tilt
  space  deep graphite ground, real photography from the project's own
         dashboard, mint accents

Layout contract (1920x1080 px canvas):
  eyebrow row 76-104 · hairline 130 · title band 210-400 · content 400-980
  footer row 1004-1032
"""

from __future__ import annotations

TOTAL = 16
M = 104
CW = 1712
FOOT = 1004


# --------------------------------------------------------------------- builders
def r(t: str, s: str | None = None) -> dict:
    return {"t": t} if s is None else {"t": t, "s": s}


def txt(box, runs, style="body", align="left", valign="top", rot=0, wrap=True) -> dict:
    d = {"box": list(box), "runs": runs, "style": style, "align": align,
         "valign": valign, "wrap": wrap}
    if rot:
        d["rot"] = rot
    return d


def plate(box, fill="cream2", opacity=1.0, border=None, radius=0, rot=0) -> dict:
    d = {"box": list(box), "fill": fill, "opacity": opacity, "border": border,
         "radius": radius}
    if rot:
        d["rot"] = rot
    return d


def pic(src, box, fit="cover", focusY=0.5, focusX=0.5, pad="paper", radius=0) -> dict:
    return {"src": src, "box": list(box), "fit": fit, "focusY": focusY,
            "focusX": focusX, "pad": pad, "radius": radius}


# -------------------------------------------------------------- art primitives
COL = {"paper": "#F3EEE2", "sage": "#D8E1D3", "cream2": "#EAE1CE", "ink": "#1C241F",
       "teal": "#1E6F5C", "amber": "#E29A2E", "coral": "#D8512F", "space": "#0E1519",
       "mint": "#8FD9C4", "cream": "#F4F1E8", "line": "#C6BFAC", "lineDark": "#2C3A42",
       "tealTint": "#BDD4C7", "amberTint": "#F2D9A9", "coralTint": "#F1C3B2"}


def rule(box, colour="ink", opacity=1.0) -> str:
    x, y, w, h = box
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{COL[colour]};opacity:{opacity}"></div>')


def hair(box, colour="line", opacity=1.0) -> str:
    return rule(box, colour, opacity)


def disc(cx, cy, r_, colour, opacity=1.0) -> str:
    return (f'<div style="position:absolute;left:{cx - r_}px;top:{cy - r_}px;'
            f'width:{r_ * 2}px;height:{r_ * 2}px;border-radius:50%;background:{COL[colour]};'
            f'opacity:{opacity}"></div>')


def ring(cx, cy, r_, colour, thick=3, opacity=1.0) -> str:
    return (f'<div style="position:absolute;left:{cx - r_}px;top:{cy - r_}px;'
            f'width:{r_ * 2}px;height:{r_ * 2}px;border-radius:50%;'
            f'border:{thick}px solid {COL[colour]};opacity:{opacity}"></div>')


def quarter(x, y, size, colour, corner="tl", opacity=1.0) -> str:
    radii = {"tl": "100% 0 0 0", "tr": "0 100% 0 0", "br": "0 0 100% 0",
             "bl": "0 0 0 100%"}
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{size}px;'
            f'height:{size}px;border-radius:{radii[corner]};background:{COL[colour]};'
            f'opacity:{opacity}"></div>')


def half_disc(cx, cy, r_, colour, side="top", opacity=1.0) -> str:
    radii = {"top": "100% 100% 0 0", "bottom": "0 0 100% 100%",
             "left": "100% 0 0 100%", "right": "0 100% 100% 0"}
    return (f'<div style="position:absolute;left:{cx - r_}px;top:{cy - r_}px;'
            f'width:{r_ * 2}px;height:{r_ * 2}px;border-radius:{radii[side]};'
            f'background:{COL[colour]};opacity:{opacity}"></div>')


def bars(box, colour, n=4, thickness=14, gap=26, vertical=True, opacity=1.0) -> str:
    x, y, w, h = box
    out = []
    for i in range(n):
        if vertical:
            bx, by, bw, bh = x + i * (thickness + gap), y, thickness, h
        else:
            bx, by, bw, bh = x, y + i * (thickness + gap), w, thickness
        out.append(rule((bx, by, bw, bh), colour, opacity))
    return "".join(out)


def plus(cx, cy, size, thick, colour, opacity=1.0) -> str:
    return (rule((cx - size // 2, cy - thick // 2, size, thick), colour, opacity)
            + rule((cx - thick // 2, cy - size // 2, thick, size), colour, opacity))


def dots(x, y, w, h, step=26, rad=4, colour="#1C241F", opacity=0.25) -> str:
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background-image:radial-gradient({colour} {rad}px,transparent {rad + 1}px);'
            f'background-size:{step}px {step}px;opacity:{opacity}"></div>')


def photo(src, box, focus="50% 50%", extra="") -> str:
    x, y, w, h = box
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background-image:url({src});background-size:cover;'
            f'background-position:{focus};{extra}"></div>')


def scrim(x, y, w, h, direction, stops) -> str:
    body = ",".join(f"{c} {p}%" for p, c in stops)
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:linear-gradient({direction},{body})"></div>')


def grid_art(x, y, w, h, step=96, opacity=0.5, colour="rgba(28,36,31,.16)") -> str:
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background-image:repeating-linear-gradient(to right,{colour} 0 1px,transparent 1px {step}px),'
            f'repeating-linear-gradient(to bottom,{colour} 0 1px,transparent 1px {step}px);'
            f'opacity:{opacity}"></div>')


def bigquote(x, y, colour="amber", size=300) -> str:
    """Giant serif quotation mark, baked into the art layer."""
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;font-family:\'IBM Plex Serif\',serif;'
            f'font-size:{size}px;line-height:.72;color:{COL[colour]};">“</div>')


# ------------------------------------------------------------------ components
def chip(box, label, fill="ink", text_style="chipsCream", rot=0, align="center") -> list:
    """Sticker chip: rounded plate + caps label centred inside."""
    x, y, w, h = box
    return [plate(box, fill, 1, radius=h // 2, rot=rot),
            txt((x + 22, y, w - 44, h), [r(label, text_style)], text_style,
                align=align, valign="middle", rot=rot)]


def stat_block(x, y, number, unit, caption, w=330, num_style="statTeal",
               unit_style="unit", cap_style="caption") -> list:
    return [txt((x, y, w, 108), [r(number, num_style), r(" " + unit, unit_style)],
                num_style),
            txt((x, y + 74, w, 60), [r(caption, cap_style)], cap_style)]


def stat_block_dark(x, number, unit, caption, w=420) -> list:
    """Huge stat on the space world: XL number + small unit + mint label."""
    return [txt((x, 340, w, 140), [r(number, "statXl"), r(" " + unit, "unitSmDark")],
                "statXl"),
            txt((x, 470, w, 34), [r(caption, "labelMint")], "labelMint")]


def chrome(num, eyebrow, source=None, dark=False) -> tuple[list, list]:
    if dark:
        art = [rule((M, 52, 56, 5), "mint")]
        els = [txt((M, 76, 1200, 34), [r(eyebrow)], "eyebrowMint"),
               txt((1100, 76, CW - 996, 34), [r("Docking Lab · investor brief")],
                   "markDark", align="right")]
        art.append(hair((M, 130, CW, 1), "lineDark"))
        if source:
            els.append(txt((M, FOOT, 1500, 30), [r(source)], "captionDark"))
        els.append(txt((1516, FOOT - 6, 300, 34),
                       [r(f"{num:02d}", "markDark"), r(f"  /  {TOTAL}", "markDark")],
                       "markDark", align="right"))
    else:
        art = [rule((M, 52, 56, 5), "coral")]
        els = [txt((M, 76, 1200, 34), [r(eyebrow)], "eyebrow"),
               txt((1100, 76, CW - 996, 34), [r("Docking Lab · investor brief")],
                   "mark", align="right")]
        art.append(hair((M, 130, CW, 1), "line"))
        if source:
            els.append(txt((M, FOOT, 1500, 30), [r(source)], "caption"))
        els.append(txt((1516, FOOT - 6, 300, 34),
                       [r(f"{num:02d}", "mark"), r(f"  /  {TOTAL}", "mark")],
                       "mark", align="right"))
    return art, els


SLIDES: list[dict] = []


def add(sid, num, eyebrow, bg, art, plates, pictures, elements, notes,
        source=None, dark=False):
    extra_art, extra_els = chrome(num, eyebrow, source, dark)
    SLIDES.append({"id": sid, "bg": bg,
                   "art": "".join(list(art) + extra_art),
                   "plates": list(plates), "pictures": list(pictures),
                   "elements": extra_els + list(elements), "notes": notes})


# ============================================================== 01 cover
add("cover", 1, "Docking Lab · October 2026", "paper",
    art=[
        # right-hand sage panel with an arch photo, like a magazine cover
        rule((1064, 0, 856, 1080), "sage"),
        photo("assets/hero-station.jpg", (1160, 120, 620, 830),
              focus="56% 42%", extra="border-radius:310px 310px 14px 14px;"),
        disc(1790, 210, 96, "amber"),
        ring(1120, 900, 58, "coral", 10),
        # colour-block accents on the paper side
        quarter(1064, 0, 160, "teal", "br"),
        plus(948, 196, 44, 10, "coral"),
        dots(104, 152, 300, 64, 26, 4, "#1C241F", 0.18),
    ],
    plates=[],
    pictures=[],
    elements=[
        txt((M, 236, 900, 420),
            [r("A spacecraft that\ndocks itself.\nAnd shows its work.", "h1xl")], "h1xl"),
        txt((M, 668, 860, 200),
            [r("An LLM plans the manoeuvre, a learned policy advises it, and an "
               "independent safety channel gates every command — over real orbital "
               "dynamics, in one dashboard.", "kicker")], "kicker"),
        txt((M, 852, 400, 30), [r("THE LAST RECORDED RUN", "labelTeal")], "labelTeal"),
        *stat_block(M, 890, "1.945", "cm", "final port separation", 300, "statTeal"),
        *stat_block(424, 890, "0.004", "m/s", "relative speed at capture", 320, "statCoral"),
        *stat_block(778, 890, "0", "fallbacks", "two provider decisions, both applied",
                    260, "stat"),
    ],
    notes=("Open on the button: this is a working system, not a concept video.\n"
           "Say in one breath: an LLM, a learned policy and an independent safety "
           "channel fly a 500 kg chaser from 100 metres to a centimetre-class "
           "capture — and every claim in this deck traces to a file.\n"
           "Numbers on screen: 1.945 cm, 0.004 m/s, zero fallbacks — "
           "proofs/precision-vertex-docking/checks.json."),
    source="cover capture · this project's own dashboard, 100 m approach",
)

# ============================================================== 02 problem
add("problem", 2, "The problem", "sage",
    art=[
        plus(1806, 208, 40, 9, "amber"),
        quarter(1824, 940, 96, "coral", "tl", 0.9),
        dots(104, 760, 260, 170, 26, 4, "#1C241F", 0.2),
    ],
    plates=[plate((1120, 210, 700, 232), "paper", 1, radius=20),
            plate((1120, 466, 700, 232), "paper", 1, radius=20),
            plate((1120, 722, 700, 232), "paper", 1, radius=20)],
    pictures=[],
    elements=[
        txt((M, 214, 940, 200), [r("The final 100 metres\ndecide the mission.", "h1")], "h1"),
        txt((M, 430, 880, 170),
            [r("Rendezvous is unforgiving: close on a moving target, null your "
               "motion down to centimetres, and touch down softly enough to latch.",
               "lead")], "lead"),
        txt((M, 640, 400, 120), [r("0.005", "statCoral"), r(" m/s", "unit")], "statCoral"),
        txt((M, 742, 640, 120),
            [r("the permitted capture speed at the shared gate — every method, "
               "human or learned, is judged against the same number.", "bodySm")],
            "bodySm"),
        txt((1160, 246, 620, 44), [r("One controller per target", "h3")], "h3"),
        txt((1160, 298, 620, 120),
            [r("A new vehicle or a new port means another hand-tuned control law "
               "and another test campaign.", "bodySm")], "bodySm"),
        txt((1160, 502, 620, 44), [r("Rehearsal is scarce", "h3")], "h3"),
        txt((1160, 554, 620, 120),
            [r("On-orbit proximity rehearsal is expensive and rare; ground rigs "
               "cannot reproduce contact dynamics or sensor dropouts.", "bodySm")],
            "bodySm"),
        txt((1160, 758, 620, 44), [r("Autonomy nobody can question", "h3")], "h3"),
        txt((1160, 810, 620, 120),
            [r("A planner a reviewer cannot interrogate cannot be signed off — the "
               "capability stalls at the demo stage.", "bodySm")], "bodySm"),
    ],
    notes=("Frame the pain in plain terms: proximity operations carry the mission "
           "risk, every new target restarts the control-law and verification "
           "campaign, and autonomy that cannot explain itself never gets certified.\n"
           "The 0.005 m/s figure is this simulator's shared capture gate "
           "(src/app/simulation/safety.py) — present it as the class of tolerance, "
           "not as an ISS requirement."),
    source="gate defaults · src/app/simulation/safety.py",
)

# ============================================================== 03 why now
add("why-now", 3, "Why now", "paper",
    art=[
        half_disc(1560, 150, 120, "sage", "bottom"),
        quarter(0, 968, 220, "amber", "tr", 0.9),
        plus(1836, 940, 40, 9, "teal"),
    ],
    plates=[plate((M, 470, 544, 500), "teal", 1, radius=26),
            plate((688, 470, 544, 500), "amber", 1, radius=26),
            plate((1272, 470, 544, 500), "coral", 1, radius=26)],
    pictures=[],
    elements=[
        txt((M, 214, 1600, 110), [r("Three things got cheap — all at once.", "h1")], "h1"),
        txt((M, 348, 1240, 120),
            [r("The bottleneck moved. Planning, advice and verification are now "
               "implementable in one week of engineering time.", "kicker")], "kicker"),
        txt((M + 40, 512, 464, 60), [r("01", "h2Dark")], "h2Dark"),
        txt((M + 40, 586, 464, 50), [r("Tool-using models", "h3Dark")], "h3Dark"),
        txt((M + 40, 648, 464, 280),
            [r("The planner calls measurement tools, previews a manoeuvre before "
               "submitting it, and records the alternatives it rejected. "
               "Interrogable, not a black box.", "bodySmDark")], "bodySmDark"),
        txt((728, 586, 464, 50), [r("Learned advice on a budget", "h3Dark")], "h3Dark"),
        txt((728, 512, 464, 60), [r("02", "h2Dark")], "h2Dark"),
        txt((728, 648, 464, 280),
            [r("An expert-initialized PPO policy trains to 200,704 environment "
               "steps on two T4 GPUs and is evaluated on held-out seeds. It "
               "advises; it never actuates.", "bodySmDark")], "bodySmDark"),
        txt((1312, 512, 464, 60), [r("03", "h2Dark")], "h2Dark"),
        txt((1312, 586, 464, 50), [r("Evidence-first engineering", "h3Dark")], "h3Dark"),
        txt((1312, 648, 464, 280),
            [r("Every run exports configuration, decisions, tool readings, "
               "telemetry and SHA-256 hashes — a reviewer re-derives each number "
               "instead of trusting a slide.", "bodySmDark")], "bodySmDark"),
    ],
    notes=("The 'why now': the pieces are individually unremarkable, the "
           "composition is new.\n"
           "Each card cites its artifact — the tool loop in src/app/llm/tools.py, "
           "PPO evidence in proofs/kaggle-final-seed-42/, exports in "
           "proofs/precision-vertex-docking/."),
    source="planning · src/app/llm/reasoning_agent.py · src/app/llm/tools.py",
)

# ============================================================== 04 system
add("system", 4, "The system", "sage",
    art=[
        rule((640, 300, 1, 520), "line"),
        rule((1240, 300, 1, 520), "line"),
        disc(1810, 190, 40, "amber"),
        quarter(1824, 980, 96, "coral", "tl"),
    ],
    plates=[plate((M, 840, CW, 132), "teal", 1, radius=18)],
    pictures=[],
    elements=[
        txt((M, 214, 1300, 110), [r("One dashboard. One closed loop.", "h1")], "h1"),
        txt((M + 34, 330, 300, 34), [r("Plan", "labelTeal")], "labelTeal"),
        txt((M + 34, 370, 470, 56), [r("A planner with six tools", "h3")], "h3"),
        txt((M + 34, 440, 470, 370),
            [r("A LangChain planner calls six inspection and submission tools. "
               "Vertex AI by default; OpenAI, Groq, OpenRouter and Anthropic "
               "selectable.\n\nIt measures, checks the gate, previews the "
               "manoeuvre, then submits — with a rationale.", "bodySm")], "bodySm"),
        txt((674, 330, 300, 34), [r("Advise", "labelTeal")], "labelTeal"),
        txt((674, 370, 520, 56), [r("A policy that suggests", "h3")], "h3"),
        txt((674, 440, 520, 370),
            [r("An expert-initialized PPO advisor supplies a learned proposal — "
               "a 4-second lookahead closing vector.\n\nThe planner may adopt it, "
               "cap it or reject it, and every decision records which, with a "
               "reason.", "bodySm")], "bodySm"),
        txt((1274, 330, 300, 34), [r("Fly", "labelTeal")], "labelTeal"),
        txt((1274, 370, 500, 56), [r("A controller that never guesses", "h3")], "h3"),
        txt((1274, 440, 500, 370),
            [r("An LQR controller tracks the accepted target continuously, under "
               "per-axis force, torque, acceleration and stopping-distance "
               "envelopes on a 500 kg chaser.\n\nPhysics never waits for the "
               "planner — it keeps stepping while guidance is pending.", "bodySm")],
            "bodySm"),
        txt((M + 36, 862, 500, 34), [r("And underneath everything", "labelCream")],
            "labelCream"),
        txt((M + 36, 898, 1600, 68),
            [r("An independent safety channel reads simulator truth, enforces the "
               "motion and capture gates, and performs fault braking — surviving "
               "provider loss and stale sensor data.", "bodySmCream")], "bodySmCream"),
    ],
    notes=("Walk left to right: plan, advise, fly — then the band underneath.\n"
           "The architectural claim for a technical reviewer: deterministic physics "
           "and safety sit outside the planner, so provider latency or failure "
           "cannot corrupt the state.\n"
           "Sources: src/app/simulation/runner.py, dynamics.py, safety.py, "
           "src/app/llm/reasoning_agent.py, tools.py."),
    source="architecture · src/app/simulation/runner.py · src/app/llm/tools.py",
)

# ============================================================== 05 lanes
add("lanes", 5, "Control architecture", "paper",
    art=[
        rule((M + 30, 380, 4, 480), "ink", 0.9),
        dots(1640, 170, 200, 80, 26, 4, "#1C241F", 0.2),
        plus(1852, 966, 36, 8, "amber"),
        disc(M + 32, 470, 30, "teal"),
        disc(M + 32, 614, 30, "amber"),
        disc(M + 32, 758, 30, "coral"),
        disc(M + 32, 902, 30, "ink"),
    ],
    plates=[],
    pictures=[],
    elements=[
        txt((M, 214, CW, 110), [r("Nothing flies unchallenged.", "h1")],
            "h1"),
        txt((M, 344, 1240, 44), [r("Four lanes. Only the first two can be wrong.", "kicker")],
            "kicker"),
        # 01
        txt((M + 6, 446, 60, 50), [r("1", "h3Dark")], "h3Dark", align="center"),
        txt((M + 96, 436, 260, 40), [r("Planner", "labelInk")], "labelInk"),
        txt((M + 96, 470, 1180, 96),
            [r("An LLM over a six-tool loop: measure distance, inspect the capture "
               "gate, inspect actuators, read the learned proposal, preview a "
               "manoeuvre, submit — returning targets, a rationale and the "
               "alternatives it rejected.", "bodySm")], "bodySm"),
        txt((1500, 448, 320, 70), [r("Vertex AI by default\nfour providers selectable",
                                     "caption")], "caption"),
        # 02
        txt((M + 6, 590, 60, 50), [r("2", "h3Dark")], "h3Dark", align="center"),
        txt((M + 96, 580, 260, 40), [r("Advisor", "labelInk")], "labelInk"),
        txt((M + 96, 614, 1180, 96),
            [r("Expert-initialized PPO proposes a 4 s lookahead closing vector. The "
               "planner may adopt it, cap it or reject it — every decision records "
               "which, with a reason.", "bodySm")], "bodySm"),
        txt((1500, 592, 320, 70), [r("advice, never authority", "caption")], "caption"),
        # 03
        txt((M + 6, 734, 60, 50), [r("3", "h3Dark")], "h3Dark", align="center"),
        txt((M + 96, 724, 260, 40), [r("Executor", "labelInk")], "labelInk"),
        txt((M + 96, 758, 1180, 96),
            [r("LQR tracking under per-axis force and torque, total thrust, "
               "acceleration and stopping-distance envelopes on a 500 kg chaser: "
               "50 N total, 20 N·m per axis, 0.1 m/s² local acceleration.",
               "bodySm")], "bodySm"),
        txt((1500, 736, 320, 70), [r("propellant follows\napplied impulse", "caption")],
            "caption"),
        # 04
        txt((M + 6, 878, 60, 50), [r("4", "h3Dark")], "h3Dark", align="center"),
        txt((M + 96, 868, 300, 40), [r("Safety channel", "labelInk")], "labelInk"),
        txt((M + 96, 902, 1180, 96),
            [r("Independent of the planner and the policy. It reads simulator "
               "truth, enforces the motion and capture gates, discards expired "
               "plans and labels the recovery manoeuvre.", "bodySm")], "bodySm"),
        txt((1500, 880, 320, 70), [r("survives provider loss\nand stale sensor data",
                                     "caption")], "caption"),
        txt((M, 962, 1400, 40),
            [r("In the recorded run, accepted decisions carried 24.4 s and 22.6 s "
               "plan age while the simulation kept advancing.", "note")], "note"),
    ],
    notes=("The line for engineers: only lanes 01 and 02 can be wrong, and neither "
           "can actuate anything directly.\n"
           "Provider failure produces labelled deterministic guidance, never "
           "silence.\n"
           "Numbers: 50 N, 20 N·m, 0.1 m/s², 500 kg; plan ages 24.4 s and 22.6 s "
           "from proofs/precision-vertex-docking/decisions.json."),
    source="lanes · src/app/simulation/runner.py · src/app/llm/rl_advisor.py",
)

# ============================================================== 06 trace
add("trace", 6, "Live trace", "space",
    art=[
        bigquote(96, 372, "amber", 300),
        quarter(1824, 0, 96, "teal", "bl", 0.9),
        dots(1620, 860, 200, 110, 26, 3, "#8FD9C4", 0.3),
    ],
    plates=[plate((240, 420, 1000, 208), "space2", 1, radius=18),
            plate((240, 660, 1000, 176), "space2", 1, radius=18)],
    pictures=[],
    elements=[
        txt((M, 214, 1100, 200), [r("It argued with its own advisor — and won.", "h1Dark")],
            "h1Dark"),
        txt((276, 452, 930, 150),
            [r("“Adopt the RL short-horizon waypoint at 0.65 m/s: rejected — it "
               "creates an unnecessary intermediate stop and underutilizes the "
               "2.0 m/s approach envelope at 100 m range.”", "quote")], "quote"),
        txt((276, 592, 930, 30),
            [r("Vertex gemini-3.8-flash · decision 1 of 2 · plan age 24.4 s · applied",
               "attr")], "attr"),
        txt((276, 688, 930, 120),
            [r("“The RL velocity direction aligns well with the line of sight; the "
               "short lookahead is rejected to prevent stopping mid-trajectory.”",
               "quote")], "quote"),
        txt((276, 790, 930, 30),
            [r("Vertex gemini-3.8-flash · decision 2 of 2 · range 2.49 m · plan age 22.6 s · applied",
               "attr")], "attr"),
        txt((1320, 424, 460, 34), [r("What the run records", "labelMint")], "labelMint"),
        txt((1320, 470, 480, 72), [r("2", "statSmMint"), r("  decisions", "unitSmDark")],
            "statSmMint"),
        txt((1320, 546, 480, 72), [r("0", "statSmMint"), r("  fallbacks", "unitSmDark")],
            "statSmMint"),
        txt((1320, 622, 480, 72), [r("45.3", "statSmCream"), r("°  initial error", "unitSmDark")],
            "statSmCream"),
        txt((1320, 698, 480, 72), [r("449", "statSmCream"), r("  steps of force + torque",
                                                              "unitSmDark")], "statSmCream"),
        txt((1320, 796, 470, 120),
            [r("Both plans were validated against the state at submission, then "
               "re-gated by the safety channel before actuation.", "captionDark")],
            "captionDark"),
        txt((M, 890, 1180, 80),
            [r("This is the reviewable part: the model states its target, its "
               "reason, and the proposal it declined — with the measurement that "
               "justified the choice. Short explanations are surfaced; private "
               "deliberation is not.", "noteDark")], "noteDark"),
    ],
    notes=("Slow down here. This slide separates the project from a demo video: "
           "quoted decisions with plan age, an applied flag and the rejected "
           "alternative, all in proofs/precision-vertex-docking/decisions.json.\n"
           "The model overrode its learned advisor using the configured envelope — "
           "judgment, not improvisation."),
    source="verbatim quotes · proofs/precision-vertex-docking/decisions.json",
    dark=True,
)

# ============================================================== 07 gate
add("gate", 7, "Capture criteria", "paper",
    art=[
        half_disc(960, 980, 300, "sage", "top"),
        plus(1848, 200, 40, 9, "coral"),
        disc(1806, 300, 16, "teal"),
    ],
    plates=[plate((M, 470, 404, 250), "cream2", 1, radius=22),
            plate((528, 470, 404, 250), "coralTint", 1, radius=22, rot=-1.2),
            plate((952, 470, 404, 250), "amberTint", 1, radius=22),
            plate((1376, 470, 440, 250), "tealTint", 1, radius=22, rot=1.2)],
    pictures=[pic("assets/port-plate.jpg", (M, 780, 1712, 200), "cover", focusY=0.46)],
    elements=[
        txt((M, 214, 1300, 110), [r("Capture is a contract.", "h1")], "h1"),
        txt((M, 336, 1240, 120),
            [r("All four checks must pass, plus one second of stable alignment and "
               "entry into a 5 cm lateral corridor. Manual and automatic capture "
               "share the same gate.", "kicker")], "kicker"),
        txt((M + 36, 508, 320, 34), [r("Range", "labelInk")], "labelInk"),
        txt((M + 36, 548, 330, 80), [r("2", "statSmTeal"), r(" cm", "unitSm")], "statSmTeal"),
        txt((M + 36, 636, 330, 30), [r("shared gate · max 3 cm", "caption")], "caption"),
        txt((564, 508, 320, 34), [r("Relative speed", "labelInk")], "labelInk"),
        txt((564, 548, 330, 80), [r("0.005", "statSmCoral"), r(" m/s", "unitSm")],
            "statSmCoral"),
        txt((564, 636, 330, 30), [r("max 0.01 m/s", "caption")], "caption"),
        txt((988, 508, 320, 34), [r("Attitude error", "labelInk")], "labelInk"),
        txt((988, 548, 330, 80), [r("1", "statSm"), r("°", "unitSm")], "statSm"),
        txt((988, 636, 330, 30), [r("default tolerance", "caption")], "caption"),
        txt((1416, 508, 340, 34), [r("Rotation rate", "labelInk")], "labelInk"),
        txt((1416, 548, 350, 80), [r("0.01", "statSmTeal"), r(" rad/s", "unitSm")],
            "statSmTeal"),
        txt((1416, 636, 350, 30), [r("relative, at contact", "caption")], "caption"),
        txt((M, 996, 1500, 40),
            [r("A stopping-distance envelope brakes the chaser before the near-port "
               "zone, then tightens to capture speed. All four checks are satisfied "
               "together, not in sequence.", "note")], "note"),
    ],
    notes=("The gate is code, not convention: safety.py evaluates all four checks "
           "plus stability and corridor entry.\n"
           "The announced capture only fires after server confirmation — the UI "
           "cannot claim eligibility during abort or sensor dropout.\n"
           "Imagery is a real capture from this project's dashboard."),
)

# ============================================================== 08 result
add("result", 8, "Result", "space",
    art=[
        quarter(0, 984, 200, "mint", "tr", 0.9),
        plus(1856, 196, 40, 9, "amber"),
        dots(1500, 180, 220, 90, 26, 3, "#8FD9C4", 0.28),
    ],
    plates=[plate((M, 560, 1010, 430), "paper", 1, radius=20)],
    pictures=[pic("assets/raw/approach-curves.png", (M + 24, 584, 962, 382), "contain",
                  pad="paper")],
    elements=[
        txt((M, 214, 1620, 110),
            [r("100 metres to 1.945 cm. Zero fallbacks.", "h1Dark")], "h1Dark"),
        *[e for grp in [
            stat_block_dark(x, n, u, lab)
            for x, n, u, lab in [(M, "1.945", "cm", "final separation"),
                                 (544, "0.004", "m/s", "speed at capture"),
                                 (984, "133.6", "s", "simulated time"),
                                 (1424, "5×", "/ 75.4 s", "playback / wall clock")]
        ] for e in grp],
        txt((1160, 592, 560, 34), [r("Envelope actually used", "labelMint")], "labelMint"),
        txt((1160, 640, 560, 380),
            [r("max speed      1.999 m/s\n"
               "max thrust     50.0 N\n"
               "max accel      0.100 m/s²\ngate checks    4 / 4 passed\n"
               "LLM calls      2 applied\nfallbacks      0", "monoSmDark")], "monoSmDark"),
        txt((M, 1002, 1100, 40),
            [r("Measured telemetry · live Vertex + PPO advisory · one accelerated "
               "demonstration at a 2 cm simulated gate", "captionDark")], "captionDark"),
        txt((1160, 856, 640, 120),
            [r("Speed and thrust sat exactly at the configured ceilings — the "
               "envelope bound the manoeuvre, not the model's optimism.", "captionDark")],
            "captionDark"),
    ],
    notes=("Lead with the constraint, not the number: the chaser used its full "
           "configured envelope (2 m/s, 50 N) and still arrived at 0.004 m/s.\n"
           "Chart from proofs/precision-vertex-docking/approach-curves.png.\n"
           "Say the scope out loud: one accelerated live demonstration at a 2 cm "
           "simulated gate, not a hardware accuracy claim."),
    dark=True,
)

# ============================================================== 09 learner
add("learner", 9, "Learned advisor", "paper",
    art=[
        disc(1830, 196, 42, "amber"),
        quarter(1824, 962, 96, "teal", "tl"),
        plus(1660, 300, 36, 8, "coral"),
    ],
    plates=[plate((M, 466, 544, 210), "cream2", 1, radius=20),
            plate((688, 466, 544, 210), "cream2", 1, radius=20),
            plate((1272, 466, 544, 210), "teal", 1, radius=20),
            plate((M, 712, CW, 268), "sage", 1, radius=20)],
    pictures=[],
    elements=[
        txt((M, 214, 1400, 110), [r("Fly the expert. Then improve on it.", "h1")], "h1"),
        txt((M, 334, 1300, 44),
            [r("Reproducible training: expert, cloning, PPO, matched normalisers, "
               "held-out seeds.", "kicker")], "kicker"),
        txt((M + 36, 500, 470, 34), [r("Step 01 · the expert", "labelTeal")], "labelTeal"),
        txt((M + 36, 540, 470, 50), [r("LQR trajectories", "h3")], "h3"),
        txt((M + 36, 596, 470, 60), [r("100 expert episodes over the same dynamics.",
                                       "bodySm")], "bodySm"),
        txt((724, 500, 470, 34), [r("Step 02 · the demonstration", "labelTeal")],
            "labelTeal"),
        txt((724, 540, 470, 50), [r("Behaviour cloning", "h3")], "h3"),
        txt((724, 596, 470, 60), [r("50 epochs on normalised observations.", "bodySm")],
            "bodySm"),
        txt((1308, 500, 470, 34), [r("Step 03 · the refinement", "labelCream")],
            "labelCream"),
        txt((1308, 540, 470, 50), [r("PPO fine-tuning", "h3Dark")], "h3Dark"),
        txt((1308, 596, 480, 60),
            [r("200,704 steps, 8 environments, two T4 GPUs.", "bodySmDark")], "bodySmDark"),
        txt((M + 36, 736, 900, 30),
            [r("Held-out evaluation · seeds 70000–70049 · 5–80 m starts", "label")],
            "label"),
        txt((M + 36, 780, 620, 38), [r("Method", "label")], "label"),
        txt((1130, 780, 300, 38), [r("Seed 42", "label")], "label"),
        txt((1490, 780, 300, 38), [r("Seed 137", "label")], "label"),
        txt((M + 36, 824, 620, 36), [r("LQR with deterministic planner", "bodySmInk")],
            "bodySmInk"),
        txt((1130, 824, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((1490, 824, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((M + 36, 864, 620, 36), [r("PID with deterministic planner", "bodySmInk")],
            "bodySmInk"),
        txt((1130, 864, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((1490, 864, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((M + 36, 904, 620, 36), [r("PPO with deterministic planner", "bodySmInk")],
            "bodySmInk"),
        txt((1130, 904, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((1490, 904, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((M + 36, 944, 620, 36), [r("LQR with PPO advice — recommended", "bodySmInk")],
            "bodySmInk"),
        txt((1130, 944, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((1490, 944, 300, 36), [r("50 / 50 docked", "mono")], "mono"),
        txt((M, 998, 1600, 40),
            [r("The archived policy was trained at a 1.25 m gate — these results do "
               "not establish centimetre precision. Every 50/50 carries a Wilson 95% "
               "interval of ≈92.9–100%.", "note")], "note"),
    ],
    notes=("Be scrupulous; a technical reviewer will attack this slide.\n"
           "Say plainly: the archived policy was trained and evaluated at a 1.25 m "
           "gate; the notebook packages the 2 cm environment for fresh training.\n"
           "The value on the table is pipeline reproducibility — expert, cloning, "
           "PPO, matched normalisers, held-out seeds.\n"
           "Sources: proofs/kaggle-final-seed-42/ and -137/."),
    source="training + evaluation · proofs/kaggle-final-seed-42/ · proofs/kaggle-final-seed-137/",
)

# ============================================================== 10 evidence
add("evidence", 10, "Evidence", "sage",
    art=[
        plus(1848, 966, 36, 8, "teal"),
        disc(1802, 198, 18, "coral"),
        quarter(0, 984, 180, "amber", "tr", 0.85),
    ],
    plates=[plate((M, 320, 900, 660), "paper", 1, radius=20),
            plate((1064, 320, 752, 660), "paper", 1, radius=20)],
    pictures=[pic("assets/dash-precision-bright.jpg", (1096, 356, 688, 388), "cover",
                  focusY=0.2)],
    elements=[
        txt((M, 214, 1400, 110), [r("Every number has a file behind it.", "h1")], "h1"),
        txt((M + 34, 356, 700, 34), [r("Proofs tree · committed, hashed, reviewed",
                                       "labelTeal")], "labelTeal"),
        txt((M + 34, 404, 840, 550),
            [r("kaggle-final-seed-42/      200,704 training steps\n"
               "kaggle-final-seed-137/     independent seed\n"
               "  evaluation.json          every held-out trial\n"
               "  manifest.json            SHA-256 hashes\n"
               "precision-vertex-docking/  live Vertex + PPO run\n"
               "  decisions.json           rationale, rejected options\n"
               "  telemetry.csv            range, speed, thrust\n"
               "code-audit/                30 + 5 modules audited\n"
               "verification.json          pytest · ruff · proofs", "monoSm")], "monoSm"),
        txt((1096, 768, 660, 34), [r("Dashboard · decision log and export", "labelTeal")],
            "labelTeal"),
        txt((1096, 812, 688, 150),
            [r("Every session exports its configuration, decisions, tool readings "
               "and terminal checks — raw material for a replay. Runs that failed "
               "are kept beside the successes.", "bodySm")], "bodySm"),
        txt((M, 998, 1600, 40),
            [r("Hashes establish integrity, not endorsement — the reports say so in "
               "their own words.", "note")], "note"),
    ],
    notes=("Hand a reviewer the folder, not a slide. Offer the live dashboard and "
           "the export of any session they want to poke at.\n"
           "If asked what the hashes prove: file integrity, and that the numbers "
           "were not edited after the run. They do not certify the simulator.\n"
           "Verification entry points: python -m pytest; python -m ruff check src "
           "tests scripts; python scripts/verify_proofs.py."),
)

# ============================================================== 11 safety
add("safety", 11, "Safety & verification", "paper",
    art=[
        dots(1560, 170, 240, 110, 26, 4, "#1C241F", 0.2),
        quarter(1824, 984, 96, "teal", "tl", 0.9),
        plus(120, 956, 36, 8, "amber"),
    ],
    plates=[plate((M, 330, 500, 220), "coralTint", 1, radius=20, rot=-1.5),
            plate((660, 330, 500, 220), "amberTint", 1, radius=20, rot=1.5),
            plate((1220, 330, 596, 640), "cream2", 1, radius=20)],
    pictures=[pic("assets/dash-capture-bright.jpg", (1252, 372, 532, 300), "cover",
                  focusY=0.16)],
    elements=[
        txt((M, 214, 1600, 110), [r("The safety channel trusts only the state.", "h1")], "h1"),
        txt((M + 40, 366, 430, 110), [r("15", "statCoral")], "statCoral"),
        txt((M + 40, 474, 430, 60), [r("audit findings checked against execution — "
                                       "and fixed", "captionInk")], "captionInk"),
        txt((700, 366, 430, 110), [r("6", "statTeal")], "statTeal"),
        txt((700, 474, 430, 60), [r("of them P1, including fault braking moved to "
                                    "an independent channel", "captionInk")], "captionInk"),
        txt((M, 596, 1060, 34), [r("Selected P1 corrections", "labelTeal")], "labelTeal"),
        txt((M, 640, 1060, 340),
            [r("Learned advice was silently off by default → an inference probe now "
               "enables it, and Reset restores that verified default.\n\n"
               "Corrupt policy files passed capability checks → dimensions, "
               "normalisation and a finite prediction are validated before a "
               "session exists.\n\n"
               "Expired provider responses installed braking holds → they are "
               "discarded and current-state guidance sustains the approach.",
               "bodySm")], "bodySm"),
        txt((1252, 700, 532, 34), [r("Capture confirmed in the dashboard", "labelTeal")],
            "labelTeal"),
        txt((1252, 744, 532, 200),
            [r("130 automated tests, ruff clean and a passing production build at "
               "the time of the run.\n\nProvider failure and invalid output take a "
               "labelled deterministic path.", "bodySm")], "bodySm"),
        txt((M, 998, 1600, 40),
            [r("Safety here is a simulation-time envelope contract, not flight "
               "certification — the roadmap starts with latency and sensor models.",
               "note")], "note"),
    ],
    notes=("This slide answers 'how do you know it is safe to even run?'. The "
           "audit is the strongest artifact in the repository: every finding names "
           "its correction and its file.\n"
           "Say the caveat yourself: simulation-time envelope contract, not flight "
           "certification.\n"
           "Full table: proofs/code-audit/README.md."),
)

# ============================================================== 12 limits
add("limits", 12, "Scope", "cream2",
    art=[
        quarter(1824, 0, 96, "coral", "bl"),
        disc(1806, 986, 30, "teal"),
        plus(1836, 208, 40, 9, "amber"),
        dots(104, 940, 260, 90, 26, 4, "#1C241F", 0.2),
    ],
    plates=[],
    pictures=[],
    elements=[
        txt((M, 250, 1200, 110), [r("What this is not.", "h1")], "h1"),
        txt((M, 372, 1400, 120),
            [r("Stated up front, because the first serious question is: what does "
               "this actually prove?", "kickerCoral")], "kickerCoral"),
        txt((M, 540, 780, 34), [r("Not flight-certified", "eyebrowCoral")], "eyebrowCoral"),
        txt((M, 578, 780, 70), [r("Research software, with no certification of any kind.",
                                   "bodySm")], "bodySm"),
        txt((M, 660, 780, 34), [r("Local linearised dynamics", "eyebrowCoral")],
            "eyebrowCoral"),
        txt((M, 698, 780, 70), [r("The primary's motion is prescribed, not controlled.",
                                   "bodySm")], "bodySm"),
        txt((M, 780, 780, 34), [r("No contact model", "eyebrowCoral")], "eyebrowCoral"),
        txt((M, 818, 780, 70), [r("No contact mechanics, structural dynamics or plume "
                                   "interaction.", "bodySm")], "bodySm"),
        txt((M, 900, 780, 34), [r("No sensor estimation", "eyebrowCoral")], "eyebrowCoral"),
        txt((M, 938, 780, 70), [r("The safety channel reads simulator truth — not a "
                                   "flight-ready estimator.", "bodySm")], "bodySm"),
        txt((1016, 540, 800, 34), [r("Demonstrations, not rates", "eyebrowCoral")],
            "eyebrowCoral"),
        txt((1016, 578, 800, 70), [r("Provider runs are individual live checks, not a "
                                      "success rate.", "bodySm")], "bodySm"),
        txt((1016, 660, 800, 34), [r("Archived policy limits", "eyebrowCoral")],
            "eyebrowCoral"),
        txt((1016, 698, 800, 70), [r("Stored checkpoints were trained at a 1.25 m gate; "
                                      "the 2 cm environment is packaged for fresh "
                                      "training.", "bodySm")], "bodySm"),
        txt((1016, 780, 800, 34), [r("Process-local sessions", "eyebrowCoral")],
            "eyebrowCoral"),
        txt((1016, 818, 800, 70), [r("Four active and 32 retained sessions in memory, no "
                                      "authentication.", "bodySm")], "bodySm"),
        txt((1016, 900, 800, 34), [r("Fuel and geometry are assumed", "eyebrowCoral")],
            "eyebrowCoral"),
        txt((1016, 938, 800, 70), [r("Thruster efficiency, lever arm and inertias are "
                                      "editable simulator assumptions.", "bodySm")],
            "bodySm"),
    ],
    notes=("Do not skip this slide. For any technical audience it is the "
           "credibility purchase: you are disclosing the same limits their "
           "reviewers would find.\n"
           "It also points the conversation at what a partner can change — their "
           "propagator, their sensor model, their latency budget.\n"
           "Sources: proofs/README.md, proofs/code-audit/README.md, README.md."),
)

# ============================================================== 13 integration
add("integration", 13, "Integration", "sage",
    art=[
        disc(1810, 196, 40, "amber"),
        quarter(1824, 962, 96, "coral", "tl"),
        plus(1700, 252, 36, 8, "teal"),
    ],
    plates=[plate((M, 330, 800, 520), "paper", 1, radius=24),
            plate((1016, 330, 800, 520), "teal", 1, radius=24),
            plate((M, 878, CW, 100), "cream2", 1, radius=18)],
    pictures=[],
    elements=[
        txt((M, 214, 1600, 110), [r("Bring your vehicle. Keep the loop.", "h1")], "h1"),
        txt((M + 36, 362, 600, 34), [r("You supply", "labelTeal")], "labelTeal"),
        txt((M + 36, 408, 730, 48), [r("A reference vehicle", "h3")], "h3"),
        txt((M + 36, 460, 730, 70),
            [r("Mass properties, thruster and torque limits, propellant model, port "
               "geometry, capture tolerances.", "bodySm")], "bodySm"),
        txt((M + 36, 546, 730, 48), [r("Your dynamics", "h3")], "h3"),
        txt((M + 36, 598, 730, 70),
            [r("Propagator or relative-motion model, attitude coupling, actuator "
               "response.", "bodySm")], "bodySm"),
        txt((M + 36, 684, 730, 48), [r("A mission profile", "h3")], "h3"),
        txt((M + 36, 736, 730, 80),
            [r("Start corridor, approach constraints, abort criteria, and sensor or "
               "timing reality.", "bodySm")], "bodySm"),
        txt((1052, 362, 600, 34), [r("We keep", "labelCream")], "labelCream"),
        txt((1052, 408, 730, 48), [r("The planner contract", "h3Dark")], "h3Dark"),
        txt((1052, 460, 730, 70),
            [r("The same six tools, so plans stay inspectable and comparable across "
               "vehicles.", "bodySmDark")], "bodySmDark"),
        txt((1052, 546, 730, 48), [r("The safety contract", "h3Dark")], "h3Dark"),
        txt((1052, 598, 730, 70),
            [r("An independent gate over your limits, evaluated on your state "
               "estimates.", "bodySmDark")], "bodySmDark"),
        txt((1052, 684, 730, 48), [r("The evidence pipeline", "h3Dark")], "h3Dark"),
        txt((1052, 736, 730, 80),
            [r("Decisions, telemetry and hashes in one shape, so reviewers read one "
               "format.", "bodySmDark")], "bodySmDark"),
        txt((M + 36, 896, 500, 30), [r("Swap points", "labelTeal")], "labelTeal"),
        txt((M + 36, 926, 1620, 50),
            [r("dynamics — replace Clohessy–Wiltshire with your propagator     "
               "controller — replace LQR with your GNC law     policy — plug your "
               "own policy into the advisor slot, it stays advisory", "monoSm")],
            "monoSm"),
    ],
    notes=("This is the commercial slide. Do not sell a black box; sell the "
           "interface and the evidence format.\n"
           "The ask follows naturally: one vehicle model and one mission profile, "
           "and we re-run the reference scenarios on your dynamics.\n"
           "Interfaces: src/app/llm/tools.py, src/app/simulation/safety.py, "
           "src/app/api/routes.py."),
    source="interfaces · src/app/llm/tools.py · src/app/simulation/safety.py",
)

# ============================================================== 14 roadmap
add("roadmap", 14, "Roadmap", "paper",
    art=[
        hair((M, 400, CW, 2), "line"),
        disc(240, 400, 14, "teal"),
        disc(854, 400, 14, "amber"),
        disc(1468, 400, 14, "coral"),
        quarter(1824, 0, 96, "sage", "bl"),
        plus(1836, 966, 36, 8, "teal"),
    ],
    plates=[],
    pictures=[],
    elements=[
        txt((M, 214, 1600, 110), [r("From simulator to qualification.", "h1")],
            "h1"),
        txt((M, 340, 1200, 44),
            [r("Three phases, proposed with a partner — none has started.", "kicker")],
            "kicker"),
        txt((M, 436, 500, 34), [r("Phase 01", "labelTeal")], "labelTeal"),
        txt((M, 476, 500, 56), [r("Partner dynamics", "h3")], "h3"),
        txt((M, 546, 500, 220),
            [r("Plug a partner propagator and actuator model in, re-run the "
               "reference scenarios, and publish a paired comparison against the "
               "current stack.", "bodySm")], "bodySm"),
        txt((M, 790, 500, 90),
            [r("Exit: the same capture gate passed on partner dynamics.", "kickerTeal")],
            "kickerTeal"),
        txt((680, 436, 500, 34), [r("Phase 02", "labelTeal")], "labelTeal"),
        txt((680, 476, 500, 56), [r("Hardware in the loop", "h3")], "h3"),
        txt((680, 546, 500, 220),
            [r("Real flight-computer timing, sensor models and injected comms "
               "latency — then verify that stale plans are discarded and recovery "
               "stays bounded.", "bodySm")], "bodySm"),
        txt((680, 790, 500, 90),
            [r("Exit: latency-bounded replanning demonstrated.", "kickerTeal")],
            "kickerTeal"),
        txt((1356, 436, 500, 34), [r("Phase 03", "labelTeal")], "labelTeal"),
        txt((1356, 476, 500, 56), [r("Qualification pack", "h3")], "h3"),
        txt((1356, 546, 500, 220),
            [r("Traceability from requirement to scenario to telemetry to hash, "
               "with failure cases retained and a reviewer-runnable bundle.",
               "bodySm")], "bodySm"),
        txt((1356, 790, 500, 90),
            [r("Exit: an independent reviewer reproduces a claim unaided.",
               "kickerTeal")], "kickerTeal"),
        txt((M, 916, 1600, 90),
            [r("What stays constant across all three phases: the gate that decides "
               "what counts as capture, the six tools the planner may call, and the "
               "evidence format a reviewer reads. The vehicle underneath them is "
               "yours.", "lead")], "lead"),
    ],
    notes=("Phases are proposals, not commitments — say so explicitly and let the "
           "partner choose the order. Most aerospace teams start with phase 02, "
           "because latency is their real worry.\n"
           "If asked about timeline or cost: that is a scoping conversation, not a "
           "number on this slide."),
)

# ============================================================== 15 ask
add("ask", 15, "The ask", "cream2",
    art=[
        disc(1806, 196, 44, "teal"),
        quarter(0, 984, 200, "amber", "tr", 0.9),
        plus(1660, 280, 36, 8, "coral"),
        dots(1500, 950, 240, 80, 26, 4, "#1C241F", 0.2),
    ],
    plates=[plate((M, 340, 800, 520), "paper", 1, radius=24),
            plate((1016, 340, 800, 520), "teal", 1, radius=24)],
    pictures=[],
    elements=[
        txt((M, 214, 1600, 110), [r("One vehicle model. One mission profile.", "h1")],
            "h1"),
        txt((M + 36, 372, 600, 34), [r("A pilot needs from you", "labelTeal")], "labelTeal"),
        txt((M + 36, 424, 730, 44), [r("A reference vehicle", "h3")], "h3"),
        txt((M + 36, 474, 730, 70),
            [r("Mass properties, thruster limits, port geometry, capture "
               "tolerances.", "bodySm")], "bodySm"),
        txt((M + 36, 556, 730, 44), [r("A mission profile", "h3")], "h3"),
        txt((M + 36, 606, 730, 70),
            [r("The scenario you would actually fly, and the failure cases you care "
               "about.", "bodySm")], "bodySm"),
        txt((M + 36, 688, 730, 44), [r("An evaluation owner", "h3")], "h3"),
        txt((M + 36, 738, 730, 90),
            [r("Someone who will tell us the run is wrong and why. That is the "
               "fastest route to a defensible result.", "bodySm")], "bodySm"),
        txt((1052, 372, 600, 34), [r("You get back", "labelCream")], "labelCream"),
        txt((1052, 424, 730, 44), [r("Your scenarios, re-run", "h3Dark")], "h3Dark"),
        txt((1052, 474, 730, 70),
            [r("The reference captures on your dynamics, with the same gate, the "
               "same tools, the same telemetry.", "bodySmDark")], "bodySmDark"),
        txt((1052, 556, 730, 44), [r("A paired comparison", "h3Dark")], "h3Dark"),
        txt((1052, 606, 730, 70),
            [r("Your controller against the current stack on identical seeds, "
               "reported with intervals.", "bodySmDark")], "bodySmDark"),
        txt((1052, 688, 730, 44), [r("An evidence bundle", "h3Dark")], "h3Dark"),
        txt((1052, 738, 730, 90),
            [r("Decisions, tool readings, telemetry and hashes — including the runs "
               "that did not work.", "bodySmDark")], "bodySmDark"),
        txt((M, 906, 1600, 60),
            [r("Everything in this deck is reproducible from the files in proofs/ — "
               "including the failures.", "lead")], "lead"),
    ],
    notes=("Adapt the closing sentence to the room before presenting: name the "
           "specific team and vehicle you want to fly.\n"
           "If they push on maturity, concede it and redirect: the loop runs end to "
           "end today with an audit trail; what changes with them is the vehicle "
           "model and the mission profile.\n"
           "Do not quote a price or a schedule from this slide."),
    source="pilot scope · draft for partner discussion",
)

# ============================================================== 16 close
add("close", 16, "Docking Lab", "space",
    art=[
        photo("assets/hero-capture.jpg", (0, 0, 1920, 1080), focus="46% 42%"),
        scrim(0, 0, 1920, 1080, "to right",
              [(0, "rgba(14,21,25,.97)"), (46, "rgba(14,21,25,.9)"),
               (80, "rgba(14,21,25,.6)"), (100, "rgba(14,21,25,.3)")]),
        bigquote(84, 300, "mint", 220),
        plus(1836, 960, 40, 9, "amber"),
    ],
    plates=[],
    pictures=[],
    elements=[
        txt((M, 420, 900, 240), [r("Point it at\nyour vehicle.", "h1xlDark")], "h1xlDark"),
        txt((M, 660, 860, 140),
            [r("The loop already runs end to end: planner, advisor, executor, "
               "safety channel, dashboard and evidence bundle.", "kickerDark")],
            "kickerDark"),
        txt((M, 828, 300, 30), [r("Watch the run", "labelMint")], "labelMint"),
        txt((M, 862, 860, 34),
            [r("loom.com/share/fc396b5ea4f344659464c48dba367314", "monoSmDark")],
            "monoSmDark"),
        txt((M, 918, 300, 30), [r("Open the evidence", "labelMint")], "labelMint"),
        txt((M, 952, 900, 34),
            [r("proofs/ · dashboard at 127.0.0.1:8000 · API docs at /docs", "monoSmDark")],
            "monoSmDark"),
        txt((M, 1002, 900, 30),
            [r("Contact: [ name · email ] — replace before sending", "captionDark")],
            "captionDark"),
    ],
    notes=("Close by handing over the artifacts, not by summarising: offer the "
           "live dashboard, the proofs folder, and the exported session of any run "
           "they want to audit.\n"
           "Replace the placeholder contact line before sending this deck out.\n"
           "Demo link as published in README.md."),
    dark=True,
)
