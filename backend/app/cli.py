from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.corpus.ingest import ingest_corpus


def main() -> None:
    parser = argparse.ArgumentParser(prog="lawagent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="normalize and audit a legal corpus")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--output", type=Path, required=True)
    ingest.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()

    if arguments.command == "ingest":
        report = ingest_corpus(arguments.input, arguments.output, arguments.report)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
