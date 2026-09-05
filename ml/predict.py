"""Loads the trained model and scores P(recovery) for one or more transactions."""

import json
import pickle
from pathlib import Path

import pandas as pd

import sys
sys.path.append(str(Path(__file__).parent))
from features import build_feature_matrix

MODEL_PATH = Path(__file__).parent / "model.pkl"
ENCODER_PATH = Path(__file__).parent / "encoder_categories.json"

_model = None
_encoder_categories = None


def _load():
    global _model, _encoder_categories
    if _model is None:
        with open(MODEL_PATH, "rb") as f:
            _model = pickle.load(f)
        with open(ENCODER_PATH) as f:
            _encoder_categories = json.load(f)
    return _model, _encoder_categories


def predict_recovery_probability(transaction: dict) -> float:
    """transaction: dict of the raw feature columns for one payment row."""
    model, encoder_categories = _load()
    df = pd.DataFrame([transaction])
    X, _ = build_feature_matrix(df, encoder_categories=encoder_categories)
    # Align columns exactly to training order (any missing dummy = 0)
    X = X.reindex(columns=list(model.feature_names_in_), fill_value=0)
    return float(model.predict_proba(X)[:, 1][0])


def predict_recovery_probability_batch(df: pd.DataFrame) -> pd.Series:
    model, encoder_categories = _load()
    X, _ = build_feature_matrix(df, encoder_categories=encoder_categories)
    X = X.reindex(columns=list(model.feature_names_in_), fill_value=0)
    return pd.Series(model.predict_proba(X)[:, 1], index=df.index)


ALL_METHODS = ["card", "upi", "netbanking", "wallet", "emi"]


def predict_recovery_by_method(transaction: dict, methods=None) -> dict:
    """
    Instead of scoring only the method the payment actually failed on, this
    asks the SAME trained model "what if this customer had paid with method
    X instead?" for every method, holding everything else about the
    transaction (amount, customer history, timing, etc.) fixed.

    This lets the agent choose a payment method by genuine expected value
    (P(recovery) x amount) rather than a hand-tuned threshold rule.

    Returns: {"card": 0.41, "upi": 0.77, "netbanking": 0.22, ...}

    Caveat: the model was trained on real (customer, method) pairs, so
    swapping method on a row whose upi_success_rate/card_success_rate were
    computed for the ORIGINAL method is an extrapolation for methods the
    customer rarely uses -- treat low-history methods' scores as noisier.
    """
    methods = methods or ALL_METHODS
    model, encoder_categories = _load()
    rows = []
    for m in methods:
        row = dict(transaction)
        row["method"] = m
        rows.append(row)
    df = pd.DataFrame(rows)
    X, _ = build_feature_matrix(df, encoder_categories=encoder_categories)
    X = X.reindex(columns=list(model.feature_names_in_), fill_value=0)
    probs = model.predict_proba(X)[:, 1]
    return {m: float(p) for m, p in zip(methods, probs)}
