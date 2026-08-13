"""Small MLP for win/loss classification (CPU-friendly)."""
from __future__ import annotations

from pathlib import Path

from ml.features import feature_dim


def build_model(hidden: int = 32, dropout: float = 0.15):
    import torch
    import torch.nn as nn

    n_in = feature_dim()

    class SignalNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(n_in, hidden),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden, hidden // 2 or 8),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden // 2 or 8, 1),
            )

        def forward(self, x):
            return self.net(x).squeeze(-1)

    return SignalNet()


def save_checkpoint(model, path: str | Path, meta: dict | None = None) -> None:
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"state_dict": model.state_dict(), "meta": meta or {}}
    torch.save(payload, path)


def load_checkpoint(path: str | Path):
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    hidden = int((payload.get("meta") or {}).get("hidden", 32))
    dropout = float((payload.get("meta") or {}).get("dropout", 0.15))
    model = build_model(hidden=hidden, dropout=dropout)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, payload.get("meta") or {}
