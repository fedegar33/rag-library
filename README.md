# RAG Library API

A Python book catalog agent exposed through FastAPI, with EPUB ingestion and
vector, BM25, and hybrid search CLI workflows. Managed with `uv`.

This is a learning and experimentation project for querying and analyzing books.
Keep retrieval, chunking, persistence, prompts, and evaluation understandable,
preserve book/chapter/chunk provenance, and add infrastructure when it solves a
current problem. The current application has no frontend or production deployment.

The stack uses FastAPI, SQLAlchemy 2.x, PostgreSQL with pgvector,
LangChain components, and OpenAI embedding and chat models.

## Requirements

- Python 3.12+
- uv
- PostgreSQL with the `pgvector` extension available for catalog and RAG workflows
- An OpenAI API key for ingestion, vector/hybrid search, answering, and evaluation;
  catalog listing and BM25 search need only `DATABASE_URL`

## Setup

Copy `.env.example` to `.env` and fill in `DATABASE_URL` and `OPENAI_API_KEY`.
Keep local books and notebook outputs out of source control.

Create the virtual environment and install the locked dependencies:

```bash
uv sync
```

This creates `.venv/` using the committed `uv.lock`. Run all commands from the
repository root with `uv`. Use `uv run python` for Python modules and scripts so
they use the project's environment; no manual environment activation is needed.
EPUB inspection, offline tests, and code checks do not require a running database
or OpenAI credentials.

## Run the API

```bash
uv run uvicorn rag_library.main:app --reload
```

The API is available at <http://127.0.0.1:8000>. Interactive documentation is at `/docs`.

## Use Jupyter for experiments

Jupyter is an optional development dependency for trying retrieval, prompt, and API ideas interactively. It is not required to run the service.

Install the notebook tools and launch JupyterLab:

```bash
uv sync --group notebooks
uv run jupyter lab
```

Open `notebooks/01_catalog_agent.ipynb` using the project `.venv` kernel. It
creates a fresh catalog agent with `get_agent()`, exercises the same response
helper as `/agent`, and lets you inspect native messages, tool calls, and an
explicit follow-up conversation. No API server is needed. Re-run the setup cell
to reload `.env` and create a new agent. Notebook outputs are intentionally empty
so credentials and catalog data are not committed.

## Verify

