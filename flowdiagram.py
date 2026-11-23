"""Animated process flow diagram (self-contained SVG + CSS) driven by the technical results."""
from __future__ import annotations
from engine.flows import energy_flows


def _n(v):
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def pfd_html(t: dict, p, process_label: str, height: int = 520) -> str:
    wet = max(t["wet_feed_t_y"], 1e-9); e = energy_flows(t, p); htc = t["process_type"] == "htc"
    w = lambda x: max(3.0, 46.0 * x / wet) if x > 1e-9 else 0.0
    ss = e["self_sufficiency"]; surplus = e["surplus"] > 0
    badge_c = "#3fd0a8" if ss >= 0.999 else ("#e0b04c" if ss >= 0.6 else "#ff7a66")
    badge_t = "Heat self-sufficient" + (f" · surplus {_n(e['surplus'])} GJ/y" if surplus else "") if ss >= 0.999 else f"{ss:.0%} self-sufficient · external heat {_n(e['external'])} GJ/y"
    def pipe(d, x, col, spd=1.0, dash="10 14"):
        if x <= 0: return ""
        return (f'<path d="{d}" stroke="{col}" stroke-opacity=".30" stroke-width="{x:.1f}" fill="none" stroke-linecap="butt"/>'
                f'<path class="flow" style="animation-duration:{1.6/spd:.2f}s" d="{d}" stroke="{col}" stroke-width="{max(2.0, x*0.35):.1f}" fill="none" stroke-dasharray="{dash}" stroke-linecap="round"/>')
    box = lambda x, y, wd, h, title, sub, col: (f'<rect x="{x}" y="{y}" width="{wd}" height="{h}" rx="14" fill="#10242f" stroke="{col}" stroke-width="2"/>'
        f'<text x="{x+wd/2}" y="{y+h/2-4}" class="bt" text-anchor="middle">{title}</text><text x="{x+wd/2}" y="{y+h/2+16}" class="bs" text-anchor="middle">{sub}</text>')
    lbl = lambda x, y, txt, col="#cfe3ec", anchor="middle": f'<text x="{x}" y="{y}" class="lb" fill="{col}" text-anchor="{anchor}">{txt}</text>'
    s = []
    # mass streams
    s.append(pipe("M120,215 L250,215", w(wet), "#8fb339")); s.append(lbl(185, 190, f"Wet feed {_n(wet)} t/y"))
    s.append(pipe("M360,215 L500,215", w(t["dry_feed_t_y"]), "#8fb339")); s.append(lbl(430, 190, f"Dry feed {_n(t['dry_feed_t_y'])}"))
    if t["feed_water_t_y"] > 1e-9:
        s.append(pipe("M305,160 L305,70", w(t["feed_water_t_y"]), "#6aa7d6")); s.append(lbl(305, 52, ("Process water " if htc else "Water vapour ") + f"{_n(t['feed_water_t_y'])} t/y", "#9cc9ec"))
    s.append(pipe("M610,185 C660,185 690,110 760,110", w(t["char_t_y"]), "#c8d3dc")); s.append(lbl(770, 92, f"Biochar {_n(t['char_t_y'])} t/y", "#ffffff", "start"))
    s.append(pipe("M610,215 L760,215", w(t["liquid_t_y"]), "#e0b04c")); s.append(lbl(770, 200, f"Bio-oil {_n(t['liquid_t_y'])} t/y", "#f2cf86", "start"))
    s.append(pipe("M610,245 C650,245 660,300 720,320", w(t["gas_t_y"]), "#b0a8d8")); s.append(lbl(730, 300, f"Syngas {_n(t['gas_t_y'])} t/y", "#cfc9ee", "start"))
    # energy loop
    s.append(pipe("M720,350 C600,400 420,400 320,370 L320,262", max(4.0, 36 * min(e["recovered"], max(e["requirement"], 1e-9)) / max(e["requirement"], e["recovered"], 1e-9)), "#ff7a66", 0.8, "4 12"))
    s.append(lbl(520, 424, f"Recovered heat {_n(e['recovered'])} GJ/y → dryer & reactor", "#ff9d8c"))
    if e["external"] > 0: s.append(pipe("M120,330 L260,330 L300,262", max(4.0, 36 * e["external"] / max(e["requirement"], 1e-9)), "#7fb4ff", 0.8, "4 12")); s.append(lbl(120, 352, f"External heat {_n(e['external'])} GJ/y", "#9cc4ff", "start"))
    if surplus: s.append(pipe("M880,350 L1010,350", max(4.0, 36 * e["surplus"] / max(e["recovered"], 1e-9)), "#3fd0a8", 0.8, "4 12")); s.append(lbl(1010, 340, f"Surplus {_n(e['surplus'])} GJ/y", "#7ff0cf", "end"))
    nodes = box(250, 165, 110, 100, "Slurry heating" if htc else "Drying", "feed prep", "#8fb339") + box(500, 150, 110, 130, "Reactor", f"{p.reactor_temp_C:.0f} °C", "#ff7a66") + box(720, 320, 160, 62, "Burner / boiler", "uses syngas", "#b0a8d8")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent;font-family:-apple-system,"Segoe UI",Inter,Roboto,sans-serif}}
.card{{position:relative;border-radius:16px;overflow:hidden;background:radial-gradient(ellipse at 25% 15%,#1b3a49 0%,#0c1a24 60%,#070f16 100%);border:1px solid rgba(120,170,190,.22);height:{height-4}px}}
svg{{width:100%;height:100%}} .bt{{fill:#e8f3f8;font-size:16px;font-weight:700}} .bs{{fill:#8fb0c0;font-size:12.5px}} .lb{{font-size:13px;font-weight:600}}
.flow{{animation:mv linear infinite}} @keyframes mv{{to{{stroke-dashoffset:-48}}}}
.ttl{{position:absolute;left:16px;top:12px;color:#9fc3d3;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}}
.badge{{position:absolute;right:16px;top:10px;padding:7px 14px;border-radius:999px;font-size:13px;font-weight:700;color:#07131a;background:{badge_c}}}
.bar{{position:absolute;left:16px;bottom:12px;width:300px;color:#9fc3d3;font-size:12px}} .bar i{{display:block;height:8px;border-radius:6px;background:rgba(255,255,255,.12);margin-top:5px;overflow:hidden}} .bar b{{display:block;height:100%;width:{min(ss,1)*100:.0f}%;background:{badge_c}}}
</style></head><body><div class="card"><div class="ttl">{process_label} · stream width ∝ flow</div><div class="badge">{badge_t}</div>
<svg viewBox="0 0 1100 {height-4}" preserveAspectRatio="xMidYMid meet">{''.join(s)}{nodes}</svg>
<div class="bar">Energy self-sufficiency {ss:.0%}<i><b></b></i></div></div></body></html>"""
    return html
