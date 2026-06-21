from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agents.model_client import OpenAIEmbeddingClient
from app.config import Settings
from app.corpus.ingest import ingest_corpus
from app.rag.builder import EmbeddingIndexBuilder


def main() -> None:
    parser = argparse.ArgumentParser(prog="lawagent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="normalize and audit a legal corpus")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--output", type=Path, required=True)
    ingest.add_argument("--report", type=Path, required=True)
    build = subparsers.add_parser(
        "build-index", help="embed normalized articles and persist an index"
    )
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--index", type=Path, required=True)
    build.add_argument("--cache", type=Path, required=True)
    build.add_argument("--batch-size", type=int, default=64)
    build.add_argument("--workers", type=int, default=1)
    arguments = parser.parse_args()

    if arguments.command == "ingest":
        report = ingest_corpus(arguments.input, arguments.output, arguments.report)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
    elif arguments.command == "build-index":
        settings = Settings.load()
        client = OpenAIEmbeddingClient(
            settings.embedding, max_retries=settings.max_retries
        )
        builder = EmbeddingIndexBuilder(
            arguments.input,
            arguments.index,
            arguments.cache,
            embedding_model=client.model,
            embed_batch=client.embed,
            progress=lambda completed, total: print(f"INDEX_PROGRESS={completed}/{total}"),
        )
        report = builder.build(batch_size=arguments.batch_size, workers=arguments.workers)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
