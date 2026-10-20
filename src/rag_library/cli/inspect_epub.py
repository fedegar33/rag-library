"""Print the title and numbered chapter headings from an EPUB file."""

import argparse
import sys
from pathlib import Path

from rag_library.ingestion.epub import EpubExtractor


def inspect_epub(file_path: str | Path, show_excluded: bool = False) -> None:
    """Print the EPUB title and chapter number/title pairs from its own contents."""
    result = EpubExtractor().load_with_auxiliary(file_path)
    documents = result.documents + result.auxiliary_documents
    title = documents[0].metadata.get("title", "Unknown") if documents else "Unknown"
    print(f"Libro: {title}")

    section = None
    for document in result.documents:
        metadata = document.metadata
        if metadata.get("section_title") and metadata["section_title"] != section:
            section = metadata["section_title"]
            print(section)
        chapter = metadata.get("chapter")
        title = metadata.get("chapter_title") or "Untitled section"
        print(f"{chapter}. {title}" if chapter is not None else f"- {title}")
    chapter_numbers = {
        document.metadata["chapter"]
        for document in result.documents
        if document.metadata.get("chapter") is not None
    }
    print(f"Numbered chapters: {len(chapter_numbers)}")
    if show_excluded:
        print(f"\nExcluded from retrieval: {len(result.auxiliary_documents)} sections")
        for document in result.auxiliary_documents:
            metadata = document.metadata
            print(
                f"- [{metadata['auxiliary_category']}] {metadata['document_path']}"
                f" | {metadata['auxiliary_reason']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect metadata and chapter names in an EPUB file"
    )
    parser.add_argument("file", help="Path to an EPUB file")
    parser.add_argument(
        "--show-excluded",
        action="store_true",
        help="Also print auxiliary sections and the evidence for excluding them",
    )
    args = parser.parse_args()

    try:
        inspect_epub(args.file, show_excluded=args.show_excluded)
    except Exception as error:
        print(f"No se pudo leer el EPUB: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
