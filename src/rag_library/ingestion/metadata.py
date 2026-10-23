"""EPUB presentation metadata, independent of text chunking and embeddings."""

import posixpath
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from ebooklib import ITEM_COVER, epub


@dataclass(frozen=True)
class BookPresentation:
    categories: list[str]
    cover_data: bytes | None = None
    cover_media_type: str | None = None


def _image_media_type(data: bytes) -> str | None:
    """Identify supported raster covers from their bytes, not EPUB MIME claims."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _cover_candidates(book: epub.EpubBook):
    # EbookLib converts EPUB3 manifest cover-image items into EpubCover objects.
    yield from book.get_items_of_type(ITEM_COVER)
    legacy_covers = list(book.get_metadata("OPF", "cover"))
    legacy_covers.extend(
        (value, attributes)
        for value, attributes in book.get_metadata("OPF", "meta")
        if attributes.get("name") == "cover"
    )
    for _, attributes in legacy_covers:
        item = book.get_item_with_id(attributes.get("content"))
        if item is not None:
            yield item
    for entry in book.guide:
        if entry.get("type") != "cover":
            continue
        href = unquote(urlsplit(entry.get("href", "")).path)
        item = book.get_item_with_href(href)
        if item is None:
            continue
        yield item
        if item.media_type != "application/xhtml+xml":
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for image in soup.find_all(["img", "image"]):
            src = image.get("src") or image.get("href") or image.get("xlink:href")
            if not src:
                continue
            target = urlsplit(src)
            if target.scheme or target.netloc:
                continue
            image_path = posixpath.normpath(
                posixpath.join(posixpath.dirname(href), unquote(target.path))
            )
            image_item = book.get_item_with_href(image_path)
            if image_item is not None:
                yield image_item


def extract_book_presentation(file_path: str | Path) -> BookPresentation:
    """Read all DC subjects and a declared cover; never guess a genre or image."""
    book = epub.read_epub(str(file_path))
    categories = [
        str(value) for value, _ in book.get_metadata("DC", "subject") if value
    ]
    for item in _cover_candidates(book):
        data = item.get_content()
        media_type = _image_media_type(data)
        if media_type:
            return BookPresentation(categories, data, media_type)
    return BookPresentation(categories)
