# Web app

Root `AGENTS.md` applies here too. Python remains at the repository root;
`web/` is an independent pnpm-managed Next.js App Router application.

## Commands

From the repository root, use `make setup`, `make web`, `make check-web`,
and `make build`. From `web/`, use `pnpm dev`, `pnpm lint`, `pnpm typecheck`,
`pnpm build`, and `pnpm start` (after a build).
Use Node 24 and pnpm 10.33.2, recorded in `.node-version` and `package.json`.
Commit `pnpm-lock.yaml` with dependency changes.

## Design

Read [DESIGN.md](DESIGN.md) before changing the interface. It records the
approved dark palette, typography, layout, and interaction conventions.

### Chat UX references

When a proposed change introduces or materially alters a chat interaction,
consult the relevant current references before implementing it. Use judgment:
routine styling fixes and internal refactors do not need a research pass.

- [AI UX Playground — Chat UX](https://aiuxplayground.com/frameworks/chat-ux):
  primary framework for context, onboarding, input, progress visibility,
  evidence, refinement, structured responses, and error recovery.
- [Shape of AI](https://www.shapeof.ai/): concrete patterns and product examples,
  especially controls, attachments, citations, and references.
- [Google — Design AI user experiences](https://web.dev/learn/ai/ux-patterns):
  combining conversation with structured UI and making system state visible.
- [Google — People + AI Guidebook](https://pair.withgoogle.com/guidebook-v2/chapters)
  and [Microsoft HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/):
  expectations, user control, and recovery from failures.
- [NN/g — Explainable AI in Chat Interfaces](https://www.nngroup.com/articles/explainable-ai/):
  evidence presentation and avoiding misleading signals of reliability.

Read the sections relevant to the decision; do not review every resource for
all changes. Apply patterns to this book RAG app's actual capabilities and
approved design rather than copying features or expanding scope. Consider the
whole turn: active book context, real progress, streaming and interruption,
text/tool-result ordering, usable output, source verification, and recovery.
Briefly explain a reference-backed decision when it materially shapes the UX.
User decisions and this project's conventions take precedence.

## Structure and scope

- Keep routes/layouts in `src/app/`, shadcn primitives in `src/components/ui/`,
  app-specific chat components in `src/components/`, and frontend helpers in
  `src/lib/`. Use the `@/*` import alias.
- Keep small, private components together when that improves readability.
  Extract them for an independent responsibility, reuse, or a clearer parent
  file; avoid arbitrary line limits and premature abstractions.
- Use strict TypeScript, Tailwind CSS v4, and existing shadcn theme tokens.
  Prefer Server Components; add client boundaries for interactive behavior.
- Add individual shadcn components through their registry as needed; compose
  AI Elements patterns directly from `components/ui/` primitives. Do not restore
  compatibility wrappers or install the entire component catalog by default.
- Use Message Scroller for transcript position, Message/Bubble for turns,
  Input Group for the composer, and Trace for discreet tool status lines.
  Streamdown renders assistant Markdown; tools keep structured result views.
  Keep Python execution and SDK chat state separate from presentation.
- Preserve chronological model text and tool activity. Catalog result views
  wait for the assistant turn to settle; tool completion and text-end alone
  must not release cards. Keep valid results after later interruption. Show
  the catalog count in the tool status, and never synthesize agent narration.
- The UI consumes Python `/chats/{id}/messages` through the same-origin Next.js
  `/api/chat` proxy. `useChat` owns SDK messages/status/cancellation through one
  SDK `Chat` per conversation, hydrated from stored UI messages. Python owns
  checkpoints and history; send only `{chat_id, request_id, message, book_ids}`.
  Chats live at `/chats/<id>` and restore through `/api/chats/<id>`; create/list
  and scope updates use the conversation resource proxies. Save book selection
  before changing it locally and show failures without broadening retrieval.
  Drafts stay in memory only. Preserve the full transcript independently of the
  model's token window. The legacy transport/history adapter remains for independent
  stateless callers. Source panels, background generation and LangChain.js remain deferred.
- Agent execution, retrieval, database access, and model credentials belong
  to Python. AI SDK React manages frontend chat state and transport; it does not
  establish a second agent. Python owns the streaming backend contract.
- `.env.local` configures server-only `BACKEND_API_URL`. The composer owns a
  selection per chat: empty means the whole library; explicit IDs restrict
  retrieval exclusively to those books. `CHAT_BOOK_IDS` is no longer used.
  The proxy validates client IDs and Python validates catalog membership.
  Never expose model keys through `NEXT_PUBLIC_*`; keep them in the root `.env`.
- Load picker metadata through `GET /api/books` → Python `GET /books`, without
  running the agent. Keep selection edits provisional until Apply; closing
  discards them. Display up to two removable chips and a +N shortcut. Disable
  scope changes during generation and provide Stop. New chats start unfiltered.
  Save book IDs and titles on each user message; retries use its original scope.
  Catalog errors retain current selection and never broaden retrieval silently.
- Preserve book/chapter/chunk provenance when API integration is added.
  Python streams answers with explicit book attachments and checkpoint-backed history
  using the AI SDK UI message SSE protocol.

Run `pnpm test`, `make check-web`, and `make build` for frontend integration
changes, and backend checks when changing Python code or the shared Makefile.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