Run the offline tests and code checks:

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
uv run ruff format --check .
```

## Ingest an EPUB

To inspect EPUB metadata and chapter names without ingesting a book into the
database, run:

```bash
uv run epub-ingestion-debug "./book.epub"
uv run epub-ingestion-debug "./book.epub" --show-excluded
```

The command uses the ingestion extractor to print the book title, named sections,
and detected chapter numbers. When the EPUB has no usable table of contents, it
uses reading-order files and recognizes HTML headings or standalone numbered
paragraphs at the start of a file. The numbered-chapter count excludes sections
with unknown chapter numbers. TOC labels are reconciled with the reading order
so unlisted narrative interludes between chapters are retained.

Auxiliary classification uses document-level EPUB guide/semantic labels,
recognized section headings, and corroborated title/copyright filenames.
Clearly editorial introductions, prefaces, forewords, and afterwords are
excluded. An ambiguous TOC label alone does not discard story material;
prologues, epilogues, part epigraphs, notes, and unknown narrative sections stay.
`--show-excluded` prints each excluded file and the evidence for classification.
See `docs/corpus-cleanup-report.md` for the current local EPUB inspection.

Set `DATABASE_URL` and `OPENAI_API_KEY` in `.env`, then run:

```bash
uv run python -m rag_library.cli.ingest --file "./book.epub"
```

The database must be PostgreSQL with the `pgvector` extension available. The
first run creates the vector extension and application tables automatically.
Ingestion uses 1000-character chunks with 200-character overlap and
`text-embedding-3-small` by default. Re-ingesting identical EPUB content
replaces its existing book and chunks and assigns a new book ID. Existing
chunks do not change until ingestion runs again; list the current IDs afterward:

```bash
uv run python -m rag_library.cli.books
```

No ingestion or model calls are performed by `epub-ingestion-debug`.

## Search ingested books

Search stored chunks with vector retrieval (the default), BM25, or hybrid RRF:

```bash
uv run python -m rag_library.cli.search "something" --book-id 1
uv run python -m rag_library.cli.search "something" --book-id 1 --limit 10
uv run python -m rag_library.cli.search "something" --book-id 1 --verbose
uv run python -m rag_library.cli.search "something" --book-id 1 --chapter 1,2,3
uv run python -m rag_library.cli.search "something" --book-id 1 --limit 10 --verbose --chapter 1,2
uv run python -m rag_library.cli.search "Church's full name" --book-id 1 --method bm25
uv run python -m rag_library.cli.search "Church's full name" --book-id 1 --method vector
uv run python -m rag_library.cli.search "burial ground" --book-id 1 --book-id 2 --method bm25 --limit 10 --verbose
uv run python -m rag_library.cli.search "Church's full name" --book-id 1 --method hybrid --verbose
uv run python -m rag_library.cli.search "burial ground" --book-id 1 --book-id 2 --method hybrid --candidate-limit 40 --limit 10
```

Replace the example IDs with current catalog IDs from `cli.books`. Search accepts
repeated `--book-id` arguments to attach several books and returns a pooled top-k
across them. `ask` still selects exactly one book. `--book-id` can be omitted
only when the catalog has one book; an ambiguous or invalid selection fails
without embedding calls. Use a content-only query: select books with arguments
instead of adding their titles to the search text. Reusable `semantic_search()`,
`bm25_search()`, `hybrid_search()`, and `ask_question()` require explicit nonempty
`book_ids` lists.

Vector results use pgvector cosine similarity. BM25 uses BM25S's Lucene variant
with `k1=1.5`, `b=0.75`, lowercase tokens, English stopword removal, and no
stemming. The initial tokenization policy is intended for English books and
questions; it does not automatically adapt to book language metadata. BM25
scores and cosine similarities have different scales and are not directly
comparable. Compare returned evidence and ranks instead.

BM25 loads only attached-book text and provenance, builds a fresh in-memory
index on each invocation, and makes no embedding or chat calls. Existing chunks
are sufficient: no schema migration, re-ingestion, or whole-book text field is
needed. There is no saved index to synchronize after ingestion. Indexing cost
grows with the attached corpus; persistent indexing is deferred.

Output includes book ID, chapter, chunk index, a method-specific score, and a
compact preview; `--verbose` includes the title and complete matching text.
Use `--chapter` to restrict results to one or more 1-based EPUB document/chapter
numbers. BM25 calculates term statistics over all chapters of the attached books,
then applies chapter eligibility before selecting top-k. Unattached books never
participate in scoring. Results with no lexical matches are omitted; queries
containing only stopwords or punctuation return no matches. Blank queries fail.

### Hybrid rank fusion

`--method hybrid` retrieves candidates from both vector and BM25 search using the
same query, attached books, and chapter restrictions. Each branch contributes up
to 20 candidates by default, increasing to `--limit` when it exceeds 20. Override
this depth with `--candidate-limit`, which is hybrid-only and must be positive
and at least `--limit`. Candidate depth applies per branch across all attachments,
not separately per book.

Reciprocal rank fusion (RRF) adds `1 / (60 + rank)` for each branch containing a
chunk, using ranks starting at 1 and equal contributions. It deduplicates by
`(book_id, chunk_index)` and returns the final top `--limit`. Raw BM25 scores and
cosine similarities do not enter the fusion formula. Ties use book ID and chunk
index for repeatable ordering. RRF scores are not confidence probabilities.
See the [original RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf).

Compact output shows the RRF score and provenance. `--verbose` also shows each
branch's rank, cosine similarity, BM25 score, and the complete text; `None` means
the chunk was absent from that branch's candidate list. An empty branch is valid
and the other branch's ranks still contribute. A branch error fails the command
rather than silently returning partial results. Hybrid requires one query
embedding request and builds the same temporary BM25 index; it generates no
answer and changes no stored data.

The agent and full-agent evaluation runner use hybrid retrieval by default.
Direct `ask` remains vector by default and supports explicit method selection.
Additional reranking, automated retrieval evidence metrics, and persistent lexical
indexing remain deferred.

## Ask questions about ingested books

Retrieve the top five chunks and ask the configured chat model to answer using
only that book context:

```bash
uv run python -m rag_library.cli.ask "Who is Nicolas?" --book-id 1
uv run python -m rag_library.cli.ask "Who is Nicolas?" --book-id 1 --top-k 8
uv run python -m rag_library.cli.ask "Who is Nicolas?" --book-id 1 --method hybrid --candidate-limit 20
```

Set `OPENAI_CHAT_MODEL` to choose the chat model; it defaults to
`gpt-4o-mini`. The command prints the generated answer and the source chunks
used to produce it. Use `--top-k` to control how many chunks are supplied as
context; it defaults to 5. `--method vector|bm25|hybrid` selects retrieval;
`--candidate-limit` is hybrid-only and must be at least `--top-k` when supplied.
Answer system instructions are shared across methods. Hybrid context and source
output label RRF scores explicitly instead of treating them as cosine similarity.

## Book agent

`POST /agent` answers one independent message using a LangChain agent with
two tools, `list_books` and `answer_book_question`. Set `DATABASE_URL` and `OPENAI_API_KEY`; the agent uses
`OPENAI_CHAT_MODEL` (default: `gpt-4o-mini`). Start the API as described above,
then send a request:

```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"message": "Which town does the Creed family move to?", "book_ids": [1]}'
```

Choose current IDs through `GET /books` (or `uv run python -m rag_library.cli.books`).
That catalog includes each book's `content_sha256`. The API requires one or more
positive integer IDs in every request and validates all attachments before
initializing the agent. Missing, empty, or unknown IDs return HTTP 422.
The answer tool uses hybrid retrieval by default: 20 candidates per branch,
equal-contribution RRF with constant 60, and five final passages. Retrieval method
and depth belong to `AgentContext`, alongside book attachments; the model cannot
select them. Notebook callers can set `retrieval_method="vector"` or `"bm25"`
when constructing a context, or set `candidate_limit` for hybrid experiments.
The caller keeps the selected IDs between requests; the backend does not persist
chats or attachment state.

Attachments enter an `AgentContext` in `agent/context.py`, passed to `run_agent()`.
LangChain injects this context into the tools; the model sees only the question
argument on `answer_book_question`. Its `list_books` tool exposes only attached
books. The separate `GET /books` endpoint exposes the whole catalog for selection.

The model's final answer uses provider-native structured output with a strict
Pydantic `AgentAnswer` schema. The server reads the validated `structured_response`
and combines it with tool records; the model does not generate the tool log.
The configured OpenAI model must support structured output together with tools.
Invalid structured answers return HTTP 503, like other execution errors.
The tool log comes from actual execution messages. Greetings can return an
empty `tool_calls` list. Book-content questions use `answer_book_question`, a
thin wrapper around the same `ask_question()` workflow used by the `ask` CLI.
It retrieves five chunks and returns the grounded answer plus source passages
with book ID/title, chapter, and chunk references in the tool log. The agent
uses the attached IDs automatically. SQL filters with `book_id IN (...)`,
then selects the five closest chunks across the pooled attachments. A book need
not contribute a chunk to that global top five. Each source retains its own
book ID, title, chapter, and chunk index. The model cannot widen the scope by
supplying another book ID. Questions normally omit the title because the caller
has already chosen the books. Multiple attachments are supported per request.
Answers are limited to the retrieved context.

Messages must contain 1-4000 characters after trimming surrounding whitespace;
invalid requests return HTTP 422. Database, provider, and execution-limit errors
return HTTP 503 with `{"detail": "Agent service unavailable"}` and server logs.
Each request allows at most three model calls and two tool calls. Model calls
have a 30-second timeout with automatic retries disabled. These limits apply
to the outer agent; the existing RAG model and embedding calls inside the
book-answer tool retain their provider defaults.

This JSON endpoint is for local experiments: it has no authentication,
pagination, conversation history, or session persistence. `/` and `/health` do
not initialize the agent or require credentials. The endpoint is also available
in `/docs`.

## Project layout

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
│           ├── hybrid_search.py
│           ├── keyword_search.py
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


Keep API and CLI entry points thin. Reusable workflows live in the corresponding
Python modules so notebooks and future agent tools can call them directly.
Use absolute imports beginning with `rag_library` and import workflows from
their implementation modules, such as `ingestion.pipeline` or `rag.answering`.
When moving modules, update imports, CLI commands, script targets, notebooks,
and documentation together. See [AGENTS.md](AGENTS.md) for the full development
conventions.

## Agent evaluation with DeepEval

DeepEval is the main evaluation runner, following the
[RAG QA tutorial](https://deepeval.com/tutorials/rag-qa-agent/evaluation).
With dependencies installed (`uv sync`), the referenced EPUB ingested, and `.env`
configured, run from the repository root:

```bash
uv run python eval.py
```

Generation now uses hybrid retrieval by default. Save separate snapshots for
comparison with vector-only retrieval:

```bash
uv run python eval.py all --method hybrid --candidate-limit 20 --output evals/results/hybrid/answers.json
uv run python eval.py all --method vector --output evals/results/vector/answers.json
```

`--method bm25` is also available. Final context remains five passages; hybrid
candidate depth defaults to 20 per method and explicit depths must be at least
five. The dataset, system instructions, and judge rubric are unchanged.

The runner reads `evals/basic.json`: ten English questions about Pet Sematary.
It calls the full agent independently for each question, including tool selection
and query rewriting, then passes the entire batch to DeepEval’s `evaluate()`
Python API. No pytest runner or parametrization is involved. The source JSON
stays curated: `id`, `question`, `expected_answer`, and a nonempty `book_refs`
list of lowercase `content_sha256` strings. Each case also has source-verified
`reference_evidence` for manual auditing; see [the dataset guide](evals/README.md)
for its fields, answer conventions, and baseline changes. No synthesizer is used. These hashes
identify exact EPUB bytes, so reingestion can change numeric IDs without changing
the eval references. A different EPUB edition or modified file has another hash.
Before each invocation, references resolve to current IDs; missing references
fail that case explicitly. Questions contain only the content question.

Generated answers save `book_refs`, resolved `book_ids`, `attached_books`, and
`retrieval` settings (method, final top-k, effective candidate depth, RRF constant).
The same fields enter DeepEval case metadata, alongside tool records containing
source scores and branch ranks.
Rescoring uses the saved answers and scope without resolving or retrieving again;
Older answer files remain scoreable but do not acquire missing attachment or
retrieval metadata. Regenerate answers to evaluate a changed retrieval method.

Each response becomes an `LLMTestCase`: the original question is `input`, the
expected answer is `expected_output`, the final agent answer is `actual_output`,
and passages from actual `answer_book_question` executions become
`retrieval_context`, in execution/retrieval order. Full tool results remain in
case metadata for book/chapter/chunk provenance. No second retrieval is performed.
Agent answers and tool records are checkpointed to `evals/basic_result.json`.
During generation, the terminal shows each case's position, ID, and question
before the agent call, then its elapsed time, executed tool names, retrieved
passage count, and checkpoint status. Failed cases display their errors and the
remaining questions continue. A transition message identifies when the saved
answers are being prepared for DeepEval scoring.
Cases with agent errors or missing passages stay in the saved results as failed
cases, without judge scores, and cause a nonzero exit status. Judge errors are
also recorded as failures while the remaining metrics/cases continue.

The five metrics use an initial **0.7 threshold**, defined in
`src/rag_library/deepeval_evaluation.py`:

| Metric | What it checks |
| --- | --- |
| Contextual relevancy | Whether retrieved content is relevant to the question |
| Contextual recall | Whether retrieved content supports the expected answer |
| Contextual precision | Whether relevant chunks rank ahead of irrelevant chunks |
| Faithfulness | Whether the final answer is grounded in the retrieved content |
| Answer correctness (G-Eval) | Whether the final answer matches the expected facts, allowing paraphrases |

Every metric must pass for a question to pass. These initial thresholds and judge
scores are a starting point for iteration, not an objective measure of quality.
The curated answers are the correctness reference: review ambiguous questions
and incorrect references before interpreting failures as RAG regressions.

The judge defaults to `OPENAI_CHAT_MODEL`. Override it independently in `.env`:

```dotenv
EVAL_JUDGE_MODEL=gpt-4o-mini
```

The judge uses `OPENAI_API_KEY`. Running the suite incurs agent, retrieval, and
additional judge calls. Answer collection is sequential; DeepEval then evaluates
the collected cases and metrics asynchronously, with a default concurrency
limit of 20. Evaluation caching is disabled so each scoring run uses fresh
judge calls, matching the reference workflow.
It prints progress, scores, reasons, and pass/fail results in the terminal.
Adjust concurrency with:

```bash
uv run python eval.py --max-concurrent 2
```

DeepEval is the sole store for scored results. Configure its local SQLite backend
in `.env` (the same settings are included in `.env.example`):

```dotenv
DEEPEVAL_LOCAL_STORE=sqlite
DEEPEVAL_RESULTS_FOLDER=evals/results
```

Each scoring run is appended to `evals/results/deepeval.db`, including cases,
metric scores, reasons, and tool-call metadata. No custom scored JSON export is
written. The answers file remains JSON for independent re-scoring. Change the
runner's database folder with `--results-folder`; use the same
`DEEPEVAL_RESULTS_FOLDER` when inspecting that database.

Browse stored runs with DeepEval:

```bash
uv run deepeval inspect --list
uv run deepeval inspect --run-id 1
```

Results are local and ignored by Git. A Confident AI login is not required;
this suite does not push datasets or configure cloud reporting. Existing JSON
reports are left in place; switching backends does not migrate them.

### Generate and score

This follows the staged runner/scorer workflow from
[Mohamad Hachem's evaluation project](https://github.com/Mohamad-Hachem/LLM_Evaluation_System).
The scripts in that project use JSONL; this project retains JSON arrays so the
existing question set and manual notebook continue to work.

```bash
# 1. Agent calls only; save answers, actual retrieved passages, and tool records.
uv run python eval.py generate

