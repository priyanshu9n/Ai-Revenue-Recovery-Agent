"""Shared feature engineering for the recovery-probability model."""

import pandas as pd

NUMERIC_FEATURES = [
    "amount",
    "attempt_number",
    "previous_success_rate",
    "previous_failure_rate",
    "upi_success_rate",
    "card_success_rate",
    "time_since_last_attempt_min",
    "hour",
    "day_of_week",
    "checkout_duration_sec",
]

CATEGORICAL_FEATURES = ["method", "root_cause", "customer_value_tier"]

TARGET = "recovered"


def load_dataset(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def build_feature_matrix(df: pd.DataFrame, encoder_categories: dict = None):
    """
    One-hot encodes categorical columns. If encoder_categories is given
    (from training), applies the same categories at inference time so
    the evaluation/serving matrix has identical columns to training.
    """
    df = df.copy()
    if encoder_categories is None:
        encoder_categories = {c: sorted(df[c].dropna().unique().tolist()) for c in CATEGORICAL_FEATURES}

    frames = [df[NUMERIC_FEATURES].reset_index(drop=True)]
    for col in CATEGORICAL_FEATURES:
        cats = encoder_categories[col]
        dummies = pd.DataFrame(
            {f"{col}__{cat}": (df[col] == cat).astype(int) for cat in cats}
        ).reset_index(drop=True)
        frames.append(dummies)

    X = pd.concat(frames, axis=1)
    return X, encoder_categories
