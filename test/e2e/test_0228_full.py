"""
End-to-end test for 0228 dataset.
Run full processing pipeline and verify final totals match expected results.
"""

import pytest
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from broker_processor import BrokerStatementProcessor
from data_persistence import save_processing_results


def load_expected_results():
    """Load expected results from baseline file"""
    import json
    baseline_file = Path(__file__).parent / "expected_results.json"
    if baseline_file.exists():
        with open(baseline_file) as f:
            data = json.load(f)
            return data['0228'], data['tolerance_percent']
    # Fallback to hardcoded values if file missing
    return {
        'total_cash': 12_601_423.22,
        'total_positions': 64_855_665.97,
        'grand_total': 77_457_089.19
    }, 5.0


@pytest.mark.slow
@pytest.mark.e2e
class TestE2E_0228:
    """End-to-end test simulating: python src/main.py data/20250228_Statement --date 2025-02-28"""
    
    def test_full_pipeline_0228(self, broker_folder_0228, test_date_0228, project_root_path):
        """
        Run complete processing pipeline and verify results match expected totals.
        Simulates running main.py with real data.
        """
        # Step 1: Run full processing (like main.py does)
        processor = BrokerStatementProcessor()
        
        results, exchange_rates, date = processor.process_folder(
            broker_folder=broker_folder_0228,
            image_output_folder=str(project_root_path / "out" / "pictures"),
            date=test_date_0228,
            broker=None,
            force=False,
            max_workers=5
        )
        
        # Verify processing succeeded
        assert results is not None, "Processing failed"
        assert len(results) > 0, "No brokers processed"
        
        # Step 2: Save results (like main.py does)
        output_dir = str(project_root_path / "out" / "result")
        saved_files = save_processing_results(
            results=results,
            date=test_date_0228,
            exchange_rates=exchange_rates,
            output_dir=output_dir
        )
        
        # Step 3: Read generated CSV
        csv_path = saved_files['portfolio_csv']
        assert Path(csv_path).exists(), f"CSV not generated: {csv_path}"
        
        csv_df = pd.read_csv(csv_path)
        summary = csv_df[csv_df['broker_name'] == '[SUMMARY]']
        
        # Step 4: Extract actual totals
        actual_cash = summary[summary['account_id'] == 'TOTAL_CASH']['position_value_usd'].values[0]
        actual_positions = summary[summary['account_id'] == 'TOTAL_POSITIONS']['position_value_usd'].values[0]
        actual_total = summary[summary['account_id'] == 'GRAND_TOTAL']['position_value_usd'].values[0]
        
        # Step 5: Load expected results and verify
        expected, tolerance_percent = load_expected_results()
        tolerance = tolerance_percent / 100
        
        def within_tolerance(actual, expected, tol):
            if expected == 0:
                return actual == 0
            diff_percent = abs(actual - expected) / expected
            return diff_percent <= tol
        
        # Verify cash (should be very stable)
        assert within_tolerance(actual_cash, expected['total_cash'], tolerance), \
            f"Cash mismatch: expected ${expected['total_cash']:,.2f}, got ${actual_cash:,.2f}"
        
        # Verify positions (may vary due to price changes)
        assert within_tolerance(actual_positions, expected['total_positions'], tolerance), \
            f"Positions mismatch: expected ${expected['total_positions']:,.2f}, got ${actual_positions:,.2f}"
        
        # Verify grand total
        assert within_tolerance(actual_total, expected['grand_total'], tolerance), \
            f"Grand total mismatch: expected ${expected['grand_total']:,.2f}, got ${actual_total:,.2f}"
        
        # Print summary for visibility
        print(f"\n=== 0228 E2E Test Results ===")
        print(f"Cash:      ${actual_cash:,.2f} (expected ${expected['total_cash']:,.2f})")
        print(f"Positions: ${actual_positions:,.2f} (expected ${expected['total_positions']:,.2f})")
        print(f"Total:     ${actual_total:,.2f} (expected ${expected['grand_total']:,.2f})")
        print(f"Brokers:   {len(results)}")
        print(f"✅ All totals within {tolerance_percent}% tolerance")

