"""명령줄 사용법

  python -m mathcheck check examples/sample_quiz.yaml --out build/
  python -m mathcheck check quiz.yaml --out build/ --bank bank.jsonl --record

종료 코드: 통과 0, 오류 있음 1
"""
from __future__ import annotations

import argparse
import json
import sys

from .dupes import record
from .pipeline import check_all
from .spec import load_spec


def main() -> int:
    ap = argparse.ArgumentParser(prog="mathcheck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="퀴즈 사양을 검사하고 PDF를 만든다")
    c.add_argument("spec")
    c.add_argument("--out", default="build")
    c.add_argument("--bank", default=None, help="예전에 낸 문항 기록 파일(jsonl)")
    c.add_argument("--record", action="store_true", help="통과하면 문항 기록에 추가")
    c.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = ap.parse_args()

    rep, files = check_all(args.spec, args.out, args.bank)
    if args.json:
        print(json.dumps({**rep.to_dict(), "files": files}, ensure_ascii=False, indent=2))
    else:
        print(rep.to_text())
        for k, v in files.items():
            print(f"{k}: {v.get('pdf')}")
    if rep.ok and args.record and args.bank:
        record(load_spec(args.spec), args.bank)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
