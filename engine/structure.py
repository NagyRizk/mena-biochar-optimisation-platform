"""Stylised 3D structure generator for biochar (layer-1 visual).

HONEST SCOPE: this is a *qualitative, property-driven* structure model for communication, not a molecular
simulation, DFT or MD result. Inputs are the platform's own predicted properties (H/C, ash, HTT, feedstock
class). Each structural descriptor is derived by a stated rule and labelled with its basis:

* Aromatic cluster size   - from predicted H/C. For a compact polycyclic aromatic hydrocarbon the H/C ratio is
                            fixed by the cluster size (benzene 1.0, coronene 0.5, circumcoronene 0.33 ...), so
                            the cluster whose H/C is closest to the predicted value is drawn.
* Aromatic carbon share   - linear screening trend in H/C (placeholder); the rest is drawn as aliphatic chains.
* Layers per crystallite  - typical turbostratic stacking trend with HTT (placeholder).
* Interlayer spacing      - typical d002 trend with HTT (placeholder).
* O/C                     - median O/C of the bundled dataset in the matching H/C bin (not a predicted target).
* Porosity / pore network - stylised, feedstock-class dependent; NOT a BET or porosimetry prediction.
"""
from __future__ import annotations
import base64
import numpy as np

CC = 1.42                    # aromatic C-C bond length, angstrom
A_RING = CC * np.sqrt(3.0)   # ring-centre spacing, angstrom
CH, CO, CC_ALI = 1.09, 1.36, 1.54

_OC_H = [0.10, 0.20, 0.30, 0.425, 0.60, 0.80, 1.05, 1.50]
_OC_V = [0.060, 0.066, 0.093, 0.114, 0.184, 0.240, 0.267, 0.337]   # dataset medians per H/C bin


# ---------------------------------------------------------------- aromatic cluster templates
def _ring_centres(n):
    """First n ring centres of a compact cluster on the triangular lattice (ordered by distance, then angle)."""
    pts = []
    R = 8
    for q in range(-R, R + 1):
        for r in range(-R, R + 1):
            if abs(q + r) > R: continue
            x, y = A_RING * (q + r / 2.0), A_RING * (r * np.sqrt(3) / 2.0)
            pts.append((round(float(np.hypot(x, y)), 3), round(float(np.arctan2(y, x)) % (2 * np.pi), 3), x, y))
    pts.sort()
    return np.array([[p[2], p[3]] for p in pts[:n]])


def _template(n_rings):
    cen = _ring_centres(n_rings)
    th = np.deg2rad(30 + 60 * np.arange(6))
    atoms, key2i, ring_of, bonds = [], {}, [], set()
    for ci, (cx, cy) in enumerate(cen):
        ids = []
        for t in th:
            x, y = cx + CC * np.cos(t), cy + CC * np.sin(t)
            k = (round(x, 2), round(y, 2))
            if k not in key2i:
                key2i[k] = len(atoms); atoms.append((x, y)); ring_of.append([])
            i = key2i[k]; ring_of[i].append(ci); ids.append(i)
        for a in range(6):
            i, j = ids[a], ids[(a + 1) % 6]
            bonds.add((min(i, j), max(i, j)))
    C = np.array(atoms)
    edge = [i for i, r in enumerate(ring_of) if len(r) == 1]
    out = np.array([C[i] - cen[ring_of[i][0]] for i in edge])
    out /= np.linalg.norm(out, axis=1, keepdims=True)
    return {"C": C, "bonds": np.array(sorted(bonds)), "edge": np.array(edge, dtype=int), "out": out,
            "n_rings": n_rings, "hc": len(edge) / len(C), "rmax": float(np.linalg.norm(C - C.mean(0), axis=1).max())}


_TPL, _HC_BY_N = {}, {}
def _tpl(n):
    if n not in _TPL: _TPL[n] = _template(n)
    return _TPL[n]

def _hc_table():
    if not _HC_BY_N:
        for n in range(1, 62): _HC_BY_N[n] = _tpl(n)["hc"]
    return _HC_BY_N


def rings_for_hc(hc: float) -> int:
    """Number of fused rings in a compact PAH cluster whose H/C is closest to `hc` (1 ring = benzene)."""
    tab = _hc_table()
    return min(tab, key=lambda n: (abs(tab[n] - hc), n))


# ---------------------------------------------------------------- descriptors
LUMEN_BASE = {"woody": 0.60, "herbaceous": 0.52, "shells and kernels": 0.30, "kitchen waste": 0.40, "manure": 0.0, "sewage sludge": 0.0}
CH_GRID = {"woody": 5, "herbaceous": 7, "shells and kernels": 4, "kitchen waste": 3, "manure": 0, "sewage sludge": 0}


