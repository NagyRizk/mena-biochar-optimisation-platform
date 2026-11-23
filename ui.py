"""Shared look-and-feel helpers."""
import streamlit as st

PALETTE = ["#1f7a5a", "#d9a441", "#3b82a0", "#b5523b", "#7a8b99", "#6b5b95", "#8fb339", "#c97b9b"]
GREEN, AMBER, BLUE, RED, GREY = PALETTE[0], PALETTE[1], PALETTE[2], PALETTE[3], PALETTE[4]

CSS = """
<style>
html, body, [class*="css"] { font-family: -apple-system, "Segoe UI", Inter, Roboto, sans-serif; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1280px; }
[data-testid="stToolbar"], [data-testid="stDecoration"], footer, #MainMenu { visibility: hidden; height: 0; }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }
.ph { margin: 0 0 1.4rem 0; }
.ph h2 { margin: 0; font-size: 1.9rem; font-weight: 700; }
.ph p { margin: .35rem 0 0; opacity: .66; font-size: 1rem; max-width: 62ch; }
.sec { font-size: .74rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; opacity: .55; margin: 1.9rem 0 .7rem; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px; margin: .3rem 0 1.2rem; }
.kpi { border: 1px solid rgba(127,140,150,.24); border-radius: 14px; padding: 14px 16px; background: rgba(127,140,150,.06); }
.kpi .kl { font-size: .72rem; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; opacity: .6; }
.kpi .kv { font-size: 1.55rem; font-weight: 700; line-height: 1.25; margin-top: 3px; overflow-wrap: anywhere; }
.kpi .kv small { font-size: .8rem; font-weight: 500; opacity: .6; margin-left: 4px; }
.kpi .ks { font-size: .8rem; opacity: .65; margin-top: 2px; }
.kpi.accent { border-left: 4px solid #1f7a5a; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: .2rem 0 1.1rem; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: .8rem; font-weight: 600; border: 1px solid transparent; }
.chip.ok { background: rgba(31,122,90,.12); color: #1f7a5a; border-color: rgba(31,122,90,.25); }
.chip.bad { background: rgba(181,82,59,.12); color: #b5523b; border-color: rgba(181,82,59,.28); }
.chip.warn { background: rgba(217,164,65,.16); color: #946a10; border-color: rgba(217,164,65,.35); }
.chip.na { background: rgba(127,140,150,.14); opacity: .85; border-color: rgba(127,140,150,.25); }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
.stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid rgba(128,128,128,.22); flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] { padding: 9px 16px; border-radius: 8px 8px 0 0; font-weight: 550; }
.stTabs [aria-selected="true"] { color: #1f7a5a; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.1rem; }
section[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.18); }
section[data-testid="stSidebar"] .stRadio label[data-baseweb="radio"] > div:first-child { display: none; }
section[data-testid="stSidebar"] .stRadio label[data-baseweb="radio"] { padding: 9px 12px; border-radius: 9px; width: 100%; margin: 1px 0; }
section[data-testid="stSidebar"] .stRadio label[data-baseweb="radio"]:hover { background: rgba(31,122,90,.09); }
section[data-testid="stSidebar"] .stRadio label[data-baseweb="radio"]:has(input:checked) { background: rgba(31,122,90,.16); font-weight: 650; }
.brand { font-weight: 750; font-size: 1.15rem; line-height: 1.2; }
.brand span { display: block; font-weight: 400; font-size: .8rem; opacity: .6; margin-top: 2px; }
.scn { border: 1px solid rgba(127,140,150,.24); border-radius: 12px; padding: 10px 12px; font-size: .82rem; line-height: 1.5; background: rgba(127,140,150,.06); }
.scn b { font-weight: 650; }
.small { font-size: .84rem; opacity: .72; }
.stButton > button[kind="primary"] { background: #1f7a5a; border-color: #1f7a5a; }
.stButton > button, .stDownloadButton > button { border-radius: 9px; }

.hero { border-radius: 18px; padding: 26px 30px 24px; background: linear-gradient(135deg, rgba(31,122,90,.22), rgba(59,130,160,.14) 60%, rgba(217,164,65,.10)); border: 1px solid rgba(31,122,90,.30); margin: 0 0 1.3rem; }
.hero .eyebrow { font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #1f7a5a; }
.hero h1 { margin: .25rem 0 0; font-size: 2.15rem; line-height: 1.15; letter-spacing: -.02em; font-weight: 750; padding: 0; }
.hero p { margin: .6rem 0 0; font-size: 1.05rem; opacity: .78; max-width: 68ch; }
.tagrow { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.tag { font-size: .78rem; padding: 4px 11px; border-radius: 999px; background: rgba(127,140,150,.16); font-weight: 600; }
.strip { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; border: 1px solid rgba(127,140,150,.24); border-radius: 12px; padding: 9px 14px; background: rgba(127,140,150,.06); margin: .1rem 0 1.1rem; font-size: .88rem; }
.strip .lbl { font-size: .7rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; opacity: .55; }
.strip .it { padding: 3px 10px; border-radius: 999px; background: rgba(31,122,90,.12); font-weight: 600; }
.strip .hint { margin-left: auto; opacity: .55; font-size: .78rem; }
.side-h { font-size: .7rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; opacity: .5; margin: .9rem 0 .25rem; }
.stepnum { display: inline-flex; width: 26px; height: 26px; border-radius: 50%; align-items: center; justify-content: center; background: #1f7a5a; color: #fff; font-weight: 700; font-size: .85rem; margin-bottom: 6px; }
.stepcard-t { font-weight: 700; font-size: 1.02rem; margin: 0; }
.stepcard-d { font-size: .84rem; opacity: .68; margin: .2rem 0 .5rem; min-height: 3.6em; line-height: 1.4; }
.flowbar { margin: 0 0 .9rem; }
.flowbar .stButton > button { padding: .25rem .4rem; font-size: .82rem; font-weight: 600; min-height: 2.1rem; }
.foot { border-top: 1px solid rgba(127,140,150,.22); margin: 2rem 0 .8rem; }
.viewer-note { font-size: .8rem; opacity: .65; margin-top: .4rem; line-height: 1.45; }
section[data-testid="stSidebar"] .stRadio [data-testid="stCaptionContainer"], section[data-testid="stSidebar"] .stRadio label p + div { opacity: .6; }
</style>
"""

