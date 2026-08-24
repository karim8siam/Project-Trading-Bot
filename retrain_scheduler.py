"""
Automated Sunday Retraining Scheduler & ML Maintenance Daemon.
Executes the Sunday Continuous Learning Pipeline:
1. Loads all completed trades from database
2. Prepares feature matrix X and win/loss target y
3. Trains Random Forest & XGBoost models (80/20 split)
4. Validates model accuracy (> 55%)
5. Extracts and logs hidden market patterns
6. Updates persisted model weights
"""

import time
import argparse
from datetime import datetime
from database import get_training_dataset, get_performance_summary
from ml_brain import ml_brain


def run_retraining_cycle(verbose: bool = True) -> bool:
    """Runs a complete ML retraining and evaluation cycle."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    if verbose:
        print("=" * 75)
        print(f"🤖 [ML RETRAINING PIPELINE] Executing Cycle @ {now_str}")
        print("=" * 75)

    X, y = get_training_dataset()
    if X.empty or len(y) < 50:
        if verbose:
            print(f"  [Notice] Insufficient trade samples ({len(y)}/50). Skipping retraining until more trades accumulate.")
        return False

    if verbose:
        print(f"  • Total Completed Trades Dataset: {len(X)} rows")
        print(f"  • Training Random Forest Model (150 Trees)...")
        print(f"  • Training XGBoost / HistGBDT Model (150 Iterations)...")

    result = ml_brain.train(X, y)

    if result["success"]:
        if verbose:
            print(f"\n  ✅ [TRAINING COMPLETED SUCCESSFULLY]")
            print(f"    - Random Forest Test Accuracy : {result['rf_accuracy'] * 100:.1f}%")
            print(f"    - XGBoost Test Accuracy       : {result['xgb_accuracy'] * 100:.1f}%")
            print(f"    - Combined Ensemble Accuracy   : {result['ensemble_accuracy'] * 100:.1f}%")
            print(f"    - Validation ROC-AUC Score     : {result['val_roc_auc']:.3f}")
            print(f"    - Validation F1-Score          : {result['val_f1']:.3f}")

            print(f"\n  🔍 [DISCOVERED HIDDEN MARKET PATTERNS]:")
            for i, p in enumerate(result.get("discovered_patterns", []), 1):
                print(f"    {i}. {p}")

            print("=" * 75)
        return True
    else:
        if verbose:
            print(f"  ❌ Training failed: {result.get('message')}")
        return False


def start_scheduler_loop(check_interval_seconds: int = 3600):
    """
    Continuous background loop checking for Sunday midnight or interval triggers.
    """
    print("=" * 75)
    print("  ⏰ ML AUTO-RETRAINING SCHEDULER DAEMON ACTIVE")
    print(f"  • Periodic check every {check_interval_seconds // 60} minutes")
    print(f"  • Automated Sunday Retraining Trigger Enabled")
    print("=" * 75)

    last_retrained_day = -1

    while True:
        now = datetime.utcnow()
        # Check if Sunday (weekday 6) and midnight hour (00:00 - 01:00 UTC)
        if now.weekday() == 6 and now.hour == 0 and now.day != last_retrained_day:
            print(f"\n[Sunday Trigger] Starting weekly automated ML retraining cycle...")
            success = run_retraining_cycle(verbose=True)
            if success:
                last_retrained_day = now.day

        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ML Sunday Retraining Scheduler")
    parser.add_argument("--now", action="store_true", help="Run retraining immediately")
    parser.add_argument("--daemon", action="store_true", help="Start background scheduler loop")

    args = parser.parse_args()

    if args.now or not args.daemon:
        run_retraining_cycle(verbose=True)
    elif args.daemon:
        start_scheduler_loop()
