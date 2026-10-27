# RAG Library

A Python book catalog agent exposed through FastAPI, with EPUB ingestion and
vector, BM25, and hybrid search CLI workflows, plus a Next.js streaming chat UI.
Python is managed with `uv`; the independent `web/` app uses pnpm.

This is a learning and experimentation project for querying and analyzing books.
Keep retrieval, chunking, persistence, prompts, and evaluation understandable,
preserve book/chapter/chunk provenance, and add infrastructure when it solves a
current problem. Chats persist in PostgreSQL through LangGraph checkpoints and
application-owned presentation records. Production deployment remains deferred.

The stack uses FastAPI, SQLAlchemy 2.x, PostgreSQL with pgvector,
LangChain components, and OpenAI embedding and chat models. The web app
uses Next.js App Router, TypeScript, Tailwind CSS v4, shadcn/ui chat primitives, and Streamdown for Markdown.

## Requirements

- Python 3.12+
- uv
- Node.js 24 and pnpm 10.33.2 for the web app
- PostgreSQL with the `pgvector` extension available for catalog and RAG workflows
- An OpenAI API key for ingestion, vector/hybrid search, answering, and evaluation;
  catalog listing and BM25 search need only `DATABASE_URL`

## Setup

Install both apps' locked dependencies from the repository root:

```bash
make setup
```

This runs `uv sync --locked` and `pnpm --dir web install --frozen-lockfile`.
For backend-only work, `uv sync` remains sufficient.

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

### LangSmith tracing

The backend loads the root `.env` into the process environment so LangSmith can
read its SDK settings. Exported environment variables take precedence. To enable:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-key
LANGSMITH_PROJECT=rag-library
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Restart the API or notebook kernel after changing tracing settings. LangChain
agent/model/tool executions are traced automatically when enabled. `make check-api`
explicitly disables tracing for offline tests, regardless of the local `.env`.
For another command, use `LANGSMITH_TRACING=false uv run ...` to disable tracing.

## Run the API

```bash
uv run uvicorn rag_library.main:app --reload
```

The API is available at <http://127.0.0.1:8000>. Interactive documentation is at `/docs`.

## Run the web chat

Run each app in its own terminal from the repository root:

```bash
make api
```

```bash
make web
```

Copy `web/.env.example` to `web/.env.local`. Select books through the composer's
Books panel; an empty selection searches the whole library. `CHAT_BOOK_IDS` is
no longer used. `BACKEND_API_URL` defaults to `http://127.0.0.1:8000`; keep model and
database credentials in the root `.env`.

The web app is available at <http://localhost:3000>. It proxies questions through
Next.js `/api/chat` to Python `/chats/{id}/messages`, streaming text and retrieval
status. Chats reopen at `/chats/<id>` after refresh or a server restart. Messages,
tool results, sources and selected books are stored in PostgreSQL; drafts remain
in memory. Python loads agent history from checkpoints and bounds model input.
Switching chats cancels
the current response and preserves partial output; failures offer manual Retry.
Source panels and LangChain.js remain deferred.
Source events are retained in message state for future provenance UI.

| Command | Purpose |
| --- | --- |
| `make setup` | Install both apps' locked dependencies |
| `make api` | Start the API development server |
| `make web` | Start the Next.js development server |
| `make check` | Run backend and frontend checks |
| `make check-api` | Run offline Python tests and Ruff checks |
| `make check-web` | Run ESLint and TypeScript checks |
| `make build` | Build the web app for production |

See [web/README.md](web/README.md) for frontend commands and component installation.

## Use Jupyter for experiments

Jupyter is an optional development dependency for trying retrieval, prompt, and API ideas interactively. It is not required to run the service.

Install the notebook tools and launch JupyterLab:

```bash
uv sync --group notebooks
uv run jupyter lab
```