# 2. Judge calls only; read the saved answers and evaluate the whole batch.
uv run python eval.py score
```

`uv run python eval.py` (or `uv run python eval.py all`) performs both stages.
DeepEval prints its own evaluation summary after scoring. To re-score
an unchanged RAG run with a different judge, change `EVAL_JUDGE_MODEL` and run
only `score`; it does not call the agent or retrieve again.
Score-only rejects `--method` and `--candidate-limit`; it uses the saved retrieval
metadata and passages rather than changing or relabeling them.

| File | Contents |
| --- | --- |
| `evals/basic.json` | Curated questions and expected answers |
| `evals/basic_result.json` | Frozen agent answers, passages, tool records, errors |
| `evals/results/deepeval.db` | DeepEval run history, answers, context, tool records, metric scores and reasons |

DeepEval retains case IDs with scored results. Cases with generation errors or
no book passages remain in the intermediate answers file and are reported in
the terminal; they are not submitted to the judge and are absent from the
DeepEval report. They still cause the command to exit with failure.

Re-running `generate` replaces the answers file, while each scoring run appends
a new database run. Use `--output` to retain named answer snapshots:

```bash
uv run python eval.py all --output evals/results/baseline/answers.json
uv run python eval.py score --output evals/results/baseline/answers.json
```

All evaluation options can be passed after the stage:

```bash
uv run python eval.py all \
  --dataset evals/basic.json \
  --output evals/results/baseline/answers.json \
  --results-folder evals/results \
  --max-concurrent 2
```

| Option | Default | Purpose |
| --- | --- | --- |
| Stage | `all` | `all`, `generate`, or `score` |
| `--dataset` | `evals/basic.json` | Curated cases to generate answers for |
| `--output` | `evals/basic_result.json` | Write generated answers or read saved answers for scoring |
| `--results-folder` | `evals/results` | DeepEval result database folder |
| `--max-concurrent` | `20` | Maximum concurrent scoring tasks; must be positive |
| `--manual` | Disabled | Alias for `generate`; cannot be combined with `score` |

The legacy alias can also be run explicitly:

```bash
uv run python eval.py --manual
```

The existing
`notebooks/03_basic_evals.ipynb` still uses the original manual workflow.
