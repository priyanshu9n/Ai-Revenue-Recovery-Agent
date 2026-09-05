"""
Trains P(recovery) - the probability a given failed payment will be
recovered - using XGBoost, on the Razorpay-schema demo dataset.

Run: python train.py
Outputs: model.pkl, encoder_categories.json, metrics.json
"""

import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, confusion_matrix
from xgboost import XGBClassifier

import sys
sys.path.append(str(Path(__file__).parent))
from features import load_dataset, build_feature_matrix, TARGET

DATA_PATH = Path(__file__).parent.parent / "data" / "razorpay_demo_payments.csv"
MODEL_PATH = Path(__file__).parent / "model.pkl"
ENCODER_PATH = Path(__file__).parent / "encoder_categories.json"
METRICS_PATH = Path(__file__).parent / "metrics.json"


def main():
    df = load_dataset(DATA_PATH)
    X, encoder_categories = build_feature_matrix(df)
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_test, preds).ravel()

    # Business/calibration view: bucket predictions and check actual
    # recovery rate rises with predicted probability (Day-4 requirement).
    bucket_edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    buckets = []
    for lo, hi in zip(bucket_edges[:-1], bucket_edges[1:]):
        mask = (proba >= lo) & (proba < hi if hi < 1.0 else proba <= hi)
        n = int(mask.sum())
        actual_rate = float(y_test[mask].mean()) if n > 0 else None
        buckets.append({"range": f"{int(lo*100)}-{int(hi*100)}%", "n": n, "actual_recovery_rate": actual_rate})

    metrics = {
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "pr_auc": float(average_precision_score(y_test, proba)),
        "precision": float(precision_score(y_test, preds)),
        "recall": float(recall_score(y_test, preds)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "calibration_buckets": buckets,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_columns": list(X.columns),
    }

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(ENCODER_PATH, "w") as f:
        json.dump(encoder_categories, f, indent=2)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    print(f"\nSaved model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
