# RAG Library web

Dark chat UI with TypeScript, Next.js App Router, Tailwind CSS v4, shadcn/ui,
and AI Elements. `useChat` from `@ai-sdk/react` owns messages, streaming status, errors, and
cancellation. Its AI SDK transport consumes Python's UI message SSE protocol;
agent and retrieval logic remain in Python.

Use Node 24 and pnpm 10.33.2. From the repository root:

```bash
make setup
cp web/.env.example web/.env.local
uv run python -m rag_library.cli.books
```

Set `CHAT_BOOK_IDS` in `web/.env.local` to current catalog IDs, for example
`CHAT_BOOK_IDS=17,18` if those IDs exist in your catalog. All conversations share
these test books. Do not use EPUB hashes or the sample IDs without checking your
catalog. `BACKEND_API_URL` defaults to `http://127.0.0.1:8000`. Restart the web
server after changing configuration.

Run `make api` and `make web` in separate terminals. Open http://localhost:3000.
The API needs the root `.env` database and model configuration; default hybrid
reranking also requires Cohere. Keep credentials in Python's root `.env`, never
in `NEXT_PUBLIC_*` variables. The web app shows a setup error and disables sending
when test book IDs are missing or invalid.

## Chat behavior

- Create and switch chats; drafts and messages live in memory and reset on refresh.
- Send a question of up to 4,000 characters. Enter sends; Shift+Enter adds a line.
- Answer text streams as it arrives. A simple status indicates retrieval activity.
- Switching to a different chat cancels the request and preserves its partial reply.
- Failures retain partial output with an interrupted label. Retry resends the
  latest failed question, retaining the original reply. Requests never retry automatically.
- **Every question is independent.** Previous messages are displayed but are not
  sent to the agent. There is no session memory, background generation, or Stop button.
- Attachments are read-only catalog ID labels. Book selection, uploads, source
  panels, and conversation persistence remain deferred. Source events are retained
  in assistant message state for a future provenance view.

## Streaming contract

The browser uses `useChat` with a `DefaultChatTransport` subclass to POST `{ message }` to
`/api/chat`. The Next.js route validates the message and injects the configured
book IDs before forwarding `{ message, book_ids }` to Python's `POST /chat`.
It pipes the upstream body without accumulating the answer and forwards request
cancellation. Browser requests need no backend CORS configuration.

Python supplies AI SDK UI message SSE v1 events. The client handles text deltas,
tool activity, source data, `finish`, and `error`. A closed stream or `[DONE]`
without `finish` is interrupted, and an empty completed answer is treated as an
error. HTTP 422/503 and connection failures produce useful errors before streaming.
Each conversation owns an SDK `Chat` instance, and `useChat` subscribes to the
active instance. The shell retains only sidebar metadata and drafts. Text, tool
states, and custom `data-source` parts stay in SDK `UIMessage.parts`; no custom
message accumulator or request controller is maintained. Switching calls the
hook's `stop()`. Retry explicitly resends the question as a new turn, keeping the
original interrupted reply. Automatic tool follow-ups and stream resumption are
disabled. A small transport guard checks `finish` and nonempty text, because the
SDK otherwise accepts an ordinary end of stream.

The Next route is a transport proxy; it does not execute another agent.

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
`components/ui/`; AI Elements in `components/ai-elements/`; helpers in `src/lib/`.
See [AGENTS.md](AGENTS.md) and [the root README](../README.md).