Open `notebooks/01_catalog_agent.ipynb` using the project `.venv` kernel. It
creates a fresh catalog agent with `get_agent()`, exercises `run_agent()`,
and lets you inspect native messages, tool calls, and an
explicit follow-up conversation. No API server is needed. Re-run the setup cell
to reload `.env` and create a new agent. Notebook outputs are intentionally empty
so credentials and catalog data are not committed.

## Verify

Run `make check` to check both apps, and `make build` to verify the frontend
production build. The frontend TypeScript check generates Next.js route types
before checking, so it also works before the first build.

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

### Book-card metadata

New ingestions also extract all EPUB `dc:subject` values as `categories`, and a
declared cover image. Categories retain their original values and order; they
are not inferred genres. Missing categories become `[]`. Supported covers are
JPEG, PNG, GIF, and WebP; absent or unsupported covers become `null` in the card
contract. Covers are stored as bytes in PostgreSQL and loaded separately from
catalog queries and retrieval.

For existing books, run the metadata-only command **before using the updated
catalog API**. It also adds the new columns to existing databases:

```bash
uv run python -m rag_library.cli.enrich_books --file "./book.epub"
# Repeat --file to update several books in one run.
```

This command needs only `DATABASE_URL`. It matches the exact EPUB bytes through
`content_sha256` and updates only categories and cover fields, preserving book
IDs, chunks, and embeddings. Unknown EPUB hashes fail instead of creating a
book. Each file commits separately; if a later file fails, earlier updates stay
committed. Repeated runs are safe. Books without an available original retain
empty categories and no cover after schema initialization. Regular ingestion
also initializes this additive schema; re-ingestion is unnecessary for enrichment.

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

With `--no-rerank`, compact output shows the RRF score and provenance.
`--verbose` also shows each
branch's rank, cosine similarity, BM25 score, and the complete text; `None` means
the chunk was absent from that branch's candidate list. An empty branch is valid
and the other branch's ranks still contribute. A branch error fails the command
rather than silently returning partial results. Hybrid requires one query
embedding request and builds the same temporary BM25 index; it generates no
answer and changes no stored data.

The agent and full-agent evaluation runner use hybrid retrieval by default.
Direct `ask` remains vector by default and supports explicit method selection.

To test Cohere reranking in the search CLI, set `COHERE_API_KEY` in `.env` and run:

```bash
uv run python -m rag_library.cli.search "What is Church the cat's full name?" --book-id 18 --method hybrid --candidate-limit 100 --limit 5 --rerank --verbose
```

Replace `18` with your catalog's book ID. Hybrid reranking is enabled by default;
use `--no-rerank` for the RRF baseline. This step sends the question and the full
text of all distinct retrieved
chunks to Cohere's `rerank-v5.0-pro`: up to 200 chunks with 100 candidates per
method. It runs before the final five-chunk cutoff, so passages with low RRF
ranks can still be selected. It cannot recover passages absent from both
candidate lists. This adds one external API request; Cohere usage limits and
charges apply to your account. API errors fail the command without falling back.

Output shows the rerank score; `--verbose` also preserves the original RRF rank,
RRF score, both branch ranks/scores, and source identity. Rerank scores are
separate from RRF scores. Hybrid search, answering, agent tools, and evaluation
generation enable reranking by default. Vector and BM25 remain independent of
Cohere. Use `--no-rerank` in search/ask/eval commands or `rerank=False` in Python
to compare with RRF alone. Answer generation instructions are unchanged.
Automated retrieval evidence metrics and persistent lexical indexing remain deferred.

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

`POST /chat` streams one answer using a fresh LangChain agent invocation with
two tools, `list_available_books` and `answer_book_question`. Set `DATABASE_URL`, `OPENAI_API_KEY`,
and `COHERE_API_KEY`; the agent uses
`OPENAI_CHAT_MODEL` (default: `gpt-4o-mini`). Start the API as described above,
then send a request:

```bash
curl -N http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Which town does the Creed family move to?", "book_ids": [1]}'
```

