"""
Machine Learning Meta-Classifier & Dual-Model Ensemble Brain.
Implements:
1. Dual-Model Architecture:
   - Model 1: Random Forest Classifier (150 Trees)
   - Model 2: XGBoost / HistGradientBoosting Classifier (150 Iterations)
2. Exact 5-Stage ML Evolution Timeline:
   - < 50 Trades    : Rules 100% / ML 0%  (Data Collection Phase)
   - 50 - 200 Trades: Rules 70%  / ML 30% (Learning Phase)
   - 200 - 500 Trades: Rules 60% / ML 40% (Improving Phase)
   - 500 - 1000 Trades: Rules 50% / ML 50% (Equal Partnership Phase)
   - 1000+ Trades   : Rules 40%  / ML 60% (Smart System / High Responsibility)
3. 80/20 Train/Test Validation with Accuracy, F1, and ROC-AUC metrics
4. Combined Ensemble Prediction: P_Ensemble = (P_RF + P_XGB) / 2
5. Automated Hidden Pattern Discovery Engine
"""

import os
import math
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier

try:
    import xgboost as xgb
    HAS_XGB = True
except (ImportError, OSError, Exception):
    HAS_XGB = False

from config import (
    DATA_DIR,
    ML_CONFIDENCE_THRESHOLD,
    MIN_SAMPLES_FOR_TRAIN,
    RETRAIN_TRADE_INTERVAL
)
from database import (
    get_training_dataset,
    log_model_retraining,
    get_closed_trades,
    get_connection
)
from feature_extractor import FEATURE_COLUMNS


RF_MODEL_PATH = DATA_DIR / "random_forest.joblib"
XGB_MODEL_PATH = DATA_DIR / "xgboost.joblib"
SCALER_PATH = DATA_DIR / "feature_scaler.joblib"


