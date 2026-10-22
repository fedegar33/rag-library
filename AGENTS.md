# AI Book RAG — Project Guide

## Project goal

Build a practical AI Engineering/RAG application for querying and analyzing
books. This is a learning and experimentation project: keep retrieval,
chunking, persistence, prompts, and evaluation understandable, and add
infrastructure only when it solves a current problem.

### Learning diary

Before finishing relevant work, check whether it produced a meaningful AI
engineering lesson. If so, read and apply
[the learning-diary skill](.agents/skills/learning-diary/SKILL.md) to update
`DIARY.md` automatically, then tell the user what was recorded in the final
response. Preserve dated history; skip routine work, quick fixes, refactors,
and UI styling unless they establish a substantive AI engineering lesson.

### Commands that exist today

Run Python commands from the repository root with `uv`. Use `uv run python` for
Python modules and scripts so they use the project's environment; no manual
virtual-environment activation is needed.

The independent Next.js frontend lives in `web/`, managed with pnpm. Read
`web/AGENTS.md` before changing frontend files. Root guidance applies across
the repository; Python keeps its existing root layout.

Shared commands from the repository root:

```bash
make setup       # Install both apps' locked dependencies
make api         # API development server, separate terminal
make web         # Next.js development server, separate terminal
make check       # Offline Python tests, Ruff, ESLint, TypeScript
make check-api   # Backend checks only
make check-web   # Frontend checks only
make build       # Web production build
```

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
uv run python -m rag_library.cli.search "query" --book-id 1 --method bm25
uv run python -m rag_library.cli.search "query" --book-id 1 --book-id 2 --method vector
uv run python -m rag_library.cli.search "query" --book-id 1 --method hybrid --candidate-limit 20 --limit 5 --verbose
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
uv run python eval.py all --method hybrid --candidate-limit 20 --output evals/results/hybrid/answers.json
uv run python eval.py all --method vector --output evals/results/vector/answers.json
uv run deepeval inspect --list
uv run deepeval inspect --run-id 1
```

The default evaluation stage is `all`; `--manual` aliases `generate`.
Generation replaces the answers file; scoring appends one DeepEval run per
nonempty answerability group. Core scoring runs Correctness and Faithfulness;
`--metrics all` adds score-only retrieval diagnostics. Answerable cases require
both core metrics at 0.7; unanswerable cases require Correctness only, with
Faithfulness score-only. Use native `threshold=None`, not synthetic pass scores.
Save boolean `answerable` with answers and in scoring metadata; legacy rows
without it use the answerable rule with a CLI notice. Never infer labels from
expected-answer wording or reload mutable dataset labels during scoring.

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
- BM25S for in-memory lexical retrieval over stored chunks
- Hybrid retrieval with equal-contribution reciprocal rank fusion (RRF), used by
  the agent and evaluations by default
- LangChain components for document splitting, retrieval integration, prompts,
  model calls, and a stateless catalog agent
- OpenAI embeddings and chat models
- Next.js App Router, React, TypeScript, Tailwind CSS v4, shadcn/ui, and
  AI Elements in `web/`, with Node 24 and pnpm 10.33.2

The frontend is a starter page; API integration, live chat, streaming, book
selection, conversation persistence, and LangChain.js are deferred. Python owns
agent and retrieval behavior. There is no AWS deployment, graph database,
advanced agent workflow, or production ingestion service yet.

## Project structure and conventions

Keep the `src` layout and a small hybrid organization: HTTP and CLI entry points
are separate from reusable agent, ingestion, and RAG logic.

Current layout (cache directories, local books, and generated results omitted;
each Python package also contains `__init__.py`):

```text
.
├── AGENTS.md
├── README.md
├── Makefile                       # Setup, development, checks, web build
├── .env.example
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── eval.py                         # Evaluation CLI entry point
├── web/                            # Independent pnpm frontend
│   ├── AGENTS.md                   # Frontend-specific conventions
│   ├── README.md
│   ├── .env.example
│   ├── .node-version
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── pnpm-workspace.yaml
│   ├── components.json             # shadcn configuration
│   └── src/
│       ├── app/                    # Routes, layout, Tailwind styles
│       ├── components/ui/          # shadcn primitives
│       ├── components/ai-elements/ # AI Elements conversation component
│       └── lib/
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
│           ├── hybrid_search.py     # Vector/BM25 candidates and RRF
│           ├── keyword_search.py    # In-memory BM25 retrieval
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
    ├── test_evaluation.py
    ├── test_hybrid_search.py
    └── test_keyword_search.py
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
`POST /chat` is the only application HTTP route; catalog listing uses the CLI.
The caller owns attachment state.
Eval cases use nonempty `book_refs` lists of exact EPUB `content_sha256` values,
resolved to current numeric IDs at generation time and saved with answers.
Direct `ask`/`search` commands can omit `--book-id` only for a singleton catalog.
Search accepts repeated `--book-id` arguments and `--method vector|bm25|hybrid`
(default vector). BM25 builds a fresh index over the attached books together, using
English stopwords, lowercase tokens, and no stemming. Chapter filtering happens
before top-k without changing the attachment-wide statistics. Preserve distinct
BM25 scores, vector similarities, and RRF scores. Catalog/BM25 need only database
settings; vector/hybrid and model workflows still require OpenAI credentials.
Hybrid retrieves max(20, final limit) candidates per branch by default, with an
explicit `--candidate-limit` override at least as large as the final limit. RRF
uses equal contributions, one-based ranks, constant 60, and identity
`(book_id, chunk_index)`. Keep branch ranks/raw scores for verbose inspection;
empty branches are valid but branch failures must propagate. AgentContext owns
the retrieval method and candidate depth, defaulting to hybrid; the model still
supplies only the content question. Agents return five reranked passages by default.
Eval generation accepts `--method vector|bm25|hybrid` (default hybrid) and optional
`--candidate-limit` (hybrid only, at least 5). Save effective retrieval settings
in answer rows and DeepEval metadata. Score-only reads frozen answers and rejects
retrieval overrides; do not infer a method for historical rows without metadata.
Eval CLI accepts repeated `--id` for exact case selection in all stages and
`--manual`. Reject unknown IDs before model calls or output writes; preserve
dataset order and execute repeated IDs once. Generation saves only selected
cases, replacing its output as usual; score-only filters saved rows in memory.
Direct `ask`/`ask_question`/`BookRetriever` remain vector by default and support
explicit method selection; CLI `ask` also accepts `--candidate-limit` for hybrid.
Hybrid reranking defaults to true through AgentContext, BookRetriever, answering,
evaluation generation, and search. It requires `COHERE_API_KEY` and applies
Cohere `rerank-v5.0-pro` to the entire deduplicated candidate union before final
top-k, preserving source identity, branch scores/ranks, RRF score, and original
RRF rank. API response indexes map to supplied candidates, never by text; API
failures must propagate. CLI search/ask/eval accept `--no-rerank` for the RRF
baseline; Python callers use `rerank=False`. Non-hybrid methods do not call Cohere.
Save effective `rerank` and `rerank_model` in eval retrieval metadata. Score-only
rejects reranking overrides and reads the saved values. Candidate depth remains
20 per method by default; use 100 explicitly to reproduce the Church experiment.
Keep answer generation instructions unchanged.
Automated retrieval evidence metrics and persistent lexical indexing remain deferred.
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