def inject(): st.markdown(CSS, unsafe_allow_html=True)

def header(title, subtitle=""):
    st.markdown(f'<div class="ph"><h2>{title}</h2><p>{subtitle}</p></div>', unsafe_allow_html=True)

def section(text): st.markdown(f'<div class="sec">{text}</div>', unsafe_allow_html=True)

def pill(text, kind="ok"): return f'<span class="pill {kind}">{text}</span>'

def pills(items): chips(items)

def style_fig(fig, height=340, legend=True):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=32, b=8), colorway=PALETTE, showlegend=legend,
                      legend=dict(orientation="h", y=-0.2), font=dict(size=12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="rgba(128,128,128,.35)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False)
    return fig


ICON = {"ok": "\u2713", "bad": "\u2717", "warn": "!", "na": "\u00b7"}

def kpis(items):
    """items: (label, value, sub[, unit]) -> responsive card grid, never truncates."""
    cards = []
    for it in items:
        label, value, sub = it[0], it[1], (it[2] if len(it) > 2 else "")
        unit = f"<small>{it[3]}</small>" if len(it) > 3 and it[3] else ""
        cards.append(f'<div class="kpi"><div class="kl">{label}</div><div class="kv">{value}{unit}</div><div class="ks">{sub}</div></div>')
    st.markdown('<div class="kpis">' + "".join(cards) + "</div>", unsafe_allow_html=True)

def chips(items):
    st.markdown('<div class="chips">' + "".join(f'<span class="chip {k}">{ICON[k]} {t}</span>' for t, k in items) + "</div>", unsafe_allow_html=True)