Choose current IDs through `uv run python -m rag_library.cli.books`.
That catalog includes each book's `content_sha256`. The API accepts omitted or
empty `book_ids` to search the whole library. When supplied, IDs must be positive
integers and all attachments are validated before initializing the agent.
Invalid or unknown IDs return HTTP 422; they never fall back to the whole library.
For example, `{"message": "Which books are available?"}` needs no attachments.
The answer tool uses hybrid retrieval by default: 20 candidates per branch,
equal-contribution RRF with constant 60, Cohere reranking of the full union, and
five final passages. Retrieval method
and depth belong to `AgentContext`, alongside book attachments; the model cannot
select them. Notebook callers can set `retrieval_method="vector"` or `"bm25"`
when constructing a context, or set `candidate_limit` for hybrid experiments.
Set `rerank=False` on the context for the RRF baseline. The candidate default is
still 20 per method; set `candidate_limit=100` to reproduce the Church experiment.
The standalone `/chat` endpoint remains stateless. The web app uses the durable
conversation endpoints described below.

`AgentContext` in `agent/context.py` stores only validated `attached_book_ids`
and retrieval settings, and is passed to the agent. Empty IDs mean the whole
library; `answer_book_question` resolves the current catalog when retrieval runs.
Book metadata is not carried in the runtime context. Evaluation generation
resolves stable EPUB `book_refs` separately and saves book metadata with answers.
LangChain injects this context into the tools; the model sees only the question
argument on `answer_book_question`. Its `list_available_books` tool always queries
the entire catalog, regardless of attachments, without changing retrieval scope.
An empty library produces an explicit no-books tool result without calling the
retriever, embedding model, or reranker. The HTTP API serves `/chat`, `GET /books`, and
`GET /books/{id}/cover`; catalog listing is also available through the CLI.
The frontend loads public catalog metadata directly for a per-chat book selector;
empty selection searches the whole library, while explicit IDs restrict retrieval.

`list_available_books` returns a validated public object in the existing
`tool-output-available` event:

```json
{
  "books": [
    {
      "id": 1,
      "title": "Pet Sematary",
      "authors": "Stephen King",
      "categories": ["Horror", "Fiction"],
      "cover_url": "/books/1/cover"
    }
  ]
}
```

All books are returned in title/ID order, without pagination. `authors` and
`cover_url` may be `null`; `categories` is always a list. Internal hashes and image
bytes are excluded from the tool output. Cover URLs are relative to the backend
origin; a separate frontend origin must resolve or proxy them against that backend.
The cover endpoint returns the stored image and its content type, 404 for a missing
book or cover, and 503 for database failures. It does not require model credentials.
The agent is instructed to write a brief introduction in the user's language,
without repeating card data as a text list, or to explain that the catalog is
empty. The frontend shows tool activity in chronological order, followed by the
final introduction and book cards once the assistant turn settles.

Chat uses plain-text model output so answer tokens stream directly. Evaluations
and notebooks retain provider-native structured output through `get_agent()` and
`run_agent()`, independent of HTTP routes. Tool events come from actual execution.
Book-content questions use `answer_book_question`, a
thin wrapper around `BookRetriever`. It retrieves five chunks and returns source
passages with book ID/title, chapter, chunk references, and retrieval scores in
the tool log. The tool makes no chat-model call: the agent writes the answer
directly from these passages. A typical content question uses two agent model
calls: tool selection, then answer generation. The standalone `ask_question()`
workflow used by the `ask` CLI retains its own answer generation. The agent
uses the resolved IDs automatically. SQL filters with `book_id IN (...)`,
then selects the five closest chunks across the resolved books. A book need
not contribute a chunk to that global top five. Each source retains its own
book ID, title, chapter, and chunk index. The model cannot widen the scope by
supplying another book ID. With attachments, the caller chooses the books;
without attachments, all books available when retrieval runs are eligible.
Multiple attachments are supported per request.
Answers are limited to the retrieved context.

