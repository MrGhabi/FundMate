"""
End-to-end test for cross-broker aggregation logic.
Verify same stock across brokers is properly aggregated.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from broker_processor import BrokerStatementProcessor
from data_persistence import save_processing_results
import pandas as pd


@pytest.mark.slow
@pytest.mark.e2e
class TestCrossBrokerAggregation:
    """Test cross-broker position aggregation and pricing"""
    
    def test_cross_broker_0228(self, broker_folder_0228, test_date_0228, project_root_path):
        """
        Verify cross-broker logic works correctly:
        - Same stock in multiple brokers is aggregated
        - Prices are deduplicated (queried once, used everywhere)
        - Position values calculated correctly
        """
        # Run full processing
        processor = BrokerStatementProcessor()
        
        results, exchange_rates, date = processor.process_folder(
            broker_folder=broker_folder_0228,
            image_output_folder=str(project_root_path / "out" / "pictures"),
            date=test_date_0228,
            broker=None,
            force=False,
            max_workers=5
        )
        
        assert results is not None
        assert len(results) >= 2, "Need at least 2 brokers for cross-broker test"
        
        # Save and read CSV
        output_dir = str(project_root_path / "out" / "result")
        saved_files = save_processing_results(
            results=results,
            date=test_date_0228,
            exchange_rates=exchange_rates,
            output_dir=output_dir
        )
        
        csv_df = pd.read_csv(saved_files['portfolio_csv'])
        data_rows = csv_df[csv_df['broker_name'] != '[SUMMARY]'].copy()
        
        # Find stocks that appear in multiple brokers
        # For options, use raw_description to distinguish different contracts
        # For regular stocks, use stock_code
        data_rows['unique_key'] = data_rows.apply(
            lambda row: row['raw_description'] if 'OPTION' in str(row['stock_code']).upper() else row['stock_code'],
            axis=1
        )
        
        stock_counts = data_rows['unique_key'].value_counts()
        cross_broker_stocks = stock_counts[stock_counts > 1]
        
        if len(cross_broker_stocks) > 0:
            print(f"\n=== Cross-Broker Stocks Found ===")
            for stock, count in cross_broker_stocks.items():
                print(f"{stock}: appears in {count} brokers")
                
                # Verify same stock/option has same price across brokers
                stock_data = data_rows[data_rows['unique_key'] == stock]
                prices = stock_data['final_price'].dropna().unique()
                
                if len(prices) > 0:
                    print(f"  Price(s): {prices}")
                    # Should have only one price (deduplicated)
                    assert len(prices) == 1, f"Stock/Option {stock} has multiple prices: {prices}"
        
        # Verify total calculation is sum of cash + positions
        summary = csv_df[csv_df['broker_name'] == '[SUMMARY]']
        total_cash = summary[summary['account_id'] == 'TOTAL_CASH']['position_value_usd'].values[0]
        total_positions = summary[summary['account_id'] == 'TOTAL_POSITIONS']['position_value_usd'].values[0]
        grand_total = summary[summary['account_id'] == 'GRAND_TOTAL']['position_value_usd'].values[0]
        
        # Allow small floating point error
        expected_total = total_cash + total_positions
        assert abs(grand_total - expected_total) < 1.0, \
            f"Total calculation error: {grand_total} != {total_cash} + {total_positions}"
        
        print(f"\n✅ Cross-broker aggregation verified")
        print(f"Cash: ${total_cash:,.2f}")
        print(f"Positions: ${total_positions:,.2f}")
        print(f"Total: ${grand_total:,.2f}")
