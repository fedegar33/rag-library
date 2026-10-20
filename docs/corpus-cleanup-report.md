# Corpus cleanup inspection

Offline inspection of the four local EPUBs. This report describes the updated
extractor; it does not change the existing database or call embedding/chat models.

## Policy

- Use document-level EPUB guide/types and explicit section labels as evidence.
- Identify converted title pages by filename plus matching book metadata.
- Identify unlabelled copyright pages by filename plus publication markers.
- Retain unknown narrative, prologues, epilogues, notes, and part epigraphs.
- Retain an ambiguous TOC Introduction label when the actual heading does not
  identify commentary. This matters for the Spanish literary quotations.
- Reconcile the TOC with spine order inside the narrative to retain missing
  interludes, rather than adding every publisher appendix to the story.

## Inspected files

| Local file | Retained documents | Numbered chapters | Excluded sections |
| --- | ---: | ---: | ---: |
| `Class Trip - Emmanuel Carrere.epub` | 30 | 30 | 4 |
| `Pet Sematary - Stephen King.epub` | 68 | 62 | 4 |
| `animales.epub` | 68 | 62 | 2 |
| `nieve.epub` | 31 | 31 | 2 |

### Class Trip - Emmanuel Carrere.epub

| Excluded document | Category | Evidence |
| --- | --- | --- |
| `xhtml/title.xhtml` | title | EPUB semantic type: titlepage |
| `xhtml/about_the_author.xhtml` | author | Section label: About the Author |
| `xhtml/also_by.xhtml` | author | Section label: Also by Emmanuel Carrère |
| `xhtml/copyright.xhtml` | editorial | EPUB semantic type: copyright-page |

### Pet Sematary - Stephen King.epub

| Excluded document | Category | Evidence |
| --- | --- | --- |
| `OEBPS/Text/0743412273_Pet_Sematary_tp.html` | title | Title-page filename and matching book metadata |
| `OEBPS/Text/0743412273_Pet_Sematary_copyright.html` | editorial | Explicit copyright document filename |
| `OEBPS/Text/0743412273_Pet_Sematary_content.html` | contents | Section label: Contents |
| `OEBPS/Text/0743412273_Pet_Sematary_intro.html` | commentary | Section label: Introduction |

All 62 numbered chapters and the narrative epilogue are retained.
The author Introduction is excluded; the unlabelled prefatory quotations,
dedication, and part epigraphs remain under the conservative policy.

### animales.epub

| Excluded document | Category | Evidence |
| --- | --- | --- |
| `Text/titulo.xhtml` | title | EPUB guide: title-page |
| `Text/autor.xhtml` | author | Section label: Sobre el autor |

All 62 numbered chapters and the narrative epilogue are retained.
The unlisted `Text/P03b.xhtml` story interlude is now retained. The ambiguous
literary quotations labelled Introducción, part epigraphs, and translator
notes remain available.

### nieve.epub

| Excluded document | Category | Evidence |
| --- | --- | --- |
| `Text/titulo.xhtml` | title | Title-page filename and matching book metadata |
| `Text/autor.xhtml` | author | Section label: Autor |

## Apply to stored books

Existing stored chunks stay unchanged until you re-ingest. Re-ingest only the
editions you want to update; ingestion makes embedding calls. For the current
English Pet Sematary evaluation:

```bash
uv run epub-ingestion-debug "books/Pet Sematary - Stephen King.epub" --show-excluded
uv run python -m rag_library.cli.ingest --file "books/Pet Sematary - Stephen King.epub"
uv run python -m rag_library.cli.books
```

For the other local editions, run their corresponding ingestion command:

```bash
uv run python -m rag_library.cli.ingest --file "books/Class Trip - Emmanuel Carrere.epub"
uv run python -m rag_library.cli.ingest --file "books/animales.epub"
uv run python -m rag_library.cli.ingest --file "books/nieve.epub"
uv run python -m rag_library.cli.books
```

Re-ingestion replaces the old book and chunks and assigns a new book ID.
Use the ID printed by `cli.books` in direct search/ask commands. The following
examples use 1; replace it with the actual ID:

```bash
uv run python -m rag_library.cli.search "Which town does the Creed family move to?" --book-id 1 --verbose
uv run python -m rag_library.cli.ask "Which town does the Creed family move to?" --book-id 1
uv run python eval.py
```

The eval calls the full agent, which obtains current IDs from the catalog.
Regenerate answers after re-ingestion; scoring the previous answers would only
re-judge the previous corpus outputs. Existing DeepEval runs remain historical.