Messages must contain 1-4000 characters after trimming surrounding whitespace;
invalid requests return HTTP 422. Catalog and agent initialization failures
return HTTP 503; execution failures after streaming starts emit an `error` event.
Each request allows at most three model calls and two tool calls. Model calls
have a 30-second timeout with automatic retries disabled. These limits apply
to the agent; embedding and reranking calls retain their provider defaults.

The API has no authentication and assumes a single trusted user.
FastAPI's `/docs` remains available for inspecting the chat request schema.

### Streaming chat

`POST /chat` accepts `{messages, book_ids?}` and streams the next response using
the same agent, tools, attachment scope, and limits. It also retains the legacy
`{message, book_ids?}` single-question body; supply exactly one of the two fields.
It disables
structured model output so answer tokens can stream directly as plain text.
It uses `agent.astream_events(version="v2")` and FastAPI `StreamingResponse`, with
no additional dependencies or answer buffering.

```bash
curl -N http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the full name of Church, the cat?", "book_ids": [1]}'
```

For a follow-up, send ordered messages ending with the new user question:

```json
{
  "messages": [
    {"role": "user", "content": "Who is Louis Creed?"},
    {"role": "assistant", "content": "Louis Creed is a doctor."},
    {"role": "user", "content": "Where does he move?"}
  ],
  "book_ids": [18]
}
```

Assistant messages may include `tool_calls: [{id, name, args}]`; each call must
have a following `{role: "tool", tool_call_id, content: {...}}` result before the
conversation continues. The backend validates known tools, arguments, results,
unique call IDs, and pairing before execution. Client system/developer messages
are not accepted. Historical calls are context and are not executed again.

`agent/history.py` keeps a contiguous suffix of whole user turns within a
6,000 **estimated** token history budget, counting text, calls, and tool results.
The current question and server system prompt are always kept separately; this
budget does not cap new retrieval output or the full model context. If the most
recent historical turn is too large, all prior history is omitted. There is no
automatic summarization, partial-turn trimming, or server-side conversation store.
Incoming history is bounded to 1,000 message entries and 1,000,000 serialized
characters; assistant text entries are limited to 100,000 characters, and user
messages retain the 4,000-character limit. Invalid histories return HTTP 422.

The model uses history to resolve references, but each new book-content question
still retrieves fresh evidence. Current `book_ids` remain authoritative even if
historical messages mention other books. Standalone CLI and evaluation calls
remain independent questions.

The SSE wire format follows the
[AI SDK UI message stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol),
with `Content-Type: text/event-stream` and `x-vercel-ai-ui-message-stream: v1`.
Each frame is `data: <JSON>` followed by a blank line. Event types are defined
by the `ChatEvent` union in `api/streaming.py`:

| Event | Meaning |
| --- | --- |
| `start` | Assistant message begins; includes `messageId`. |
| `tool-input-available` | Tool execution starts; includes `toolName`, parsed `input`, and `toolCallId`. |
| `tool-output-available` | Tool completes; includes its `output` and matching `toolCallId`. |
| `data-source` | One retrieved passage; `data` includes `toolCallId`, `book_id`, `book_title`, `chapter_number`, `chunk_index`, `text`, and retrieval scores. |
| `text-start`, `text-delta`, `text-end` | A text block starts, streams `delta` strings, and ends; all carry the same block `id`. |
| `finish` | Agent completed successfully. |
| `error` | Execution failed; contains a generic `errorText` and ends the response. |

The last frame is `data: [DONE]`. Tool IDs are opaque execution IDs, shared
across tool and source events. Sources arrive when retrieval completes, before
the agent generates its answer; these are retrieved evidence, not a claim that
every passage was cited. The corpus has no page numbers. Text blocks stream as
the outer model emits them, including any text preceding a tool call. Internal
tool-model tokens, reasoning blocks, and partial tool-call arguments are filtered.

