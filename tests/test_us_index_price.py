"""Tests for US market index/ETF price fetching."""


def test_update_index_price_includes_sector_etfs():
    """update_index_price should include all 11 sector ETFs in indices list."""
    from jobs.market_us import update_index_price
    import inspect

    # Extract indices list from function source
    source = inspect.getsource(update_index_price)
    expected_etfs = [
        "QQQ",
        "XLK", "XLY", "XLF", "XLV", "XLP",
        "XLI", "XLE", "XLB", "XLRE", "XLU", "XLC"
    ]

    # Each ETF should appear in source code
    for etf in expected_etfs:
        assert etf in source, f"ETF {etf} not found in update_index_price()"


def test_indices_list_format():
    """Indices list should use (symbol, index_id) tuple format."""
    from jobs.market_us import update_index_price
    import inspect

    source = inspect.getsource(update_index_price)

    # Find indices assignment line
    for line in source.split('\n'):
        if 'indices = [' in line:
            # Verify format: ("XLK", "XLK")
            assert '"XLK", "XLK"' in source or "('XLK', 'XLK')" in source
            break
