"""Command line.

  python -m mathcheck check examples/sample_quiz.yaml --out build/
  python -m mathcheck check quiz.yaml --out build/ --bank bank.jsonl --record --lang ko
  python -m mathcheck curricula
  python -m mathcheck chapters ib_aa

Exit code: 0 pass, 1 errors found.
"""
from __future__ import annotations

import argparse
import json
import sys

from .dupes import record
from .pipeline import check_all
from .scope_check import list_curricula, load_curriculum
from .spec import load_spec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mathcheck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a quiz spec and build the PDFs")
    c.add_argument("spec")
    c.add_argument("--out", default="build")
    c.add_argument("--bank", default=None, help="history of questions already used (jsonl)")
    c.add_argument("--record", action="store_true", help="append to the history file if the check passes")
    c.add_argument("--no-pdf", action="store_true", help="skip LaTeX (answers, scope and duplicates only)")
    c.add_argument("--json", action="store_true", help="print the result as JSON")
    c.add_argument("--lang", default=None, help="message language: en (default) or ko")
    sub.add_parser("curricula", help="list available curriculum files")
    ch = sub.add_parser("chapters", help="list chapter codes of a curriculum")
    ch.add_argument("curriculum")
    args = ap.parse_args(argv)

    if args.cmd == "curricula":
        for k, v in list_curricula().items():
            print(f"{k:20s} {v}")
        return 0
    if args.cmd == "chapters":
        for k, v in load_curriculum(args.curriculum)["chapters"].items():
            print(f"{k:28s} {v.get('title', k)}")
        return 0

    rep, files = check_all(args.spec, args.out, args.bank, build_pdf=not args.no_pdf)
    if args.json:
        print(json.dumps({**rep.to_dict(args.lang), "files": files}, ensure_ascii=False, indent=2))
    else:
        print(rep.to_text(args.lang))
        for k, v in files.items():
            print(f"{k}: {v.get('pdf')}")
    if rep.ok and args.record and args.bank:
        record(load_spec(args.spec), args.bank)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