def descriptors(htt: float, hc: float, ash_pct: float, cls: str, c_pct: float | None = None) -> dict:
    hc = float(np.clip(hc if hc == hc else 0.5, 0.08, 1.8))
    n_rings = rings_for_hc(min(hc, 1.0))
    tpl = _tpl(n_rings)
    fa = float(np.clip(1.10 - 0.75 * hc, 0.12, 0.98))
    n_layers = int(np.clip(round(np.interp(htt, [300, 450, 550, 650, 750, 850], [1, 1, 1.6, 2.2, 3.0, 4.0])), 1, 5))
    d002 = float(np.interp(htt, [300, 500, 700, 900], [0.420, 0.395, 0.370, 0.350]))
    oc = float(np.interp(hc, _OC_H, _OC_V))
    ash = float(ash_pct) if ash_pct == ash_pct else 8.0
    lam = 0.0
    if CH_GRID.get(cls, 0): lam = float(np.clip(LUMEN_BASE.get(cls, 0.4) + 0.24 * np.clip((htt - 350) / 450, 0, 1), 0.2, 0.90))
    meso = float(np.clip(0.25 + 0.75 * np.clip((htt - 350) / 400, 0, 1), 0.2, 1.0))
    phi = float(np.interp(htt, [300, 400, 500, 600, 700, 800, 900], [0.25, 0.38, 0.50, 0.60, 0.66, 0.70, 0.68]))
    return {"htt": float(htt), "hc": hc, "cls": cls, "n_rings": n_rings, "cluster_hc": tpl["hc"], "La_nm": 2 * tpl["rmax"] / 10 + 0.28,
            "arom_frac": fa, "n_layers": n_layers, "d002_nm": d002, "oc": oc, "ash_pct": ash, "lumen_ratio": lam,
            "n_channels_axis": CH_GRID.get(cls, 0), "meso_density": meso, "porosity_visual": phi}


# ---------------------------------------------------------------- nano (atomistic) model
def _b64(a): return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")

def _rot_random(rng):
    q = rng.normal(size=4); q /= np.linalg.norm(q); w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

def _rot_z(t): c, s = np.cos(t), np.sin(t); return np.array([[c, -s], [s, c]])


def build_nano(desc: dict, seed: int = 11, c_target: int = 3000) -> dict:
    rng = np.random.default_rng(seed)
    tpl = _tpl(desc["n_rings"]); nC = len(tpl["C"]); nL = desc["n_layers"]; d_A = desc["d002_nm"] * 10
    n_cr = int(np.clip(round(c_target / (nC * nL)), 3, 240))
    curv_max = float(np.interp(desc["htt"], [300, 500, 700, 900], [0.035, 0.026, 0.016, 0.010]))
    R = float(np.sqrt(tpl["rmax"] ** 2 + (((nL - 1) * d_A) / 2) ** 2) + 1.4)
    L = float((n_cr * (4 / 3) * np.pi * R ** 3 / 0.30) ** (1 / 3)); L = max(L, 2.4 * R)
    # random sequential placement of crystallite bounding spheres
    cen = []
    lim = L / 2 - 0.55 * R
    for _ in range(n_cr * 60):
        if len(cen) >= n_cr: break
        p = rng.uniform(-lim, lim, 3)
        if all(np.linalg.norm(p - c) > 1.7 * R for c in cen): cen.append(p)
    pos, typ, bonds, e_pos, e_dir, e_idx = [], [], [], [], [], []
    off = 0
    for c in cen:
        Rm = _rot_random(rng); curv = rng.choice([-1, 1]) * rng.uniform(0.3, 1.0) * curv_max
        for li in range(nL):
            th = rng.uniform(0, 2 * np.pi); sh = rng.uniform(-1.2, 1.2, 2)
            xy = tpl["C"] @ _rot_z(th).T + sh
            z = (li - (nL - 1) / 2) * d_A + 0.5 * curv * (xy ** 2).sum(1)
            P = np.c_[xy, z] + rng.normal(0, 0.05, (nC, 3))
            P = P @ Rm.T + c
            pos.append(P); typ.append(np.zeros(nC, np.uint8)); bonds.append(tpl["bonds"] + off)
            u2 = tpl["out"] @ _rot_z(th).T
            U = np.c_[u2, np.zeros(len(u2))] @ Rm.T
            e_pos.append(P[tpl["edge"]]); e_dir.append(U); e_idx.append(tpl["edge"] + off)
            off += nC
    pos = np.vstack(pos); typ = np.concatenate(typ); bonds = np.vstack(bonds)
    e_pos = np.vstack(e_pos); e_dir = np.vstack(e_dir); e_idx = np.concatenate(e_idx)
    n_ar = len(pos); n_edge = len(e_idx)
    # aliphatic side chains (from share of non-aromatic carbon), O groups, then H on remaining edge sites
    order = rng.permutation(n_edge); used = np.zeros(n_edge, bool)
    fa = desc["arom_frac"]; chain_C = min((1 - fa) / fa * n_ar, 3.0 * n_ar)
    mean_len = 5.0; n_ch = int(min(round(chain_C / mean_len), 0.55 * n_edge))
    new_pos, new_typ, new_bonds = [], [], []; cur = n_ar
    for e in order[:n_ch]:
        used[e] = True; Ln = int(rng.integers(3, 8)); u = e_dir[e] / np.linalg.norm(e_dir[e])
        perp = np.cross(u, rng.normal(size=3)); perp /= np.linalg.norm(perp); prev = e_pos[e]; prev_i = int(e_idx[e]); sgn = 1
        for _ in range(Ln):
            step = u * 0.85 + sgn * perp * 0.55 + rng.normal(0, 0.28, 3); step *= CC_ALI / np.linalg.norm(step)
            p = prev + step; new_pos.append(p); new_typ.append(1); new_bonds.append((prev_i, cur))
            prev, prev_i = p, cur; cur += 1; sgn = -sgn
    free = [e for e in order if not used[e]]
    n_C_tot = n_ar + len(new_pos)
    n_O = int(min(round(desc["oc"] * n_C_tot), 0.9 * len(free)))
    for e in free[:n_O]:
        used[e] = True; p = e_pos[e] + e_dir[e] * CO; new_pos.append(p); new_typ.append(3); new_bonds.append((int(e_idx[e]), cur)); cur += 1
    rest = [e for e in free[n_O:]]
    pH = float(np.clip(desc["hc"] * n_C_tot / max(len(rest) + 1e-9, 1), 0.15, 1.0))
    n_H = 0
    for e in rest:
        if rng.random() < pH:
            p = e_pos[e] + e_dir[e] * CH; new_pos.append(p); new_typ.append(2); new_bonds.append((int(e_idx[e]), cur)); cur += 1; n_H += 1
    if new_pos:
        pos = np.vstack([pos, np.array(new_pos)]); typ = np.concatenate([typ, np.array(new_typ, np.uint8)]); bonds = np.vstack([bonds, np.array(new_bonds)])
    pos -= pos.mean(0)
    extent = float(np.abs(pos).max() * 2)
    stats = {"n_atoms": int(len(pos)), "n_C_aromatic": int(n_ar), "n_C_aliphatic": int(len(new_pos) - n_O - n_H), "n_O": int(n_O), "n_H": int(n_H),
             "n_crystallites": len(cen), "box_nm": L / 10}
    return {"pos": _b64(pos.astype(np.float32)), "typ": _b64(typ), "bonds": _b64(bonds.astype(np.uint32)), "n": int(len(pos)), "nb": int(len(bonds)),
            "box": float(L), "extent": extent, "stats": stats}


