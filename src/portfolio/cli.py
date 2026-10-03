"""python -m src.portfolio.cli --input input-09 --report-month 202610"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import load_config
from .model.snapshot import write_snapshot
from .pipeline import build_month, InputUnreadable, MissingInput, NoManpowerMonth
from .render.pii import find_pii  # 保留：tests/portfolio/test_cli.py 會 monkeypatch 這個名字


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--report-month", required=True)
    ap.add_argument("--today", default=None, help="reference date YYYY-MM-DD; default: the Briefing snapshot date"); ap.add_argument("--lang", default="en")
    ap.add_argument("--snapshots", default="data/snapshots"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    d = Path(a.input)
    try:
        res = build_month(d, a.report_month, a.today, a.snapshots, load_config(), a.lang, pii_check=find_pii)
    except MissingInput:
        print(f"missing master/briefing/summary in {d}", file=sys.stderr); return 1
    except (InputUnreadable, NoManpowerMonth) as ex:
        print(str(ex), file=sys.stderr); return 1
    # 負向檢查在任何寫檔之前，HTML 與 snapshot JSON 都要過；命中就兩個檔案都不寫。
    if res.pii_hits:
        print(f"PII found, refusing to write HTML or snapshot: {res.pii_hits[:5]}", file=sys.stderr); return 2
    write_snapshot(res.snap, a.snapshots)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    f = out / f"portfolio_{a.report_month}_{a.lang}.html"; f.write_text(res.html, encoding="utf-8")
    s = res.summary
    print(f"wrote {f} ({len(res.html)} bytes); {s['projects']} projects; {s['control_lists']} control lists; latest month {s['latest_month']}; snapshot {s['snap_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
