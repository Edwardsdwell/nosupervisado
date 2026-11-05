"""Métricas de agrupación reutilizables (req. 118): silueta, Davies-Bouldin, Calinski-Harabasz, ruido, inercia."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

from .preprocessing import muestra_densa, rs


def evaluar(X, lab, max_muestras: int = 2000) -> dict:
    """Métricas internas ignorando el ruido (-1). Admite matrices dispersas (submuestreo denso)."""
    lab = np.asarray(lab)
    m = lab != -1
    out = dict(grupos=int(len(np.unique(lab[m]))), ruido=float(1 - m.mean()), silueta=np.nan, davies_bouldin=np.nan, calinski_harabasz=np.nan)
    if out["grupos"] < 2 or m.sum() <= out["grupos"]:
        return out
    Xd, idx = muestra_densa(X[m], max_muestras, rs())
    l = lab[m][idx]
    if len(np.unique(l)) < 2:
        return out
    out["silueta"] = float(silhouette_score(Xd, l, sample_size=min(len(Xd), max_muestras), random_state=rs()))
    out["davies_bouldin"] = float(davies_bouldin_score(Xd, l))
    out["calinski_harabasz"] = float(calinski_harabasz_score(Xd, l))
    return out
