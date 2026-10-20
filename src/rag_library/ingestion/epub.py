"""EPUB parsing into LangChain documents."""

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub
from langchain_core.documents import Document


@dataclass
class EpubExtractionResult:
    """Main reading documents and non-RAG auxiliary sections from an EPUB."""

    documents: list[Document]
    auxiliary_documents: list[Document]


class EpubExtractor:
    """Extract readable TOC entries and Dublin Core metadata from an EPUB."""

    _BLOCK_TAGS = {
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "pre",
    }
    _AUXILIARY_TITLES = {
        "cover": {
            "cover",
            "front cover",
            "back cover",
            "cubierta",
            "portada",
            "contracubierta",
            "contraportada",
        },
        "author": {
            "author",
            "the author",
            "autor",
            "about the author",
            "author biography",
            "biography of the author",
            "sobre el autor",
            "acerca del autor",
            "el autor",
            "biografia",
            "biografia del autor",
            "nota sobre el autor",
            "by the same author",
            "also by",
            "del mismo autor",
            "otras obras del autor",
        },
        "editorial": {
            "copyright",
            "credits",
            "creditos",
            "legal notice",
            "aviso legal",
            "pagina legal",
            "derechos de autor",
            "colofon",
            "publication information",
            "datos de edicion",
            "imprint",
        },
        "title": {"title page", "titlepage", "portadilla", "pagina de titulo"},
        "contents": {
            "contents",
            "table of contents",
            "indice",
            "contenido",
            "contenidos",
        },
        "commentary": {
            "introduction",
            "introduccion",
            "preface",
            "prefacio",
            "foreword",
            "prologo del autor",
            "afterword",
            "posfacio",
        },
    }
    _SEMANTIC_CATEGORIES = {
        "cover": "cover",
        "titlepage": "title",
        "title-page": "title",
        "copyright-page": "editorial",
        "copyright": "editorial",
        "toc": "contents",
        "foreword": "commentary",
        "preface": "commentary",
        "afterword": "commentary",
        "introduction": "commentary",
    }

    def load(self, file_path: str | Path) -> list[Document]:
        """Load only the main reading documents, excluding auxiliary sections."""
        return self.load_with_auxiliary(file_path).documents

    def load_with_auxiliary(self, file_path: str | Path) -> EpubExtractionResult:
        """Load main reading documents and separately retain auxiliary sections."""
        path = Path(file_path)
        book = epub.read_epub(str(path))
        metadata = self._metadata(book)
        documents = []
        auxiliary_documents = []

        items = self._reading_items(book)

        for chapter_number, chapter_title, section_title, item in items:
            text = self._chapter_text(item.get_content())
            if text:
                document_metadata = {
                    **metadata,
                    "source": str(path),
                    "chapter": chapter_number,
                    "chapter_title": chapter_title,
                    "section_title": section_title,
                    "document_path": item.get_name(),
                }
                auxiliary_category, reason = self._classify_item(
                    book, item, chapter_title, text, metadata
                )
                if auxiliary_category:
                    document_metadata["auxiliary_category"] = auxiliary_category
                    document_metadata["auxiliary_reason"] = reason
                    auxiliary_documents.append(
                        Document(page_content=text, metadata=document_metadata)
                    )
                else:
                    documents.append(
                        Document(page_content=text, metadata=document_metadata)
                    )

        return EpubExtractionResult(
            documents=documents,
            auxiliary_documents=auxiliary_documents,
        )

    @classmethod
    def _reading_items(cls, book):
        """Keep TOC labels, filling missing narrative interludes from the spine.

        Do not blindly add all manifest documents: publishers often include
        promotional pages outside the TOC. Unknown spine items between story
        chapters remain part of the story, even without a TOC entry.
        """
        toc = cls._toc_items(book)
        spine = cls._spine_items(book)
        if not toc:
            return spine
        by_path = {entry[3].get_name(): entry for entry in toc}
        boundaries = [
            index
            for index, entry in enumerate(spine)
            if entry[3].get_name() in by_path
            and (
                by_path[entry[3].get_name()][0] is not None
                or cls._normalize_title(by_path[entry[3].get_name()][1] or "")
                in {"prologue", "prologo", "epilogue", "epilogo"}
            )
        ]
        result = []
        seen = set()
        for index, entry in enumerate(spine):
            path = entry[3].get_name()
            if path in by_path:
                result.append(by_path[path])
            elif not boundaries or min(boundaries) < index < max(boundaries):
                result.append(entry)
            elif cls._normalize_title(entry[1] or "") in {
                "prologue",
                "prologo",
                "epilogue",
                "epilogo",
            }:
                result.append(entry)
            else:
                continue
            seen.add(path)
        result.extend(entry for path, entry in by_path.items() if path not in seen)
        return result

    @classmethod
    def _classify_item(cls, book, item, title, text, metadata):
        """Exclude only positively identified document-level auxiliary material."""
        path = item.get_name()
        for reference in getattr(book, "guide", []):
            href = str(reference.get("href", ""))
            # A guide pointing at an anchor may describe only part of a file.
            if "#" not in href and unquote(href) == path:
                kind = reference.get("type", "").lower()
                if kind in cls._SEMANTIC_CATEGORIES:
                    return cls._SEMANTIC_CATEGORIES[kind], f"EPUB guide: {kind}"

        soup = BeautifulSoup(item.get_content(), "html.parser")
        body = soup.find("body") or soup
        for element in [body, *body.find_all(["section", "article", "nav"])]:
            # Inline or partial-section labels cannot exclude a whole chapter.
            if cls._chapter_text(str(element).encode()) != text:
                continue
            for kind in str(element.get("epub:type", "")).split():
                if kind in cls._SEMANTIC_CATEGORIES:
                    return cls._SEMANTIC_CATEGORIES[kind], f"EPUB semantic type: {kind}"
        if "nav" in getattr(item, "properties", []):
            return "contents", "EPUB navigation document"

        heading = cls._chapter_heading(item.get_content())
        for label in [heading, title]:
            category = cls._auxiliary_category(label or "")
            if category == "commentary" and (
                heading is None or cls._auxiliary_category(heading) != "commentary"
            ):
                # E.g. the Spanish TOC says Introducción, but the actual page
                # contains unlabelled literary quotations. Retain ambiguity.
                continue
            if category:
                return category, f"Section label: {label}"

        stem = Path(path).stem
        tokens = set(cls._normalize_title(stem).split())
        publication_markers = sum(
            marker in text.casefold()
            for marker in ["copyright", "all rights reserved", "isbn", "publisher"]
        )
        if "copyright" in tokens and publication_markers >= 2:
            return "editorial", "Explicit copyright document filename"
        title_tokens = {"title", "titlepage", "titulo", "tp", "tp2"}
        book_title = cls._normalize_title(metadata.get("title", ""))
        if (
            tokens & title_tokens
            and book_title
            and book_title in cls._normalize_title(text)
            and len(text) < 2000
        ):
            return "title", "Title-page filename and matching book metadata"
        return None, None

    @classmethod
    def _auxiliary_category(cls, title: str) -> str | None:
        """Return an auxiliary category for known front/back matter titles."""
        normalized_title = cls._normalize_title(title)
        for category, titles in cls._AUXILIARY_TITLES.items():
            if normalized_title in titles:
                return category
        # Some EPUBs append a date or symbol to the copyright page title.
        if normalized_title.startswith("copyright "):
            return "editorial"
        if normalized_title.startswith("also by "):
            return "author"
        return None

    @staticmethod
    def _normalize_title(title: str) -> str:
        decomposed = unicodedata.normalize("NFKD", title.casefold())
        without_marks = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())

    @classmethod
    def _toc_items(
        cls, book: epub.EpubBook
    ) -> list[tuple[int | None, str, str | None, epub.EpubItem]]:
        """Return readable linked TOC entries with their parent section title."""
        items = []
        for entry, section_title in cls._toc_entries(getattr(book, "toc", [])):
            title = str(getattr(entry, "title", "")).strip()
            href = str(getattr(entry, "href", "")).split("#", 1)[0]
            item = (
                entry
                if hasattr(entry, "get_content")
                else book.get_item_with_href(href)
                if href
                else None
            )
            if not title or item is None or item.get_type() != ITEM_DOCUMENT:
                continue
            items.append((cls._chapter_number(title), title, section_title, item))
        return items

    @classmethod
    def _toc_entries(
        cls, entries, parent_title: str | None = None
    ) -> Iterator[tuple[object, str | None]]:
        # EbookLib can return a single Link for a minimal/empty NCX.
        if not isinstance(entries, (list, tuple)):
            entries = [entries]
        for entry in entries:
            if isinstance(entry, tuple):
                section, children = entry
                title = str(getattr(section, "title", "")).strip() or parent_title
                yield from cls._toc_entries(children, title)
            else:
                yield entry, parent_title

    @classmethod
    def _spine_items(
        cls, book: epub.EpubBook
    ) -> list[tuple[int | None, str | None, None, epub.EpubItem]]:
        """Use XHTML headings in reading order when the EPUB has no TOC."""
        spine = []
        for item_id, _linear in getattr(book, "spine", []):
            item = book.get_item_with_id(item_id)
            if item is not None and item.get_type() == ITEM_DOCUMENT:
                spine.append(item)
        if not spine:
            spine = list(book.get_items_of_type(ITEM_DOCUMENT))

        items = []
        for item in spine:
            heading = cls._chapter_heading(item.get_content()) or None
            if heading is None:
                heading = str(getattr(item, "title", "")).strip() or None
            chapter_number = cls._chapter_number(heading) if heading else None
            items.append((chapter_number, heading, None, item))
        return items

    @staticmethod
    def _chapter_number(title: str) -> int | None:
        match = re.match(
            r"^\s*(?:(?:chapter|cap[ií]tulo)\s+)?(\d+)\b",
            title,
            re.IGNORECASE,
        )
        return int(match.group(1)) if match else None

    @classmethod
    def _chapter_heading(cls, content: bytes) -> str | None:
        soup = BeautifulSoup(content, "html.parser")
        heading = soup.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        title = " ".join(heading.get_text(" ", strip=True).split()) if heading else ""
        if title:
            return title

        # Converted EPUBs often style chapter labels as paragraphs. Only accept
        # a standalone label at the start; numbers inside prose aren't headings.
        for element in soup.find_all(cls._BLOCK_TAGS):
            if any(parent.name in cls._BLOCK_TAGS for parent in element.parents):
                continue
            title = " ".join(element.get_text(" ", strip=True).split())
            if not title:
                continue
            if re.fullmatch(
                r"(?:(?:chapter|cap[ií]tulo)\s+)?\d+", title, re.IGNORECASE
            ):
                return title
            normalized = cls._normalize_title(title)
            if cls._auxiliary_category(title) or normalized in {
                "introduction",
                "prologue",
                "epilogue",
                "contents",
                "dedication",
            }:
                return title
            if re.fullmatch(
                r"part\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)",
                title,
                re.IGNORECASE,
            ):
                return title
            return None
        return None

    @classmethod
    def _chapter_text(cls, content: bytes) -> str:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()

        blocks = []
        for element in soup.find_all(cls._BLOCK_TAGS):
            if any(parent.name in cls._BLOCK_TAGS for parent in element.parents):
                continue
            text = " ".join(element.get_text(" ", strip=True).split())
            if text:
                blocks.append(text)

        if not blocks:
            return " ".join(soup.get_text(" ", strip=True).split())
        return "\n\n".join(blocks)

    @staticmethod
    def _metadata(book: epub.EpubBook) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for key in ("title", "creator", "language", "publisher", "identifier"):
            values = book.get_metadata("DC", key)
            if values:
                metadata[key] = str(values[0][0])
        return metadata
