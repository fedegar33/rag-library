"""Offline regression checks for EPUB chapter provenance."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ebooklib import epub

from rag_library.cli.inspect_epub import inspect_epub
from rag_library.ingestion.epub import EpubExtractor
from rag_library.ingestion.pipeline import chunk_documents


class EpubChapterTests(unittest.TestCase):
    def write_book(self, directory, sections, toc=None, guide=None):
        """Make a tiny EPUB with explicit reading order and optional TOC labels."""
        book = epub.EpubBook()
        book.set_identifier("corpus-cleanup")
        book.set_title("Synthetic Book")
        book.set_language("en")
        book.add_author("A Writer")
        items = []
        for filename, content in sections:
            item = epub.EpubHtml(
                uid=filename, file_name=filename, media_type="application/xhtml+xml"
            )
            item.content = content
            book.add_item(item)
            items.append(item)
        book.spine = items
        book.toc = [epub.Link(path, label, path) for path, label in toc or []]
        book.guide = guide or []
        book.add_item(epub.EpubNcx())
        path = Path(directory) / "synthetic.epub"
        epub.write_epub(str(path), book)
        return path

    def test_structural_title_copyright_contents_and_commentary_excluded(self):
        sections = [
            ("converted_tp.html", "<p>Synthetic Book</p><p>A Writer</p>"),
            (
                "copyright.html",
                "<p>Copyright 2026 A Writer</p><p>All rights reserved. ISBN 123.</p>",
            ),
            ("contents.html", "<p>Contents</p><p>Chapter 1</p>"),
            ("introduction.html", "<p>Introduction</p><p>How I wrote this novel.</p>"),
            ("chapter.html", "<p>1</p><p>The story begins.</p>"),
            ("epilogue.html", "<p>Epilogue</p><p>The story ends.</p>"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_book(folder, sections)
            result = EpubExtractor().load_with_auxiliary(path)
            self.assertEqual(
                [d.metadata["document_path"] for d in result.documents],
                ["chapter.html", "epilogue.html"],
            )
            self.assertEqual(
                {d.metadata["auxiliary_category"] for d in result.auxiliary_documents},
                {"title", "editorial", "contents", "commentary"},
            )
            self.assertTrue(
                all(d.metadata["auxiliary_reason"] for d in result.auxiliary_documents)
            )
            output = io.StringIO()
            with redirect_stdout(output):
                inspect_epub(path, show_excluded=True)
            self.assertIn("Excluded from retrieval: 4", output.getvalue())

    def test_guide_and_whole_document_semantics_but_not_inline_labels(self):
        sections = [
            ("unlabelled.xhtml", "<p>Synthetic Book</p><p>A Writer</p>"),
            (
                "legal.xhtml",
                '<section epub:type="copyright-page">'
                "<p>Publication details</p></section>",
            ),
            (
                "story.xhtml",
                '<h1>1</h1><p>He read the <span epub:type="copyright-page">'
                "copyright</span> and shut the book.</p>",
            ),
            ("unknown.xhtml", "<p>A narrative section without a chapter number.</p>"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_book(
                folder,
                sections,
                guide=[
                    {"type": "title-page", "href": "unlabelled.xhtml", "title": "Title"}
                ],
            )
            result = EpubExtractor().load_with_auxiliary(path)
            self.assertEqual(
                [d.metadata["document_path"] for d in result.auxiliary_documents],
                ["unlabelled.xhtml", "legal.xhtml"],
            )
            self.assertEqual(len(result.documents), 2)

    def test_ambiguous_introduction_and_missing_story_interlude_are_retained(self):
        sections = [
            ("intro.xhtml", "<h1>*</h1><p>Literary quotations.</p>"),
            ("prologue.xhtml", "<h1>Prologue</h1><p>Opening scene.</p>"),
            ("one.xhtml", "<h1>1</h1><p>First chapter.</p>"),
            ("interlude.xhtml", "<h1>*</h1><p>Characters speak between chapters.</p>"),
            ("two.xhtml", "<h1>2</h1><p>Second chapter.</p>"),
            ("epilogue.xhtml", "<h1>Epilogue</h1><p>Ending.</p>"),
            ("promo.xhtml", "<h1>Other books to buy</h1><p>Advertising.</p>"),
        ]
        toc = [("intro.xhtml", "Introducción"), ("one.xhtml", "1"), ("two.xhtml", "2")]
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_book(folder, sections, toc=toc)
            result = EpubExtractor().load_with_auxiliary(path)
            self.assertEqual(
                [d.metadata["document_path"] for d in result.documents],
                [filename for filename, _ in sections[:-1]],
            )
            self.assertEqual(result.auxiliary_documents, [])

    def test_styled_paragraph_chapter_labels(self):
        for label, expected in [("1", 1), ("Chapter 12", 12), ("Capítulo 3", 3)]:
            with self.subTest(label=label):
                heading = EpubExtractor._chapter_heading(
                    f"<body><p> </p><p><span>{label}</span></p>"
                    "<p>The story begins.</p></body>".encode()
                )
                self.assertEqual(EpubExtractor._chapter_number(heading), expected)

    def test_numbers_in_prose_are_not_chapters(self):
        for text in ["1984 was a difficult year.", "There were 12 people."]:
            self.assertIsNone(
                EpubExtractor._chapter_heading(f"<body><p>{text}</p></body>".encode())
            )
        self.assertIsNone(
            EpubExtractor._chapter_heading(b"<p>Story opening.</p><p>12</p>")
        )

    def test_existing_html_heading_takes_precedence(self):
        self.assertEqual(
            EpubExtractor._chapter_heading(b"<p>1</p><h2>Chapter 2</h2>"),
            "Chapter 2",
        )

    def test_spine_fallback_preserves_chapters_through_chunking_and_debug(self):
        # Match a converted EPUB: unusable TOC, numbered paragraphs, no h tags.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.epub"
            book = epub.EpubBook()
            book.set_identifier("chapter-regression")
            book.set_title("Synthetic book")
            book.set_language("en")
            items = []
            for index, label in enumerate(["Copyright", "1", "2", "EPILOGUE"]):
                item = epub.EpubHtml(uid=f"item{index}", file_name=f"{index}.xhtml")
                item.content = (
                    f"<p><span>{label}</span></p><p>Section text {index}.</p>"
                )
                book.add_item(item)
                items.append(item)
            book.toc = [epub.Link("missing.xhtml", "Start", "start")]
            book.add_item(epub.EpubNcx())
            book.spine = items
            epub.write_epub(str(path), book)

            result = EpubExtractor().load_with_auxiliary(path)
            self.assertEqual(
                [d.metadata["chapter"] for d in result.documents], [1, 2, None]
            )
            self.assertEqual(
                result.auxiliary_documents[0].metadata["auxiliary_category"],
                "editorial",
            )
            chunks = chunk_documents(result.documents)
            self.assertEqual([d.metadata["chapter"] for d in chunks], [1, 2, None])
            output = io.StringIO()
            with redirect_stdout(output):
                inspect_epub(path)
            self.assertIn("Numbered chapters: 2", output.getvalue())
            self.assertIn("- EPILOGUE", output.getvalue())


if __name__ == "__main__":
    unittest.main()
