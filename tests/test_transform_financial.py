import json

import pandas as pd

from ts_ingest.transform_financial import transform_financial_rows


def test_transform_with_report_type_builds_json_payload():
    df = pd.DataFrame({
        "ts_code":     ["600519.SH"],
        "ann_date":    ["20240328"],
        "f_ann_date":  ["20240328"],
        "end_date":    ["20231231"],
        "report_type": ["1"],
        "comp_type":   ["1"],
        "total_revenue": [150000000000.0],
        "n_income":      [74700000000.0],
    })
    rows = transform_financial_rows(df, has_report_type=True)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[1] == "2023-12-31"  # end_date
    assert row[2] == "2024-03-28"  # ann_date
    assert row[3] == "2024-03-28"  # f_ann_date
    assert row[4] == "1"           # report_type
    assert row[5] == "1"           # comp_type
    payload = json.loads(row[6])
    assert payload["total_revenue"] == 150000000000.0


def test_transform_without_report_type_skips_report_and_comp_type():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "end_date": ["20231231"],
        "ann_date": ["20240328"], "roe": [28.5],
    })
    rows = transform_financial_rows(df, has_report_type=False)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[1] == "2023-12-31"
    assert row[2] == "2024-03-28"
    payload = json.loads(row[3])
    assert payload["roe"] == 28.5
