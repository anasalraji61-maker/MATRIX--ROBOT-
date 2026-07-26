"""NumPy-only inference for Brain — no PyTorch required at runtime."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from ml.features import extract_features, feature_dim

logger = logging.getLogger("matrix.ml.inference")


class NumpySignalModel:
    """3-layer MLP matching ml/model.py SignalNet (dropout disabled at inference)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.meta = payload.get("meta") or {}
        self.layers: list[dict[str, np.ndarray]] = payload["layers"]
        self.feature_names = tuple(payload.get("feature_names") or ())

    @classmethod
    def load(cls, path: str | Path) -> NumpySignalModel:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        return cls(payload)

    def predict_proba(self, features: list[float] | np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        h = x
        for i, layer in enumerate(self.layers):
            h = h @ layer["W"] + layer["b"]
            if i < len(self.layers) - 1:
                h = np.maximum(0.0, h)
        logit = float(h.reshape(-1)[0])
        return float(1.0 / (1.0 + np.exp(-logit)))


def export_torch_to_json(pt_path: str | Path, json_path: str | Path | None = None) -> Path:
    """Convert a .pt checkpoint to Brain-friendly JSON weights."""
    import torch

    from ml.model import build_model

    pt_path = Path(pt_path)
    payload = torch.load(pt_path, map_location="cpu", weights_only=False)
    meta = payload.get("meta") or {}
    hidden = int(meta.get("hidden", 32))
    dropout = float(meta.get("dropout", 0.15))
    model = build_model(hidden=hidden, dropout=dropout)
    model.load_state_dict(payload["state_dict"])
    model.eval()

    layers: list[dict[str, list]] = []
    state = model.state_dict()
    for idx in (0, 3, 6):
        w = state[f"net.{idx}.weight"].cpu().numpy().T  # (in, out)
        b = state[f"net.{idx}.bias"].cpu().numpy()
        layers.append({"W": w.tolist(), "b": b.tolist()})

    out = json_path or pt_path.with_suffix(".json")
    doc = {
        "format": "matrix_signal_mlp_v1",
        "n_features": feature_dim(),
        "feature_names": list(meta.get("feature_names") or []),
        "layers": layers,
        "meta": meta,
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(doc, f)
    logger.info("Exported ML model JSON → %s", out)
    return out


def export_model_json(model, json_path: str | Path, meta: dict | None = None) -> Path:
    """Export weights from a live PyTorch module."""
    import torch

    json_path = Path(json_path)
    layers: list[dict[str, list]] = []
    state = model.state_dict()
    for idx in (0, 3, 6):
        w = state[f"net.{idx}.weight"].detach().cpu().numpy().T
        b = state[f"net.{idx}.bias"].detach().cpu().numpy()
        layers.append({"W": w.tolist(), "b": b.tolist()})

    doc = {
        "format": "matrix_signal_mlp_v1",
        "n_features": feature_dim(),
        "feature_names": list((meta or {}).get("feature_names") or []),
        "layers": layers,
        "meta": meta or {},
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(doc, f)
    return json_path
