"""Streamlit bridge for the offline three.js biochar viewer (static/biochar3d)."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import streamlit.components.v1 as components

_comp = components.declare_component("biochar3d", path=str(Path(__file__).parent / "static" / "biochar3d"))


def viewer(nano: dict, micro: dict, captions: dict, height: int = 560, mode: str = "lattice", compact: bool = False, key: str | None = None):
    """Render the interactive viewer. `sig` makes the browser rebuild the scene only when the structure changes,
    so rotating/zooming survives Streamlit reruns."""
    sig = hashlib.md5((nano["pos"][:4000] + str(nano["n"]) + json.dumps(micro, sort_keys=True)[:6000]).encode()).hexdigest()
    return _comp(nano=nano, micro=micro, captions=captions, height=height, mode=mode, compact=compact, sig=sig, key=key, default=None)