Request and attachment errors remain HTTP 422; initialization failures remain
HTTP 503. After streaming begins, execution failures use an SSE `error` event
because the HTTP status has already been sent. Disconnects close the event
iterator and cancel async graph execution; an already-running synchronous
retrieval/provider call may finish in its worker thread.

The frontend uses AI SDK transport to consume this protocol, retaining custom
`data-source` parts without a source panel. It requires `finish` before treating a
response as complete. The durable endpoint uses the same SSE protocol.

### Persistent conversations

The web app sends only the new question, its message ID and its book scope.
Python owns history. One server-generated UUID identifies the chat, its URL and
LangGraph `thread_id`. All storage uses the existing `DATABASE_URL`:

- `conversations`: title (first question), current books, timestamps and the last
  successfully completed checkpoint ID.
- `chat_turns`: ordered user/assistant UI messages, including tool parts, sources,
  sent book metadata and completion/interruption status.
- LangGraph tables: agent checkpoints, managed by `AsyncPostgresSaver` from
  `langgraph-checkpoint-postgres`. `PostgresStore` is not needed: cross-chat
  preferences/memory are outside this scope.

Tables are created lazily on the first conversation request; checkpoint migrations
run under a PostgreSQL advisory lock. Existing book/chunk rows are unchanged.
The web uses these endpoints through same-origin Next.js proxies:

| Endpoint | Purpose |
| --- | --- |
| `POST /chats` | Create a conversation with a stable UUID |
| `GET /chats` | List conversations, most recently updated first |
| `GET /chats/{id}` | Restore metadata and the complete visible transcript |
| `PATCH /chats/{id}` | Save `{book_ids: [...]}` after validating catalog membership |
| `POST /chats/{id}/messages` | Stream `{request_id, message, book_ids: [...]}` |

A request ID identifies a single accepted turn. Duplicate IDs and concurrent sends
on the same chat return 409 without executing the model. A PostgreSQL session
advisory lock serializes each conversation across workers and releases on connection
close. Different chats have independent locks.

Assistant presentation is snapshotted during streaming (up to every 500 ms as events
arrive, plus completed tools/sources), on interruption and before `finish`.
A hard process failure can lose output since the last snapshot. On reload, unfinished
turns are displayed as interrupted; there is no automatic replay or resumption.
The next question starts from the last **completed** checkpoint, excluding failed
attempts from model history while preserving them in the visible transcript.
Completion saves the UI turn and its checkpoint pointer in one application transaction.

A model-call middleware applies the existing 6,000 estimated-token window to whole
historical turns, preserving current-turn tool work. It changes only model input,
not stored history. Each invocation still supplies the current book scope through
`AgentContext`, including explicit retries with their original scope. CLI, evals
and the legacy `/chat` endpoint remain independent and have no checkpointer by default.

Offline tests run with `make check-api` and `pnpm --dir web test`. To exercise the
real PostgreSQL saver, CRUD, duplicate protection and cross-connection locks without
model calls, run:

```bash
RAG_TEST_POSTGRES=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  uv run python -m unittest discover -s tests -p test_chat_postgres.py
```

This opt-in test creates and removes an isolated schema in the configured database.

## Project layout

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
│       ├── components/            # Chat composition and tool result views
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

Generation now uses hybrid retrieval with Cohere reranking by default.
Save separate snapshots for
comparison with vector-only retrieval:

```bash
uv run python eval.py all --method hybrid --candidate-limit 20 --output evals/results/hybrid/answers.json
uv run python eval.py all --method hybrid --candidate-limit 20 --no-rerank --output evals/results/rrf/answers.json
uv run python eval.py all --method vector --output evals/results/vector/answers.json
```

`--method bm25` is also available. Final context remains five passages; hybrid
candidate depth defaults to 20 per method and explicit depths must be at least
five. The dataset, system instructions, and judge rubric are unchanged.
To reproduce the successful Church search's candidate depth, use
`--candidate-limit 100`. Keep this depth the same in reranked and RRF runs.

Run a single case with `--id`, or repeat the flag for several exact IDs:

