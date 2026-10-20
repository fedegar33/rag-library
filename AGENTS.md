# AI Book RAG — Project Guide

## Project goal

Build a practical AI Engineering/RAG application for querying and analyzing
books. This is a learning and experimentation project: keep retrieval,
chunking, persistence, prompts, and evaluation understandable, and add
infrastructure only when it solves a current problem.

### Commands that exist today

Run commands from the repository root with `uv`. Use `uv run python` for
Python modules and scripts so they use the project's environment; no manual
virtual-environment activation is needed.

Setup, API, and notebooks:

```bash
uv sync
uv run uvicorn rag_library.main:app --reload
uv sync --group notebooks
uv run jupyter lab
```

Book ingestion, inspection, search, and answering (replace the example book ID
with a current catalog ID):

```bash
uv run python -m rag_library.cli.ingest --file "./book.epub"
uv run epub-ingestion-debug "./book.epub"
uv run epub-ingestion-debug "./book.epub" --show-excluded
uv run python -m rag_library.cli.books
uv run python -m rag_library.cli.search "query" --book-id 1
uv run python -m rag_library.cli.search "query" --book-id 1 --limit 10 --verbose --chapter 1,2
uv run python -m rag_library.cli.ask "question" --book-id 1
uv run python -m rag_library.cli.ask "question" --book-id 1 --top-k 8
```

Evaluation and stored results:

```bash
uv run python eval.py
uv run python eval.py all
uv run python eval.py generate
uv run python eval.py score
uv run python eval.py --manual
uv run python eval.py all --dataset evals/basic.json --output evals/results/baseline/answers.json --results-folder evals/results --max-concurrent 2
uv run python eval.py score --output evals/results/baseline/answers.json
uv run deepeval inspect --list
uv run deepeval inspect --run-id 1
```

The default evaluation stage is `all`; `--manual` aliases `generate`.
Generation replaces the answers file, and scoring appends a DeepEval run.

Offline tests and code checks:

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
uv run ruff format --check .
```

### Stack

- Python 3.12+, managed with `uv`
- FastAPI service scaffold
- SQLAlchemy 2.x and PostgreSQL
- pgvector for 1536-dimensional OpenAI embeddings
- LangChain components for document splitting, retrieval integration, prompts,
  model calls, and a stateless catalog agent
- OpenAI embeddings and chat models

There is no frontend, AWS deployment, graph database, advanced agent workflow, or
production ingestion service yet. Keep these as future options, not current
architecture.

## Project structure and conventions

Keep the `src` layout and a small hybrid organization: HTTP and CLI entry points
are separate from reusable agent, ingestion, and RAG logic.

Current layout (cache directories, local books, and generated results omitted;
each Python package also contains `__init__.py`):

```text
.
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── eval.py                         # Evaluation CLI entry point
├── src/
│   └── rag_library/
│       ├── main.py                 # FastAPI setup and route registration
│       ├── catalog.py              # Catalog queries and book selection
│       ├── config.py               # Environment settings
│       ├── database.py             # SQLAlchemy models and schema setup
│       ├── evaluation.py           # Answer generation and persistence
│       ├── deepeval_evaluation.py  # DeepEval scoring integration
│       ├── agent/
│       │   ├── agent.py
│       │   ├── context.py
│       │   ├── models.py
│       │   ├── prompts.py
│       │   └── tools.py
│       ├── api/
│       │   ├── routes.py
│       │   └── schemas.py
│       ├── cli/
│       │   ├── ask.py
│       │   ├── books.py
│       │   ├── eval.py
│       │   ├── ingest.py
│       │   ├── inspect_epub.py
│       │   └── search.py
│       ├── ingestion/
│       │   ├── epub.py
│       │   └── pipeline.py
│       └── rag/
│           ├── answering.py
│           ├── retriever.py
│           └── search.py
├── docs/
│   ├── corpus-cleanup-report.md
│   └── eval-reassessment-2026-10-19.md
├── evals/
│   ├── README.md
│   └── basic.json                  # Curated evaluation cases
├── notebooks/
│   ├── 01_catalog_agent.ipynb
│   └── 03_basic_evals.ipynb
├── Untitled1.ipynb                 # Root-level scratch notebook
└── tests/
    ├── test_attached_context.py
    ├── test_book_scope.py
    ├── test_deepeval_evaluation.py
    ├── test_epub_ingestion.py
    ├── test_eval_stages.py
    └── test_evaluation.py
```

Each subpackage has an `__init__.py`. Notebooks live in `notebooks/` and import
reusable application code from the installed package.

- Keep `main.py` limited to application setup and route registration.
- Keep HTTP schemas, dependencies, and HTTP error handling under `api/`.
- Keep argument parsing, terminal formatting, and exit codes under `cli/`;
  reusable workflows must not import CLI modules. Prefer returned results for
  reusable logic; the ingestion pipeline currently also prints progress.
- Use absolute imports beginning with `rag_library`. Import workflow functions
  from their implementation modules, such as `ingestion.pipeline` or
  `rag.answering`; avoid package-level re-export chains.
- Keep agent construction/execution, tools, prompts, and models under `agent/`.
  Keep `catalog.py` and `database.py` as modules until their actual
  responsibilities justify a split. Add folders around meaningful workflows;
  avoid generic `utils/`, `services/`, or repository layers without a concrete need.
- When moving modules, update imports, CLI commands, project script targets,
  notebooks, and documentation together. The API entry point remains
  `rag_library.main:app`.

The API requires nonempty `book_ids` and validates all attachments before model
execution. `AgentContext` injects the attached books into tools; the model supplies
only the content question. Retrieval pools top-k across attached IDs, retaining
each source's book ID. The agent's `list_books` tool exposes only attachments;
`GET /books` exposes the catalog to callers. The caller owns attachment state.
Eval cases use nonempty `book_refs` lists of exact EPUB `content_sha256` values,
resolved to current numeric IDs at generation time and saved with answers.
Direct `ask`/`search` commands can omit `--book-id` only for a singleton catalog.
Unnumbered story sections are retained unless positively identified as auxiliary.

## Technology principles

- **Incremental complexity:** add frameworks and infrastructure only to address
  a demonstrated need in the current phase.
- **Understand before abstracting:** keep retrieval, SQL, chunking, embedding
  storage, prompts, and evaluation inspectable.
- **Preserve provenance:** retain source book/chapter/chunk references wherever
  practical so the system can answer “Where did this information come from?”
- **Keep the path adaptable:** evolve from the working book RAG baseline toward
  structured knowledge, graph workflows, agents, or deployment only as useful.