class MLDualEnsembleBrain:
    """
    Dual-Model ML Meta-Classifier combining Random Forest + XGBoost / HistGradientBoosting.
    """

    def __init__(self):
        self.rf_model = None
        self.xgb_model = None
        self.scaler = None
        self.is_trained = False
        self.last_retrain_trade_count = 0
        self.discovered_patterns = []
        self.rf_accuracy = 0.0
        self.xgb_accuracy = 0.0
        self.ensemble_accuracy = 0.0
        self.load_models()

    def load_models(self) -> bool:
        """Loads persisted Random Forest, XGBoost/HistGBDT, and Scaler from disk."""
        if RF_MODEL_PATH.exists() and XGB_MODEL_PATH.exists() and SCALER_PATH.exists():
            try:
                self.rf_model = joblib.load(RF_MODEL_PATH)
                self.xgb_model = joblib.load(XGB_MODEL_PATH)
                self.scaler = joblib.load(SCALER_PATH)
                self.is_trained = True

                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT val_accuracy, val_f1, val_roc_auc FROM model_retraining_logs ORDER BY id DESC LIMIT 1")
                    row = cursor.fetchone()
                    if row:
                        self.ensemble_accuracy = float(row["val_accuracy"])
                        self.rf_accuracy = float(row["val_accuracy"])
                        self.xgb_accuracy = float(row["val_accuracy"])
                    conn.close()
                except Exception:
                    pass

                return True
            except Exception as e:
                print(f"[ML Brain] Notice loading existing models: {e}")
                self.is_trained = False
        return False

    def _align_features(self, df_or_dict: Any) -> pd.DataFrame:
        """Ensures exact matching of feature columns in fixed tabular order."""
        if isinstance(df_or_dict, dict):
            df = pd.DataFrame([df_or_dict])
        else:
            df = df_or_dict.copy()

        for col in FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = 0.0

        return df[FEATURE_COLUMNS].fillna(0.0)

    def get_adaptive_weight(self, total_samples: int) -> Tuple[float, float, str]:
        """
        Complete 5-Stage ML Evolution Timeline:
        - BEFORE 50 TRADES   : Rules 100% / ML 0%  (Data Collection Phase)
        - 50 TO 200 TRADES   : Rules 70%  / ML 30% (Learning Phase)
        - 200 TO 500 TRADES  : Rules 60%  / ML 40% (Improving Phase)
        - 500 TO 1000 TRADES : Rules 50%  / ML 50% (Equal Partnership Phase)
        - ABOVE 1000 TRADES  : Rules 40%  / ML 60% (Smart System / High Responsibility)
        Returns: (rules_weight, ml_weight, phase_name)
        """
        if total_samples < 50:
            return 1.00, 0.00, "1. Collecting Data Phase (Rules 100% / ML Inactive)"
        elif total_samples < 200:
            return 0.70, 0.30, "2. Learning Phase (Rules 70% + ML 30%)"
        elif total_samples < 500:
            return 0.60, 0.40, "3. Improving Phase (Rules 60% + ML 40%)"
        elif total_samples < 1000:
            return 0.50, 0.50, "4. Equal Partnership Phase (Rules 50% + ML 50%)"
        else:
            return 0.40, 0.60, "5. Smart System Elite Phase (Rules 40% + ML 60%)"

    def train(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, Any]:
        """
        Trains both Random Forest and XGBoost on historical trade outcomes (80/20 split).
        """
        if len(X) < MIN_SAMPLES_FOR_TRAIN:
            return {
                "success": False,
                "message": f"Insufficient trade history ({len(X)}/{MIN_SAMPLES_FOR_TRAIN} trades). Need 50+ trades."
            }

        X_clean = self._align_features(X)

        # 80/20 Train/Test split
        stratify = y if y.nunique() > 1 and y.value_counts().min() >= 2 else None
        X_train, X_test, y_train, y_test = train_test_split(
            X_clean, y, test_size=0.20, random_state=42, stratify=stratify
        )

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # -----------------------------------------------------------------
        # STEP 4: Train Random Forest Model (150 Trees)
        # -----------------------------------------------------------------
        rf = RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_split=3,
            random_state=42
        )
        rf.fit(X_train_scaled, y_train)
        rf_preds = rf.predict(X_test_scaled)
        rf_acc = accuracy_score(y_test, rf_preds)

        # -----------------------------------------------------------------
        # STEP 5: Train XGBoost / HistGradientBoosting Model
        # -----------------------------------------------------------------
        if HAS_XGB:
            xgb_clf = xgb.XGBClassifier(
                n_estimators=150,
                max_depth=5,
                learning_rate=0.03,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric='logloss'
            )
        else:
            xgb_clf = HistGradientBoostingClassifier(
                max_iter=150,
                max_depth=5,
                learning_rate=0.03,
                random_state=42
            )

        xgb_clf.fit(X_train_scaled, y_train)
        xgb_preds = xgb_clf.predict(X_test_scaled)
        xgb_acc = accuracy_score(y_test, xgb_preds)

        # -----------------------------------------------------------------
        # STEP 6: Combined Ensemble Evaluation
        # -----------------------------------------------------------------
        rf_probs = rf.predict_proba(X_test_scaled)[:, 1]
        xgb_probs = xgb_clf.predict_proba(X_test_scaled)[:, 1]
        ensemble_probs = (rf_probs + xgb_probs) / 2.0
        ensemble_preds = (ensemble_probs >= 0.50).astype(int)

        ensemble_acc = accuracy_score(y_test, ensemble_preds)
        val_f1 = f1_score(y_test, ensemble_preds, zero_division=0)
        try:
            val_roc = roc_auc_score(y_test, ensemble_probs)
        except Exception:
            val_roc = 0.50

        # Save artifacts
        joblib.dump(rf, RF_MODEL_PATH)
        joblib.dump(xgb_clf, XGB_MODEL_PATH)
        joblib.dump(scaler, SCALER_PATH)

        self.rf_model = rf
        self.xgb_model = xgb_clf
        self.scaler = scaler
        self.is_trained = True
        self.rf_accuracy = round(float(rf_acc), 4)
        self.xgb_accuracy = round(float(xgb_acc), 4)
        self.ensemble_accuracy = round(float(ensemble_acc), 4)
        self.last_retrain_trade_count = len(get_closed_trades())

        self.discovered_patterns = self.discover_hidden_patterns(X_clean, y)

        log_model_retraining(
            total_samples=len(X),
            train_acc=round(float(rf.score(X_train_scaled, y_train)), 4),
            val_acc=self.ensemble_accuracy,
            val_f1=round(float(val_f1), 4),
            val_roc_auc=round(float(val_roc), 4),
            notes=f"Dual Ensemble (RF Acc: {rf_acc*100:.1f}%, XGB Acc: {xgb_acc*100:.1f}%)"
        )

        return {
            "success": True,
            "total_samples": len(X),
            "rf_accuracy": self.rf_accuracy,
            "xgb_accuracy": self.xgb_accuracy,
            "ensemble_accuracy": self.ensemble_accuracy,
            "val_f1": round(float(val_f1), 4),
            "val_roc_auc": round(float(val_roc), 4),
            "discovered_patterns": self.discovered_patterns
        }

    def predict_dual_ensemble(
        self,
        features: Dict[str, Any],
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Step-by-step Dual Prediction Phase:
        1. Packages current market conditions
        2. Normalizes numerical features
        3. Runs Random Forest + XGBoost / HistGBDT
        4. Calculates combined ensemble probability
        5. Validates against target confidence threshold (73%, 80%, or 87%)
        """
        target_thresh = threshold if threshold is not None else ML_CONFIDENCE_THRESHOLD
        if not self.is_trained or self.rf_model is None or self.xgb_model is None:
            return {
                "rf_prob": 0.50,
                "xgb_prob": 0.50,
                "ensemble_prob": 0.50,
                "is_approved": True,
                "status": "Awaiting initial training data",
                "reason": "ML Ensemble initializing"
            }

        try:
            X_df = pd.DataFrame([features])
            for col in FEATURE_COLUMNS:
                if col not in X_df.columns:
                    X_df[col] = 0.0

            X_df = X_df[FEATURE_COLUMNS].fillna(0.0)
            X_scaled = self.scaler.transform(X_df)

            rf_p = float(self.rf_model.predict_proba(X_scaled)[0, 1])
            xgb_p = float(self.xgb_model.predict_proba(X_scaled)[0, 1])
            ensemble_p = (rf_p + xgb_p) / 2.0

            is_approved = ensemble_p >= target_thresh

            reason = (
                f"ML Dual Ensemble Approved: {ensemble_p * 100:.1f}% Win Probability "
                f"(RF: {rf_p*100:.1f}%, XGB: {xgb_p*100:.1f}% >= {target_thresh*100:.0f}%)"
                if is_approved else
                f"ML Dual Ensemble Filtered: Low Win Probability {ensemble_p * 100:.1f}% "
                f"(RF: {rf_p*100:.1f}%, XGB: {xgb_p*100:.1f}% < {target_thresh*100:.0f}%)"
            )

            return {
                "rf_prob": round(rf_p, 4),
                "xgb_prob": round(xgb_p, 4),
                "ensemble_prob": round(ensemble_p, 4),
                "is_approved": is_approved,
                "status": "Active Dual Ensemble",
                "reason": reason
            }
        except Exception as e:
            return {
                "rf_prob": 0.50,
                "xgb_prob": 0.50,
                "ensemble_prob": 0.50,
                "is_approved": True,
                "status": "Fallback",
                "reason": f"Inference warning: {e}"
            }

    def evaluate_trade(
        self,
        features: Dict[str, Any],
        threshold: float = ML_CONFIDENCE_THRESHOLD
    ) -> Tuple[bool, float, str]:
        """Dual Decision Gate wrapper for strategy module."""
        res = self.predict_dual_ensemble(features)
        return res["is_approved"], res["ensemble_prob"], res["reason"]

    def discover_hidden_patterns(self, X: pd.DataFrame, y: pd.Series) -> List[str]:
        """Discovers non-obvious quantitative patterns from historical trade data."""
        insights = []
        df_all = X.copy()
        df_all["is_win"] = y.values

        # 1. Day of Week Patterns
        if "day_of_week" in df_all.columns:
            dow_wins = df_all.groupby("day_of_week")["is_win"].mean()
            best_dow = int(dow_wins.idxmax())
            dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            if dow_wins.max() >= 0.60:
                insights.append(f"Highest Win Rate Day: {dow_names[best_dow]} ({dow_wins.max()*100:.1f}% Win Rate)")

        # 2. RSI Sweet Spot with Order Blocks
        if "rsi_14" in df_all.columns:
            rsi_sweet = df_all[(df_all["rsi_14"] >= 35) & (df_all["rsi_14"] <= 48)]
            if len(rsi_sweet) >= 5:
                sweet_wr = rsi_sweet["is_win"].mean()
                if sweet_wr >= 0.60:
                    insights.append(f"RSI 35-48 Sweet Spot: {sweet_wr*100:.1f}% Historical Win Rate ({len(rsi_sweet)} setups)")

        # 3. Confluence Score Win Rate
        if "confluence_score" in df_all.columns:
            high_score = df_all[df_all["confluence_score"] >= 170]
            if len(high_score) >= 3:
                high_wr = high_score["is_win"].mean()
                insights.append(f"Score 170+ (Perfect Setups): {high_wr*100:.1f}% Win Rate")

        if not insights:
            insights.append("Learning baseline trade distribution across market sessions.")

        return insights

    def check_and_retrain(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """Automated continuous retraining trigger when new trade data accumulates."""
        closed_trades = get_closed_trades()
        current_count = len(closed_trades)

        if current_count < MIN_SAMPLES_FOR_TRAIN:
            return None

        if force or (current_count - self.last_retrain_trade_count) >= RETRAIN_TRADE_INTERVAL or not self.is_trained:
            print(f"[ML Brain Retraining Trigger] {current_count} total trades in journal. Updating Dual Ensemble (Continuous Learning Active)...")
            X, y = get_training_dataset()
            if not X.empty and len(y) >= MIN_SAMPLES_FOR_TRAIN:
                return self.train(X, y)
        return None

    def get_feature_importances(self) -> Dict[str, float]:
        """Returns feature importance ranking from Random Forest."""
        if not self.is_trained or self.rf_model is None:
            return {}

        try:
            importances = self.rf_model.feature_importances_
            feat_imp = {
                col: round(float(imp), 4)
                for col, imp in zip(FEATURE_COLUMNS, importances)
            }
            return dict(sorted(feat_imp.items(), key=lambda item: item[1], reverse=True))
        except Exception:
            return {}


# Global ML Dual Ensemble Brain Instance
ml_brain = MLDualEnsembleBrain()
