# RAG Library API

A modern Python API scaffold built with [FastAPI](https://fastapi.tiangolo.com/) and [uv](https://docs.astral.sh/uv/).

## Requirements

- Python 3.12+
- uv

## Setup

Create the virtual environment and install the locked dependencies:

```bash
uv sync
```

This creates `.venv/` and `uv.lock`. Activate the environment if you want a traditional shell workflow:

```bash
source .venv/bin/activate
```

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

The starter notebook in `notebooks/` calls the FastAPI app in-process and includes a small LangChain prompt experiment. Keep reusable application logic in `src/rag_library/`, then move stable experiments into tested services and endpoints.

## Verify

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Ingest an EPUB

To inspect EPUB metadata and chapter names without ingesting a book into the
database, run:

```bash
uv run epub-ingestion-debug "./book.epub"
```

The command prints the book title followed by its table-of-contents entries,
including named sections and numbered chapters.

Set `DATABASE_URL` and `OPENAI_API_KEY` in `.env`, then run:

```bash
uv run python -m rag_library.ingest --file "./book.epub"
```

The database must be PostgreSQL with the `pgvector` extension available. The
first run creates the vector extension and application tables automatically.
Ingestion uses 1000-character chunks with 200-character overlap and
`text-embedding-3-small` by default. Re-ingesting identical EPUB content
replaces its existing book and chunks.

## Search ingested books

Run a semantic search against the stored chunks:

```bash
uv run python -m rag_library.search "something"
uv run python -m rag_library.search "something" --limit 10
uv run python -m rag_library.search "something" --verbose
uv run python -m rag_library.search "something" --chapter 1,2,3
```

Results are ordered by pgvector cosine similarity. The default output shows
compact previews; use `--verbose` to print each complete matching chunk.
Use `--chapter` to restrict results to one or more 1-based EPUB document/chapter
numbers.

## Ask questions about ingested books

Retrieve the top five chunks and ask the configured chat model to answer using
only that book context:

```bash
uv run python -m rag_library.ask "Who is Nicolas?"
uv run python -m rag_library.ask "Who is Nicolas?" --top-k 8
```

Set `OPENAI_CHAT_MODEL` to choose the chat model; it defaults to
`gpt-4o-mini`. The command prints the generated answer and the source chunks
used to produce it. Use `--top-k` to control how many chunks are supplied as
context; it defaults to 5.

## Catalog agent

`POST /agent` answers one independent message using a LangChain agent with
one tool, `list_books`. Set `DATABASE_URL` and `OPENAI_API_KEY`; the agent uses
`OPENAI_CHAT_MODEL` (default: `gpt-4o-mini`). Start the API as described above,
then send a request:

```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"message": "What books are available?"}'
```

Example response (the answer text depends on the model):

```json
{
  "answer": "A Book is available.",
  "tool_calls": [
    {
      "name": "list_books",
      "arguments": {},
      "result": {
        "books": [
          {"id": 1, "title": "A Book", "authors": null, "language": "es"}
        ]
      }
    }
  ]
}
```

The catalog reads all ingested books, ordered by title and ID, without reading
passages or creating embeddings. Unknown metadata stays `null`. An empty table
returns `{"books": []}`; ingestion must have created the schema beforehand.
The model's final answer uses provider-native structured output with a strict
Pydantic `AgentAnswer` schema. The server reads the validated `structured_response`
and combines it with tool records; the model does not generate the tool log.
The configured OpenAI model must support structured output together with tools.
Invalid structured answers return HTTP 503, like other execution errors.
The tool log comes from actual execution messages. Greetings can return an
empty `tool_calls` list. Summaries and questions about book contents are not
supported by this agent yet; the existing `ask` CLI remains available for RAG.

Messages must contain 1-4000 characters after trimming surrounding whitespace;
invalid requests return HTTP 422. Database, provider, and execution-limit errors
return HTTP 503 with `{"detail": "Agent service unavailable"}` and server logs.
Each request allows at most three model calls and two tool calls. Model calls
have a 30-second timeout with automatic retries disabled.

This JSON endpoint is for local experiments: it has no authentication,
pagination, conversation history, or session persistence. `/` and `/health` do
not initialize the agent or require credentials. The endpoint is also available
in `/docs`.

## Streaming chat with AI SDK

`POST /chat` accepts AI SDK UI messages and emits the
[UI message SSE protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol),
with `x-vercel-ai-ui-message-stream: v1`. It uses the same catalog tool, model,
prompt, and execution limits as `/agent`, with plain-text token streaming rather
than structured final output. The JSON endpoint is unchanged.

```bash
curl -N http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"id":"u1","role":"user","parts":[{"type":"text","text":"What books are available?"}]}]}'
```

Configure an AI SDK client with the default transport:

```tsx
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';

export function useLibraryChat() {
  return useChat({
    transport: new DefaultChatTransport({
      api: '/chat',
      prepareSendMessagesRequest: ({ messages }) => ({
        body: { messages: messages.slice(-40) },
      }),
    }),
  });
}

// In your component: const { messages, sendMessage, status, error, stop } = useLibraryChat();
// Submit: sendMessage({ text: input }); Cancel: stop();
// Render text parts with part.type === 'text' and part.text.
// Tool parts have type 'tool-list_books', toolCallId, state, input, and output.
```

Serve the frontend and API through the same origin, or proxy `/chat`
through the frontend server. Cross-origin CORS is not configured automatically.
AI SDK sends history from the client on each turn; the server keeps no sessions.
Only user and assistant roles are accepted. User messages support text only;
assistant text is retained, while UI tool results and reasoning are ignored when
building model history. Book metadata claims still require a fresh catalog call.

Requests support at most 40 messages, 4000 trimmed text characters per message,
and 24000 total text characters. Oversized or invalid history returns HTTP 422;
the client should send a smaller history when necessary. IDs and other UI message
metadata are accepted but not used for server persistence. The last message must
be a nonempty user message; submitting after a server tool result does not require
an automatic extra client turn.

Streams include text start/delta/end, tool input/output, step boundaries, message
completion, and `[DONE]`. Provider/database/limit failures after streaming begins
produce a generic `error` event and `[DONE]`, rather than changing the HTTP status
or reporting success. Initialization failures still return HTTP 503. Stopping the
client cancels ongoing model generation and closes the stream; a synchronous SQL
query already running in a worker thread may finish. There is no server-side
conversation storage or stream resumption.

## Evaluate retrieval and answers

The end-to-end QA cases are in `evals/baseline.json`. The primary retrieval
benchmark is `evals/retrieval_v1.json`: 18 Spanish questions about *Una semana
en la nieve*, with chunk-level relevance labels, including 8 exact-term cases.
English cross-language questions are kept in the separate diagnostic set
`evals/retrieval_en_diagnostic_v1.json` (13 cases) and do not affect the
Spanish benchmark scores. The cases cover factual paraphrases, entities,
exact terms, multi-hop questions, chapter filters, and cross-language
retrieval. Dataset labels contain source identifiers rather than book passages.

Set `LANGSMITH_API_KEY` in `.env`, then run:

```bash
uv run python -m rag_library.evaluation
uv run python -m rag_library.evaluation --top-k 8
uv run python -m rag_library.evaluation --dataset ./evals/my-cases.json
uv run python -m rag_library.evaluation --task retrieval
uv run python -m rag_library.evaluation --task retrieval --top-k 10
uv run python -m rag_library.evaluation --task retrieval --retrieval-language en
```

The default `qa` task runs end-to-end answer evaluation. The `retrieval` task
calls semantic search directly and scores chunk hit@k, chunk recall@k, MRR@k,
chapter recall@k, and chapter-filter compliance. It makes embedding calls but
does not call the answer model or judge. Both tasks upload full traces,
including retrieved book passages, to LangSmith. Each local dataset suite and
version is synchronized to its own LangSmith dataset, so Spanish benchmark
scores and English diagnostic scores stay separate.
Use `--retrieval-language en` to run the English diagnostic set; the retrieval
task defaults to the Spanish primary set.

Retrieval case labels use chunk indices from the current ingestion. If chunking
changes, review the labels and increment the dataset version. To add a
retrieval case, use this shape for each entry in `cases`:

```json
{
  "id": "unique-case-id",
  "question": "Pregunta basada en un libro ingerido",
  "query_type": "fact_paraphrase",
  "language": "es",
  "chapter_filter": null,
  "expected_sources": [
    {"book_title": "Book title", "chapter_number": 1, "chunk_index": 12}
  ]
}
```

Each retrieval dataset also declares its suite (`es_primary` or
`en_diagnostic`) and version at the top level. A suite may contain cases in
only its declared language.

For chapter-filter cases, set `query_type` to `chapter_filtered` and list the
allowed 1-based chapter numbers in `chapter_filter`. Keep EPUB files and
passages out of source control.

## Project layout

```text
src/rag_library/  Application package
notebooks/         Interactive API and RAG experiments
tests/             API tests
pyproject.toml     Project metadata and tool configuration
uv.lock            Reproducible dependency lockfile
```
