"""Train PyTorch signal classifier with MLflow experiment tracking."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from ml.dataset import Dataset
from ml.features import FEATURE_NAMES
from ml.model import build_model, save_checkpoint

logger = logging.getLogger("matrix.ml.trainer")

_DEFAULT_ML_DIR = Path(os.environ.get("MATRIX_ML_DIR", "C:/MatrixML"))


def default_mlflow_uri() -> str:
    """SQLite backend — works with MLflow 3+ (file:// mlruns is deprecated)."""
    if os.environ.get("MLFLOW_TRACKING_URI"):
        return os.environ["MLFLOW_TRACKING_URI"]
    _DEFAULT_ML_DIR.mkdir(parents=True, exist_ok=True)
    db = _DEFAULT_ML_DIR / "mlflow.db"
    return f"sqlite:///{db.as_posix()}"


def _configure_mlflow(uri: str) -> None:
    import mlflow

    if uri.startswith("file://"):
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(uri)


def _require_ml():
    try:
        import torch  # noqa: F401
        import mlflow  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "PyTorch/MLflow not installed. On VPS run:\n"
            "  C:\\MatrixVenv\\Scripts\\pip install -r requirements-ml.txt"
        ) from e


def _split(X: np.ndarray, y: np.ndarray, val_ratio: float = 0.2, seed: int = 42):
    n = len(y)
    if n < 5:
        return X, y, X[:0], y[:0]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    n_val = max(1, int(n * val_ratio))
    val_idx, train_idx = idx[:n_val], idx[n_val:]
    return X[train_idx], y[train_idx], X[val_idx], y[val_idx]


def _metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    y_pred = (y_prob >= 0.5).astype(int)
    acc = float((y_pred == y_true).mean()) if len(y_true) else 0.0
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "accuracy": round(acc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


def train_classifier(
    dataset: Dataset,
    *,
    symbols: list[str],
    bars: int,
    timeframe: str,
    epochs: int = 40,
    lr: float = 1e-3,
    hidden: int = 32,
    dropout: float = 0.15,
    batch_size: int = 16,
    mlflow_uri: str | None = None,
    experiment: str = "matrix_signal_classifier",
    run_name: str | None = None,
) -> dict[str, Any]:
    """Train MLP, log to MLflow, return summary dict."""
    _require_ml()
    import mlflow
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    if dataset.n_samples < 8:
        return {
            "ok": False,
            "error": f"Need ≥8 labeled trades, got {dataset.n_samples}",
            "dataset": dataset.to_dict(),
        }

    uri = mlflow_uri or default_mlflow_uri()
    _configure_mlflow(uri)
    mlflow.set_experiment(experiment)

    X_train, y_train, X_val, y_val = _split(dataset.X, dataset.y)
    device = torch.device("cpu")

    model = build_model(hidden=hidden, dropout=dropout).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss()

    train_loader = DataLoader(
        TensorDataset(
            torch.tensor(X_train, dtype=torch.float32),
            torch.tensor(y_train, dtype=torch.float32),
        ),
        batch_size=min(batch_size, len(y_train)),
        shuffle=True,
    )

    best_val_loss = float("inf")
    best_state = None

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "symbols": ",".join(symbols),
            "bars": bars,
            "timeframe": timeframe,
            "epochs": epochs,
            "lr": lr,
            "hidden": hidden,
            "dropout": dropout,
            "n_features": len(FEATURE_NAMES),
            "device": "cpu",
        })
        mlflow.log_param("dataset", dataset.to_dict())

        for epoch in range(epochs):
            model.train()
            epoch_loss = 0.0
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                opt.zero_grad()
                logits = model(xb)
                loss = loss_fn(logits, yb)
                loss.backward()
                opt.step()
                epoch_loss += loss.item() * len(yb)
            epoch_loss /= max(len(y_train), 1)

            model.eval()
            with torch.no_grad():
                if len(y_val):
                    val_logits = model(torch.tensor(X_val, dtype=torch.float32).to(device))
                    val_loss = float(loss_fn(val_logits, torch.tensor(y_val, dtype=torch.float32).to(device)))
                    val_prob = torch.sigmoid(val_logits).cpu().numpy()
                    val_m = _metrics(y_val.astype(int), val_prob)
                else:
                    val_loss = epoch_loss
                    val_m = {"accuracy": 0.0, "precision": 0.0, "recall": 0.0}

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if (epoch + 1) % 10 == 0 or epoch == 0:
                mlflow.log_metrics({
                    "train_loss": round(epoch_loss, 5),
                    "val_loss": round(val_loss, 5),
                    **{f"val_{k}": v for k, v in val_m.items()},
                }, step=epoch)

        if best_state:
            model.load_state_dict(best_state)

        model.eval()
        with torch.no_grad():
            all_logits = model(torch.tensor(dataset.X, dtype=torch.float32).to(device))
            all_prob = torch.sigmoid(all_logits).cpu().numpy()
        train_m = _metrics(dataset.y.astype(int), all_prob)

        mlflow.log_metrics({
            "final_train_accuracy": train_m["accuracy"],
            "final_train_precision": train_m["precision"],
            "final_train_recall": train_m["recall"],
            "best_val_loss": round(best_val_loss, 5),
            "dataset_win_rate": dataset.to_dict()["win_rate"],
        })

        out_dir = Path(os.environ.get("MATRIX_ML_MODEL_DIR", "ml_models"))
        out_dir.mkdir(parents=True, exist_ok=True)
        sym_tag = "_".join(s.replace("/", "") for s in symbols[:3])
        ckpt_path = out_dir / f"signal_{sym_tag}_{bars}bars.pt"
        meta = {
            "symbols": symbols,
            "bars": bars,
            "timeframe": timeframe,
            "hidden": hidden,
            "dropout": dropout,
            "feature_names": list(FEATURE_NAMES),
            "metrics": train_m,
            "dataset": dataset.to_dict(),
        }
        save_checkpoint(model, ckpt_path, meta=meta)
        from ml.inference import export_model_json

        json_path = ckpt_path.with_suffix(".json")
        export_model_json(model, json_path, meta=meta)
        mlflow.log_artifact(str(json_path))
        mlflow.log_artifact(str(ckpt_path))
        run_id = mlflow.active_run().info.run_id

    return {
        "ok": True,
        "run_id": run_id,
        "mlflow_uri": uri,
        "checkpoint": str(ckpt_path),
        "model_json": str(json_path),
        "metrics": train_m,
        "dataset": dataset.to_dict(),
        "best_val_loss": round(best_val_loss, 5),
    }
