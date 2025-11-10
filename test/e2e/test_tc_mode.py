"""
TC Mode end-to-end regression test.

Runs the trade confirmation pipeline (base statements + TC Excel files) and
verifies the generated CSV matches a known-good baseline snapshot.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from trade_confirmation_processor import TradeConfirmationProcessor
from data_persistence import DataPersistence


@pytest.mark.slow
@pytest.mark.e2e
class TestTradeConfirmationMode:
    """Validate TC processing end-to-end against baseline output."""

    def test_tc_mode_regression(
        self,
        tc_base_folder,
        tc_base_date,
        tc_target_date,
        tc_trade_confirmation_folder,
        tc_expected_csv,
        tmp_path
    ):
        processor = TradeConfirmationProcessor()
        results, exchange_rates, processed_date = processor.process_with_trade_confirmation(
            base_broker_folder=tc_base_folder,
            base_date=tc_base_date,
            target_date=tc_target_date,
            tc_folder=tc_trade_confirmation_folder
        )

        assert processed_date == tc_target_date
        assert results, "TC processing returned no broker results"

        output_dir = tmp_path / "tc_regression"
        persistence = DataPersistence(str(output_dir))
        saved_files = persistence.save_broker_data(results, processed_date, exchange_rates)

        generated_csv = Path(saved_files["portfolio_csv"])
        assert generated_csv.exists(), "Generated CSV not found"
        assert tc_expected_csv.exists(), "Baseline CSV missing; run baseline generation first"

        self._assert_csv_matches_baseline(generated_csv, tc_expected_csv)

    @staticmethod
    def _assert_csv_matches_baseline(current_path: Path, baseline_path: Path):
        """
        Compare generated CSV with baseline using deterministic subset of columns.
        
        Raw descriptions can vary slightly because PDF parsing relies on LLM output,
        so we focus on stability-critical columns (codes, holdings, pricing).
        """
        current_df = pd.read_csv(current_path)
        baseline_df = pd.read_csv(baseline_path)

        required_columns = [
            "broker_name",
            "account_id",
            "stock_code",
            "holding",
            "broker_price",
            "final_price",
            "optimized_price_currency",
            "multiplier",
            "position_value_usd",
        ]

        missing_current = [c for c in required_columns if c not in current_df.columns]
        missing_baseline = [c for c in required_columns if c not in baseline_df.columns]
        assert not missing_current and not missing_baseline, (
            f"Missing columns - current: {missing_current}, baseline: {missing_baseline}"
        )

        numeric_cols = ["holding", "broker_price", "final_price", "multiplier", "position_value_usd"]

        def normalize(df: pd.DataFrame) -> pd.DataFrame:
            subset = df[required_columns].copy()
            for col in numeric_cols:
                subset[col] = pd.to_numeric(subset[col], errors="coerce")
            return subset.sort_values(required_columns).reset_index(drop=True)

        current_sorted = normalize(current_df)
        baseline_sorted = normalize(baseline_df)

        pd.testing.assert_frame_equal(
            current_sorted,
            baseline_sorted,
            check_exact=False,
            atol=1e-6,
            rtol=1e-6,
            check_dtype=False,
        )
