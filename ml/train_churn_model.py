"""Бинарная классификация оттока (churn) — мост от описательной аналитики
(LTV/cohort retention в sql/marts.sql) к предиктивному ML. Датасет: ml/data/churn_features.csv
(см. ml/build_features.py). Обучаются Logistic Regression и Random Forest,
сравниваются по ROC-AUC/PR-AUC, печатается важность признаков обеих моделей.

days_since_last_order НЕ используется как фичи — это то же самое поле,
из которого построен label churned (target leakage)."""
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

if sys.platform == "win32":
    # mlflow печатает emoji ("🏃 View run...") при завершении run — в стандартной
    # cp1252-консоли Windows это падает с UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")

DATA_PATH = Path(__file__).parent / "data" / "churn_features.csv"
PLOTS_DIR = Path(__file__).parent / "plots"

# http://localhost:5501 локально; docker-compose хаба (airflow-common) переопределяет
# на http://mlflow:5501 — тот же сервис в общей compose-сети, см. его README
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5501")
MLFLOW_EXPERIMENT = "churn-prediction"

NUMERIC_FEATURES = ["tenure_days", "total_orders", "total_revenue", "avg_order_value",
                     "first_order_gap_days", "order_frequency"]
CATEGORICAL_FEATURES = ["channel"]

MODELS = {
    "Logistic Regression": LogisticRegression(class_weight="balanced", max_iter=1000),
    "Random Forest": RandomForestClassifier(class_weight="balanced", n_estimators=300, random_state=42),
}


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])


def plot_roc_curves(results: dict, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = {"Logistic Regression": "#1f77b4", "Random Forest": "#2ca02c"}

    for name, r in results.items():
        ax.plot(r["fpr"], r["tpr"], color=colors[name], linewidth=2,
                label=f"{name} (AUC={r['roc_auc']:.2f})")

    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="Random (AUC=0.50)")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC — churn prediction")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Saved {output_path}")


def plot_feature_importance(names: list[str], importances: np.ndarray, title: str, output_path: Path) -> None:
    order = np.argsort(importances)
    fig, ax = plt.subplots(figsize=(7, 0.4 * len(names) + 1.5))
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in importances[order]]
    ax.barh(np.array(names)[order], importances[order], color=colors)
    ax.set_title(title)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Saved {output_path}")


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df["churned"]

    print(f"n={len(df)}, churn rate={y.mean():.1%} (class imbalance handled via class_weight='balanced')\n")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=42
    )

    PLOTS_DIR.mkdir(exist_ok=True)
    roc_results = {}

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    for name, model in MODELS.items():
        with mlflow.start_run(run_name=name):
            pipeline = Pipeline([("preprocess", make_preprocessor()), ("model", model)])
            pipeline.fit(X_train, y_train)

            proba = pipeline.predict_proba(X_test)[:, 1]
            preds = pipeline.predict(X_test)

            roc_auc = roc_auc_score(y_test, proba)
            pr_auc = average_precision_score(y_test, proba)
            accuracy = accuracy_score(y_test, preds)
            fpr, tpr, _ = roc_curve(y_test, proba)
            roc_results[name] = {"fpr": fpr, "tpr": tpr, "roc_auc": roc_auc}

            print(f"=== {name} ===")
            print(f"ROC-AUC: {roc_auc:.3f}  |  PR-AUC: {pr_auc:.3f}")
            print(classification_report(y_test, preds, zero_division=0))

            mlflow.log_param("model", name)
            mlflow.log_param("random_state", 42)
            if name == "Random Forest":
                mlflow.log_param("n_estimators", model.n_estimators)
            mlflow.log_metric("roc_auc", roc_auc)
            mlflow.log_metric("pr_auc", pr_auc)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.sklearn.log_model(pipeline, "model")

            slug = name.lower().replace(" ", "_")
            cm_path = PLOTS_DIR / f"{slug}_confusion_matrix.png"
            fig, ax = plt.subplots(figsize=(5, 5))
            ConfusionMatrixDisplay(confusion_matrix(y_test, preds), display_labels=["retained", "churned"]).plot(ax=ax, cmap="Blues", colorbar=False)
            ax.set_title(f"{name} — confusion matrix")
            fig.tight_layout()
            fig.savefig(cm_path, dpi=150)
            mlflow.log_artifact(str(cm_path))

            feature_names = [n.removeprefix("num__").removeprefix("cat__")
                              for n in pipeline.named_steps["preprocess"].get_feature_names_out()]
            if name == "Random Forest":
                importances = pipeline.named_steps["model"].feature_importances_
                plot_feature_importance(list(feature_names), importances,
                                         "Random Forest — feature importance", PLOTS_DIR / "rf_feature_importance.png")
            else:
                coefs = pipeline.named_steps["model"].coef_[0]
                plot_feature_importance(list(feature_names), coefs,
                                         "Logistic Regression — coefficients (standardized)", PLOTS_DIR / "lr_coefficients.png")

    plot_roc_curves(roc_results, PLOTS_DIR / "roc_curves.png")


if __name__ == "__main__":
    main()
