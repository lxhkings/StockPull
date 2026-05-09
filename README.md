# Project_B — Unified Stocks Ingest

Daily-K ingest for US (yfinance) + A-share (akshare/efinance) + HK (akshare/efinance), writing into shared NAS MariaDB.

See `docs/superpowers/plans/` for the implementation plan.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill DB_PASSWORD
python main.py init      # one-time: insert CSI800/HSI rows into indices table
python main.py daily     # run all markets
```