# ---------------------------------------------------------------- micro (particle / pore network) model
def build_micro(desc: dict, seed: int = 5) -> dict:
    """Normalised particle (unit cube-ish) description; the viewer meshes it with marching cubes."""
    rng = np.random.default_rng(seed); n = desc["n_channels_axis"]; lam = desc["lumen_ratio"]
    channels, spheres, ash = [], [], []
    if n:
        pitch = 1.40 / n; r0 = 0.5 * pitch * lam
        for j in range(n):
            for i in range(n):
                x = -0.70 + pitch * (i + 0.5 + (0.5 if j % 2 else 0.0) - (0.25 if n > 1 else 0)); y = -0.70 + pitch * (j + 0.5)
                if abs(x) > 0.70 or abs(y) > 0.70: continue
                channels.append([x + rng.normal(0, pitch * 0.05), y + rng.normal(0, pitch * 0.05), r0 * float(np.clip(1 + 0.16 * rng.normal(), 0.6, 1.4))])
        if desc["cls"] == "woody":
            for idx in rng.choice(len(channels), size=min(3, len(channels)), replace=False): channels[idx][2] *= 1.5
        if desc["cls"] == "herbaceous": channels.append([0.0, 0.0, 0.34 * (0.8 + 0.4 * lam)])
    amorphous = n == 0
    n_sph = int((220 + 420 * desc["meso_density"]) if amorphous else (50 + 330 * desc["meso_density"]))
    for _ in range(n_sph):
        r = float(rng.uniform(0.06, 0.16) if amorphous else rng.uniform(0.022, 0.055))
        if amorphous:   # foam-like: pores biased towards the particle surface so they are visible from outside
            v = rng.normal(size=3); v /= np.linalg.norm(v); v = v * float(rng.uniform(0.35, 0.82)); v = np.clip(v, -0.72, 0.72)
            spheres.append([float(a) for a in v] + [r])
        else:
            spheres.append([float(a) for a in rng.uniform(-0.7, 0.7, 3)] + [r])
    n_ash = int(np.clip(round(desc["ash_pct"] * 0.9), 0, 48))
    for _ in range(n_ash):
        if channels and not amorphous:
            ch = channels[int(rng.integers(len(channels)))]; a = rng.uniform(0, 2 * np.pi); r = float(rng.uniform(0.03, 0.08))
            ash.append([ch[0] + (ch[2] - 0.2 * r) * np.cos(a), ch[1] + (ch[2] - 0.2 * r) * np.sin(a), float(rng.uniform(-0.7, 0.7)), r])
        else:
            ash.append([float(v) for v in rng.uniform(-0.7, 0.7, 3)] + [float(rng.uniform(0.04, 0.10))])
    rough = float(0.004 + 0.012 * desc["meso_density"])
    return {"channels": [[float(v) for v in c] for c in channels], "spheres": spheres, "ash": [[float(v) for v in a] for a in ash], "rough": rough,
            "amorphous": bool(amorphous), "stats": {"n_channels": len(channels), "n_mesopores": n_sph, "n_ash_grains": n_ash}}
