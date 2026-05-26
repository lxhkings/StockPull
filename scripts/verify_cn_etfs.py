"""一次性验证 CN_SECTOR_ETFS 中所有 ts_code 在 tushare fund_basic 存在。

跑法: uv run python scripts/verify_cn_etfs.py
"""
from config import CN_SECTOR_ETFS
from ts_ingest.client import get_client


def main() -> int:
    client = get_client()
    codes = list(CN_SECTOR_ETFS.keys())
    basic = client.call("fund_basic", market="E")
    if basic.empty:
        print("ERROR: fund_basic returned empty")
        return 1
    existing = set(basic["ts_code"].values)
    missing = [c for c in codes if c not in existing]
    if missing:
        print(f"MISSING {len(missing)}/{len(codes)}: {missing}")
        return 1
    print(f"OK: 全部 {len(codes)} 只 ETF 存在")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