```bash
uv run python eval.py all --id sematary-05 --candidate-limit 100 --max-concurrent 1 --output evals/results/church/answers.json
uv run python eval.py generate --id sematary-04 --id sematary-05 --output evals/results/selected/answers.json
uv run python eval.py score --id sematary-05 --output evals/results/church/answers.json --max-concurrent 1
```

Selection works in `all`, `generate`, and `score`, including `--manual`.
IDs must match exactly, including leading zeros. Unknown IDs fail before model
calls; repeated IDs run once in dataset order. Generation replaces the chosen
answers file with only the selected cases, so use a separate `--output` to keep
full-run answers. Score-only filters saved answers without modifying them.
`--max-concurrent 1` reduces parallel judge calls; it does not impose a provider
requests-per-minute limit.

The runner reads `evals/basic.json`: 29 reviewed English questions about Pet
Sematary (27 answerable and two unanswerable). These groups use separate native
DeepEval reports and stored runs. One additional question remains in the review draft.
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

Generated answers save `answerable`, `book_refs`, resolved `book_ids`, `attached_books`, and
`retrieval` settings (method, final top-k, effective candidate depth, RRF constant,
reranking enabled, and reranker model).
The same fields enter DeepEval case metadata, alongside tool records containing
source scores and branch ranks.
Rescoring uses the saved answers and scope without resolving or retrieving again;
Older answer files remain scoreable but do not acquire missing attachment or
retrieval metadata. Regenerate answers to evaluate a changed retrieval method.
Files without `answerable` remain scoreable as answerable cases with a CLI
notice; labels are never inferred from expected-answer wording or a changed
dataset. Generate fresh answers to preserve explicit dataset labels.

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

Scoring defaults to `--metrics core`: Answer Correctness and Faithfulness.
Use `--metrics all` in `all` or `score` to include retrieval diagnostics:

```bash
uv run python eval.py score --id sematary-05 --output evals/results/church/answers.json --metrics all --max-concurrent 1
```

Thresholds are defined in `src/rag_library/deepeval_evaluation.py`:

| Metric | What it checks |
| --- | --- |
| Contextual relevancy | Whether retrieved content is relevant to the question |
| Contextual recall | Whether retrieved content supports the expected answer |
| Contextual precision | Whether relevant chunks rank ahead of irrelevant chunks |
| Faithfulness | Whether the final answer is grounded in the retrieved content |
| Answer correctness (G-Eval) | Whether the final answer matches the expected facts, allowing paraphrases |

Answerable cases pass when both Correctness and Faithfulness reach **0.70**.
Unanswerable cases pass based on Correctness alone; Faithfulness is score-only.
With `--metrics all`, all three retrieval metrics are score-only in both groups.
DeepEval's native `threshold=None` preserves scores/reasons without pass/fail
verdicts; terminal rows display `NONE` and aggregate pass rates display `N/A`.
Each nonempty group creates a separate native report under
`evals/results/answerable/` or `evals/results/unanswerable/` and a separate
SQLite run. The command succeeds only when all scored cases in both groups pass
and no generation/context errors exist. These initial thresholds and judge
scores are a starting point for iteration, not an objective measure of quality.
The curated answers are the correctness reference: review ambiguous questions
and incorrect references before interpreting failures as RAG regressions.

The judge defaults to `OPENAI_CHAT_MODEL`. Override it independently in `.env`:

```dotenv
EVAL_JUDGE_MODEL=gpt-5.4
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

Each scoring group's run is appended to `evals/results/deepeval.db`, including cases,
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
| `--metrics` | `core` | Core answer metrics, or `all` including score-only retrieval diagnostics; scoring stages only |
| `--manual` | Disabled | Alias for `generate`; cannot be combined with `score` |

The legacy alias can also be run explicitly:

```bash
uv run python eval.py --manual
```

The existing
`notebooks/03_basic_evals.ipynb` still uses the original manual workflow.
