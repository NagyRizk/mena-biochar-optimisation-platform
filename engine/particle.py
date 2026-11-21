"""1-D transient heat conduction with first-order devolatilisation in a spherical biomass particle.

Finite-volume, fully implicit in time. A reduced-order particle-scale model, NOT CFD: no gas flow,
no intra-particle pressure, no shrinkage. Verified against the analytical sphere solution
(see verify_conduction). Kinetic defaults: Di Blasi & Branca (2001) one-step global reaction for beech
wood (E = 141.2 kJ/mol, ln A = 22.2 1/s), fitted over 573-708 K; used beyond that range it is an
extrapolation. All property values are placeholders typical of wood/char.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np
from scipy.linalg import solve_banded

R_GAS = 8.314462618

@dataclass
class ParticleParams:
    diameter_mm: float = 20.0
    T0_C: float = 25.0
    T_inf_C: float = 500.0
    h_W_m2K: float = 50.0          # lumped convection + radiation coefficient (assumption)
    rho_virgin: float = 600.0      # kg/m3 (assumption)
    k_virgin: float = 0.15         # W/m/K (assumption)
    k_char: float = 0.10           # W/m/K (assumption)
    cp_virgin: float = 1500.0      # J/kg/K (assumption)
    cp_char: float = 1100.0        # J/kg/K (assumption)
    char_mass_fraction: float = 0.30   # solid mass left per unit virgin converted
    ln_A: float = 22.2             # Di Blasi & Branca 2001, one-step global
    E_kJ_mol: float = 141.2
    dH_J_kg: float = 0.0           # reaction enthalpy per kg virgin converted, endothermic > 0 (assumption)
    reactive: bool = True
    n_cells: int = 30
    target_conversion: float = 0.95

def rate_constant(T_K, pp: ParticleParams):
    return np.exp(pp.ln_A - pp.E_kJ_mol * 1000.0 / (R_GAS * T_K)) if pp.reactive else 0.0 * T_K

def _props(f, pp):
    yc = pp.char_mass_fraction
    rho_cp = pp.rho_virgin * (f * pp.cp_virgin + yc * (1 - f) * pp.cp_char)
    k = f * pp.k_virgin + (1 - f) * pp.k_char
    return rho_cp, k

def simulate_particle(pp: ParticleParams, t_end_s: float, dt_s: float = 0.5, stop_at_target: bool = False,
                      n_snap: int = 6, n_rec: int = 240) -> dict:
    N = pp.n_cells; Rp = pp.diameter_mm / 2000.0; dr = Rp / N
    rf = dr * np.arange(1, N + 1); r0 = np.r_[0.0, rf[:-1]]
    vol = 4 / 3 * np.pi * (rf**3 - r0**3); area = 4 * np.pi * rf**2
    rc = (r0 + rf) / 2
    T = np.full(N, pp.T0_C + 273.15); f = np.ones(N); Tinf = pp.T_inf_C + 273.15
    nsteps = int(np.ceil(t_end_s / dt_s)); rec_every = max(1, nsteps // n_rec)
    snap_steps = set(np.linspace(0, nsteps, n_snap + 1)[1:].astype(int))
    ts, Tc, Ts, Xm, snaps = [0.0], [T[0] - 273.15], [T[-1] - 273.15], [0.0], []
    t_target = None; t_center = None; rate_prev = np.zeros(N)
    for n in range(1, nsteps + 1):
        rho_cp, k = _props(f, pp)
        kf = 2 * k[:-1] * k[1:] / (k[:-1] + k[1:])               # harmonic face conductivity
        G = kf * area[:-1] / dr                                  # conductance between cells i,i+1
        Gs = area[-1] / (dr / 2 / k[-1] + 1 / pp.h_W_m2K)        # centre of surface cell -> gas
        cap = rho_cp * vol / dt_s
        ab = np.zeros((3, N)); b = cap * T - pp.dH_J_kg * pp.rho_virgin * vol * rate_prev
        ab[1] = cap; ab[1, :-1] += G; ab[1, 1:] += G; ab[1, -1] += Gs
        ab[0, 1:] = -G; ab[2, :-1] = -G; b[-1] += Gs * Tinf
        T = solve_banded((1, 1), ab, b)
        kk = rate_constant(T, pp)
        f_new = f * np.exp(-kk * dt_s)
        rate_prev = (f - f_new) / dt_s                           # 1/s of initial virgin mass
        f = f_new
        X = 1 - float(np.sum(f * vol) / np.sum(vol)); t = n * dt_s
        if t_target is None and X >= pp.target_conversion: t_target = t
        if t_center is None and (Tinf - T[0]) <= 5.0: t_center = t
        if n % rec_every == 0 or n == nsteps:
            ts.append(t); Tc.append(T[0] - 273.15); Ts.append(T[-1] - 273.15); Xm.append(X)
        if n in snap_steps: snaps.append({"t_s": t, "r_mm": rc * 1000, "T_C": T - 273.15, "virgin": f.copy()})
        if stop_at_target and t_target is not None:
            ts.append(t); Tc.append(T[0] - 273.15); Ts.append(T[-1] - 273.15); Xm.append(X); break
    k_inf = float(rate_constant(Tinf, pp)); alpha = pp.k_virgin / (pp.rho_virgin * pp.cp_virgin)
    tau_heat = Rp**2 / (np.pi**2 * alpha)
    tau_kin = (np.log(1 / (1 - pp.target_conversion)) / k_inf) if k_inf > 0 else float("inf")
    return {"t_s": np.array(ts), "T_center_C": np.array(Tc), "T_surface_C": np.array(Ts), "X_mean": np.array(Xm),
            "snapshots": snaps, "t_target_s": t_target, "t_center_within_5K_s": t_center,
            "Biot": pp.h_W_m2K * Rp / pp.k_virgin, "tau_heat_s": float(tau_heat), "tau_kin_s": float(tau_kin),
            "regime": ("heat-transfer limited" if tau_heat > tau_kin else "kinetically limited"),
            "k_at_Tinf_per_s": k_inf, "steps": n, "dt_s": dt_s, "cells": N,
            "reached_target": t_target is not None,
            "kinetics_validity_range_K": (573.0, 708.0),
            "kinetics_extrapolated": not (573.0 <= Tinf <= 708.0)}

def conversion_time_s(htt_C, pp: ParticleParams, t_max_s=14400.0, dt_s=1.0):
    r = simulate_particle(replace(pp, T_inf_C=float(htt_C), n_cells=20), t_max_s, dt_s, stop_at_target=True, n_snap=1, n_rec=10)
    return r["t_target_s"]

def verify_conduction(n_cells=60, fo_points=(0.05, 0.1, 0.2, 0.4)) -> dict:
    """Compare the numerical centre temperature with the analytical sphere solution (Dirichlet surface,
    constant properties, no reaction): theta_c = 2*sum((-1)^(n+1) exp(-n^2 pi^2 Fo))."""
    pp = ParticleParams(diameter_mm=20.0, h_W_m2K=1e9, k_char=0.15, cp_char=1500.0, reactive=False, n_cells=n_cells)
    Rp = pp.diameter_mm / 2000.0; alpha = pp.k_virgin / (pp.rho_virgin * pp.cp_virgin)
    rows = []
    for fo in fo_points:
        t_end = fo * Rp**2 / alpha
        sim = simulate_particle(pp, t_end, dt_s=t_end / 4000, n_snap=1, n_rec=4)
        n = np.arange(1, 400)
        theta = 2 * np.sum((-1.0)**(n + 1) * np.exp(-(n * np.pi)**2 * fo))
        dT = pp.T_inf_C - pp.T0_C
        T_ana = pp.T_inf_C - dT * theta
        # numerical value at r=0 extrapolated from the first cell centre (second order)
        rows.append({"Fo": fo, "T_center_numeric_C": float(sim["T_center_C"][-1]), "T_center_analytic_C": float(T_ana),
                     "error_pct_of_dT": float(abs(sim["T_center_C"][-1] - T_ana) / dT * 100)})
    return {"rows": rows, "max_error_pct": max(r["error_pct_of_dT"] for r in rows)}
