"""
TC Mode end-to-end regression test.

Loads a cached base portfolio snapshot, runs trade confirmations, and
validates the generated CSV against a known-good baseline.
"""

import json
import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import src.trade_confirmation_processor as tcp
from src.trade_confirmation_processor import TradeConfirmationProcessor
from src.data_persistence import DataPersistence
from src.broker_processor import ProcessedResult
from src.position import Position


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
        tc_base_fixture_dir,
        tmp_path
    ):
        base_results, base_rates = self._load_base_results_from_fixture(tc_base_fixture_dir)

        processor = TradeConfirmationProcessor()
        results, exchange_rates, processed_date = processor.process_with_trade_confirmation(
            base_broker_folder=tc_base_folder,
            base_date=tc_base_date,
            target_date=tc_target_date,
            tc_folder=tc_trade_confirmation_folder,
            base_results_override=base_results,
            base_exchange_rates_override=base_rates,
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
    def _load_base_results_from_fixture(base_dir: Path):
        metadata = json.load(open(base_dir / f"metadata_{base_dir.name}.json", "r", encoding="utf-8"))
        cash_df = pd.read_parquet(base_dir / f"cash_summary_{base_dir.name}.parquet")
        positions_df = pd.read_parquet(base_dir / f"positions_{base_dir.name}.parquet")

        results = []
        for _, cash_row in cash_df.iterrows():
            broker = cash_row["broker_name"]
            account = cash_row["account_id"]
            cash_data = {
                "CNY": cash_row.get("cny"),
                "HKD": cash_row.get("hkd"),
                "USD": cash_row.get("usd"),
                "Total": cash_row.get("total"),
                "Total_type": cash_row.get("total_type"),
            }
            subset = positions_df[
                (positions_df["broker_name"] == broker) &
                (positions_df["account_id"] == account)
            ]
            position_objs = []
            for _, row in subset.iterrows():
                pos = Position(
                    stock_code=row["stock_code"],
                    holding=row["holding"],
                    broker_price=row.get("broker_price"),
                    price_currency=row.get("broker_price_currency"),
                    raw_description=row.get("raw_description"),
                    multiplier=row.get("multiplier"),
                    broker=broker,
                )
                pos.final_price = row.get("final_price")
                pos.final_price_source = row.get("final_price_source")
                if row.get("optimized_price_currency"):
                    pos.optimized_price_currency = row.get("optimized_price_currency")
                position_objs.append(pos)

            results.append(
                ProcessedResult(
                    broker_name=broker,
                    account_id=account,
                    cash_data=cash_data,
                    positions=position_objs,
                    usd_total=cash_row.get("usd_total") or 0.0,
                )
            )

        exchange_rates = metadata.get("exchange_rates", {})
        return results, exchange_rates

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
