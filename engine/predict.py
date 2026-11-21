"""Data-driven biochar property predictor trained on the bundled literature dataset.

Honest scope: a random forest fitted to published lab/pilot slow-pyrolysis observations.
It interpolates the literature; it is not a mechanistic model and not validated for any
specific reactor. Cross-validation is grouped by publication to avoid leakage.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline

DATA = Path(__file__).resolve().parent.parent / "data" / "biochar_production_characteristics_202404.csv"
CLASSES = ["woody", "herbaceous", "shells and kernels", "manure", "kitchen waste", "sewage sludge"]
# Fixed_C and O_C were tested and dropped: grouped CV R2 ~ 0 (no skill beyond the mean).
TARGETS = {
    "Yield": "Char yield (wt% of dry feed)",
    "C": "Carbon in char (wt%)",
    "Ash": "Ash (wt%)",
    "H_C": "H/C molar ratio",
}
FEATURES = ["HTT", "log_duration", "heating_rate"] + [f"cls_{c}" for c in CLASSES]


def load_dataset(path: Path = DATA) -> pd.DataFrame:
    d = pd.read_csv(path, na_values=["NA", "", "um"])
    for c in ["HTT", "Pyrolysis_duration", "Heating_rate", *TARGETS]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d.Pyrolysis_type == "slow") & d.Feedstock_class.isin(CLASSES) & d.HTT.between(250, 900)].copy()
    for c in ["Yield", "C", "Fixed_C", "Ash"]:
        d.loc[~d[c].between(0, 100), c] = np.nan
    d.loc[~d.H_C.between(0, 3), "H_C"] = np.nan
    d.loc[~d.O_C.between(0, 2), "O_C"] = np.nan
    d["Title"] = d["Title"].fillna("id_" + d["ID"].astype(str))
    return d.reset_index(drop=True)


def make_features(d: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({"HTT": d["HTT"].astype(float),
                      "log_duration": np.log1p(d["Pyrolysis_duration"].astype(float)),
                      "heating_rate": d["Heating_rate"].astype(float)})
    for c in CLASSES:
        X[f"cls_{c}"] = (d["Feedstock_class"] == c).astype(float)
    return X[FEATURES]


def _model(seed=0):
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                         RandomForestRegressor(n_estimators=200, min_samples_leaf=8, max_features=0.6,
                                               n_jobs=-1, random_state=seed))


@dataclass
class BiocharPredictor:
    models: dict = field(default_factory=dict)
    cv: dict = field(default_factory=dict)
    n_obs: dict = field(default_factory=dict)
    ranges: dict = field(default_factory=dict)
    data: pd.DataFrame | None = None
    class_means: dict = field(default_factory=dict)
    global_means: dict = field(default_factory=dict)
    model_strategy: dict = field(default_factory=dict)

    @classmethod
    def train(cls, run_cv: bool = True) -> "BiocharPredictor":
        d = load_dataset()
        self = cls(data=d)
        X = make_features(d)
        self.ranges = {c: (float(d[d.Feedstock_class == c].HTT.min()), float(d[d.Feedstock_class == c].HTT.max()))
                       for c in CLASSES if (d.Feedstock_class == c).any()}
        for t in TARGETS:
            m = d[t].notna()
            self.class_means[t] = d.loc[m].groupby("Feedstock_class")[t].mean().to_dict()
            self.global_means[t] = float(d.loc[m, t].mean())
            self.model_strategy[t] = "random_forest"
            self.n_obs[t] = int(m.sum())
            self.models[t] = _model().fit(X[m], d.loc[m, t])
            if run_cv:
                groups = d.loc[m, "Title"].values
                Xt, yt = X[m].reset_index(drop=True), d.loc[m, t].reset_index(drop=True)
                oof = np.zeros(len(yt)); base = np.zeros(len(yt))
                for tr, te in GroupKFold(n_splits=5).split(Xt, yt, groups):
                    oof[te] = _model().fit(Xt.iloc[tr], yt.iloc[tr]).predict(Xt.iloc[te])
                    cls_mean = d.loc[m].reset_index(drop=True).iloc[tr].groupby("Feedstock_class")[t].mean()
                    glob = yt.iloc[tr].mean()
                    base[te] = d.loc[m].reset_index(drop=True).iloc[te].Feedstock_class.map(cls_mean).fillna(glob).values
                rf_r2 = float(r2_score(yt, oof)); baseline_r2 = float(r2_score(yt, base))
                self.cv[t] = {"r2": rf_r2, "mae": float(mean_absolute_error(yt, oof)),
                              "baseline_r2": baseline_r2, "n": int(m.sum()),
                              "papers": int(pd.Series(groups).nunique())}
                # Prefer the simpler class-mean baseline when the forest has worse grouped-CV R².
                if baseline_r2 > rf_r2:
                    self.model_strategy[t] = "feedstock_class_mean"
        return self

    def predict(self, feedstock_class: str, htt: float, duration_min: float = 60.0,
                heating_rate: float = 10.0) -> dict:
        row = pd.DataFrame([{"HTT": htt, "Pyrolysis_duration": duration_min, "Heating_rate": heating_rate,
                             "Feedstock_class": feedstock_class}])
        X = make_features(row)
        out = {}
        for t, mdl in self.models.items():
            if self.model_strategy.get(t) == "feedstock_class_mean":
                value = self.class_means.get(t, {}).get(feedstock_class, self.global_means[t])
                out[t] = {"mean": float(value), "std": 0.0}
            else:
                imp, rf = mdl.steps[0][1], mdl.steps[1][1]
                Xi = imp.transform(X)
                per_tree = np.array([e.predict(Xi)[0] for e in rf.estimators_])
                out[t] = {"mean": float(per_tree.mean()), "std": float(per_tree.std())}
        lo, hi = self.ranges.get(feedstock_class, (np.nan, np.nan))
        out["extrapolating"] = bool(not (lo <= htt <= hi))
        return out

    def predict_grid(self, feedstock_class, htts, durations, rates) -> pd.DataFrame:
        """Fast batch mean prediction over a full factorial grid (no per-tree spread)."""
        g = pd.MultiIndex.from_product([htts, durations, rates], names=["HTT", "Pyrolysis_duration", "Heating_rate"]).to_frame(index=False)
        g["Feedstock_class"] = feedstock_class
        X = make_features(g)
        for t, mdl in self.models.items():
            if self.model_strategy.get(t) == "feedstock_class_mean":
                g[t] = self.class_means.get(t, {}).get(feedstock_class, self.global_means[t])
            else:
                g[t] = mdl.predict(X)
        lo, hi = self.ranges.get(feedstock_class, (np.nan, np.nan))
        g["extrapolating"] = ~g.HTT.between(lo, hi)
        return g

    def curve(self, feedstock_class, htts, duration_min=60.0, heating_rate=10.0, target="Yield"):
        mu, sd = [], []
        for h in htts:
            r = self.predict(feedstock_class, float(h), duration_min, heating_rate)[target]
            mu.append(r["mean"]); sd.append(r["std"])
        return np.array(mu), np.array(sd)


def stable_fraction_from_hc(hc: float) -> float:
    """Screening permanence proxy: fraction of char carbon assumed stable >100 y, from molar H/C.

    SHAPE follows the widely used quality classes (H/Corg < 0.4 high, 0.4-0.7 medium, > 0.7 low,
    where 0.7 is the EBC/IBI quality limit). The NUMERIC values are placeholders chosen for
    screening and should be replaced by a published BC+100 regression before any claim is made.
    """
    pts = [(0.0, 0.90), (0.4, 0.85), (0.7, 0.65), (1.0, 0.40), (1.5, 0.20)]
    xs, ys = zip(*pts)
    return float(np.interp(hc, xs, ys))
