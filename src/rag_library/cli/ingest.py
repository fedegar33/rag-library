"""Command-line entry point for ingesting EPUB files."""

import argparse
import sys

from rag_library.ingestion.pipeline import ingest_book


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest an EPUB into the RAG library")
    parser.add_argument("--file", required=True, help="Path to an EPUB file")
    args = parser.parse_args()

    try:
        ingest_book(args.file)
    except Exception as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
