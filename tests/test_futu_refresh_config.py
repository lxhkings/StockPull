"""Tests for FUTU_REFRESH_DAYS per-interface throttle config."""

from config import FUTU_REFRESH_DAYS, FUTU_DEFAULT_REFRESH_DAYS


def test_refresh_days_covers_all_22_interfaces():
    """Verify all 22 Futu interfaces are covered."""
    expected = {
        "us_shares_daily", "us_analyst_consensus", "us_capital_flow",
        "us_capital_distribution", "us_short_interest", "us_daily_short_volume",
        "us_valuation_snapshot", "us_rating_summary", "us_morningstar",
        "us_dividends", "us_splits", "us_earnings_dates", "us_company_profile",
        "us_financial", "us_revenue_breakdown", "us_earnings_price_move",
        "us_shareholders_overview", "us_holding_changes", "us_institutional",
        "us_insider_holders", "us_insider_trades", "us_op_efficiency",
    }
    assert set(FUTU_REFRESH_DAYS) == expected


def test_refresh_days_frequency_tiers():
    """Verify frequency tiers match design."""
    assert FUTU_REFRESH_DAYS["us_shares_daily"] == 1
    assert FUTU_REFRESH_DAYS["us_valuation_snapshot"] == 6
    assert FUTU_REFRESH_DAYS["us_dividends"] == 20
    assert FUTU_REFRESH_DAYS["us_company_profile"] == 25
    assert FUTU_REFRESH_DAYS["us_financial"] == 80
    assert FUTU_DEFAULT_REFRESH_DAYS == 80