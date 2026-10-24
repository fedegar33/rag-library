# RAG Library web

Dark chat UI with TypeScript, Next.js App Router, Tailwind CSS v4, shadcn/ui,
and shadcn chat patterns. `useChat` from `@ai-sdk/react` owns messages, streaming status, errors, and
cancellation. Its AI SDK transport consumes Python's UI message SSE protocol;
agent and retrieval logic remain in Python.

Use Node 24 and pnpm 10.33.2. From the repository root:

```bash
make setup
cp web/.env.example web/.env.local
uv run python -m rag_library.cli.books
```

`BACKEND_API_URL` defaults to `http://127.0.0.1:8000`. Restart the web server
when changing this configuration. `CHAT_BOOK_IDS` is no longer used: each chat
starts with the whole library and users choose books in the composer.

Run `make api` and `make web` in separate terminals. Open http://localhost:3000.
The API needs the root `.env` database and model configuration; default hybrid
reranking also requires Cohere. Keep credentials in Python's root `.env`, never
in `NEXT_PUBLIC_*` variables. The picker reports catalog loading errors and offers a manual retry.

## Chat behavior

- Create and switch chats; drafts and messages live in memory and reset on refresh.
- Send a question of up to 4,000 characters. Enter sends; Shift+Enter adds a line.
- Answer text streams as it arrives. A simple status indicates retrieval activity.
- Switching to a different chat cancels the request and preserves its partial reply.
- Failures retain partial output with an interrupted label. Retry resends the
  latest failed question with its original book selection, retaining the original reply. Requests never retry automatically.
- Recent conversation, including completed tool calls and results, is sent to
  the agent. Python uses a 6,000 estimated-token sliding window of complete turns;
  the full transcript stays visible. There are no automatic summaries or server
  persistence. Stop interrupts the current response; no background generation.
- Books opens a right panel (full screen on mobile), with an alphabetical catalog,
  checkboxes, and an Apply button. Closing without applying discards changes.
- The composer shows up to two removable book chips and +N; no chips means Whole
  library. Selection is per chat, retained across switches, and locked during a response.
- Each question records and displays its sent scope. Uploads, source panels, and
  conversation persistence remain deferred. Source events stay in message state.

## Streaming contract

The browser uses `useChat` with a `DefaultChatTransport` subclass to POST
`{ messages, book_ids }` to `/api/chat`. `chat-history.ts` converts text and completed
dynamic tools into user/assistant/tool messages. Incomplete calls, duplicate source
events, display metadata, and unanswered past questions are excluded; original UI
messages are not modified. Tool call IDs link each call with its result. The Next.js
route validates the envelope and positive integer IDs, then Python validates the
full history and selects its sliding window. The latest question's selection
controls retrieval regardless of historical book references. Legacy single-message
requests remain accepted. Requests are bounded to 1,000 history entries and
1,000,000 serialized characters in Python, independently of the model token budget.
It pipes the upstream body without accumulating the answer and forwards request
cancellation. Browser requests need no backend CORS configuration.

Python supplies AI SDK UI message SSE v1 events. The client handles text deltas,
tool activity, source data, `finish`, and `error`. A closed stream or `[DONE]`
without `finish` is interrupted, and an empty completed answer is treated as an
error. HTTP 422/503 and connection failures produce useful errors before streaming.
Each conversation owns an SDK `Chat` instance, and `useChat` subscribes to the
active instance. The shell retains sidebar metadata, book selections, and drafts. Text, tool
states, and custom `data-source` parts stay in SDK `UIMessage.parts`; no custom
message accumulator or request controller is maintained. Switching calls the
hook's `stop()`. Retry explicitly resends the question as a new turn, keeping the
original interrupted reply. Automatic tool follow-ups and stream resumption are
disabled. A small transport guard checks `finish` and nonempty text or a validated
catalog result (including an empty catalog), because the
SDK otherwise accepts an ordinary end of stream.

The Next route is a transport proxy; it does not execute another agent.
`GET /api/books` proxies Python `GET /books` for validated public catalog metadata,
without model calls. Empty book IDs mean whole-library retrieval; explicit IDs
restrict retrieval, and Python rejects missing books without widening the scope.

See [DESIGN.md](DESIGN.md) for visual and interaction rules.

## Commands

| Repository root | Inside `web/` | Purpose |
| --- | --- | --- |
| `make web` | `pnpm dev` | Development server |
| `make check-web` | `pnpm lint` and `pnpm typecheck` | ESLint and TypeScript |
| `make build` | `pnpm build` | Production build |
| — | `pnpm test` | Offline proxy and SSE consumer tests |
| — | `pnpm start` | Serve the production build |

Tests use Node 24's native TypeScript stripping and test runner. No model requests
are made. They exercise fragmented SSE/UTF-8, incremental updates, source identity,
HTTP/in-stream failures, premature EOF, cancellation, and server-side configuration.

`pnpm-workspace.yaml` records dependency build-script policy for this app;
there is no root JavaScript workspace or monorepo framework.
Routes live in `src/app/`; application UI in `src/components/`; primitives in
`components/ui/`; app-specific chat views in `components/`; helpers in `src/lib/`.
See [AGENTS.md](AGENTS.md) and [the root README](../README.md).


## Chat UI primitives

The chat uses shadcn Message Scroller, Message/Bubble, Input Group, and Trace
directly. The former AI SDK Elements Conversation wrapper and use-stick-to-bottom
dependency have been removed. Message Scroller anchors each user turn near the
top and follows streaming only while the reader stays at the live edge.

`ChatShell` coordinates chats and the SDK; `ChatMessage` presents a turn, with
Streamdown for assistant Markdown and literal user text. `ChatComposer` preserves
the existing draft, Enter/Shift+Enter, and IME behavior on Input Group. `ToolResult`
uses an explicit tool-name mapping for catalog cards. `ToolActivity` renders the
Trace status in stream order. Successful catalog cards wait until the assistant
turn settles, so preamble, counted status, and final introduction precede them.
Completed results survive a later interruption; narration remains model-generated.
There are no artificial delays. Python remains responsible for execution; no automatic tool follow-up,
new backend protocol, persistence, uploads, or source panel is introduced.
