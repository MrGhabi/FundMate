"""
Pytest configuration and shared fixtures for FundMate tests.
Provides common test data paths and setup.
"""

import pytest
import sys
from pathlib import Path


# Add src directory to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


@pytest.fixture
def test_date_0228():
    """Test date for 0228 dataset"""
    return "2025-02-28"


@pytest.fixture
def test_date_0630():
    """Test date for 0630 dataset"""
    return "2025-06-30"


@pytest.fixture
def broker_folder_0228():
    """Path to 0228 broker data folder"""
    return str(project_root / "data" / "20250228_Statement")


@pytest.fixture
def broker_folder_0630():
    """Path to 0630 broker data folder"""
    return str(project_root / "data" / "20250630_Statement")


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory for test results"""
    output_dir = tmp_path / "test_output"
    output_dir.mkdir(exist_ok=True)
    return str(output_dir)


@pytest.fixture
def mock_exchange_rates():
    """Mock exchange rates for testing without API calls"""
    return {
        'USD': 1.0,
        'CNY': 0.139,  # 1 CNY = 0.139 USD
        'HKD': 0.128   # 1 HKD = 0.128 USD
    }


@pytest.fixture(scope="session")
def project_root_path():
    """Project root directory path"""
    return project_root


@pytest.fixture
def tc_base_folder(project_root_path):
    """Path to base statements used for TC mode regression"""
    return str(project_root_path / "data" / "20250718_Statement")


@pytest.fixture
def tc_base_date():
    """Base date for TC regression."""
    return "2025-07-18"


@pytest.fixture
def tc_target_date():
    """Target date for TC regression."""
    return "2025-07-22"


@pytest.fixture
def tc_trade_confirmation_folder(project_root_path):
    """Path to archived trade confirmation Excel files."""
    return str(project_root_path / "data" / "archives" / "TradeConfirmation")


@pytest.fixture
def tc_expected_csv(project_root_path, tc_target_date):
    """Baseline CSV generated from known-good TC run."""
    return project_root_path / "test" / "fixtures" / "tc_expected" / f"portfolio_details_{tc_target_date}.csv"
