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
- The UI consumes Python `/chat` through the same-origin Next.js `/api/chat`
  streaming proxy. `useChat` owns SDK messages/status/cancellation through one
  SDK `Chat` instance per conversation; the shell owns only sidebar metadata and
  drafts. Chats are in memory; every question is independent.
  Book selection, conversation history in the agent, persistence, source panels,
  background generation, and LangChain.js are deferred.
- Agent execution, retrieval, database access, and model credentials belong
  to Python. AI SDK React manages frontend chat state and transport; it does not
  establish a second agent. Python owns the streaming backend contract.
- `.env.local` configures server-only `BACKEND_API_URL` and required
  `CHAT_BOOK_IDS` (comma-separated current catalog IDs). All conversations share
  these test books. The proxy injects IDs and sends only the latest message.
  Never expose model keys through `NEXT_PUBLIC_*`; keep them in the root `.env`.
- Preserve book/chapter/chunk provenance when API integration is added.
  Python `/chat` streams independent messages with explicit book attachments
  using the AI SDK UI message SSE protocol.

Run `pnpm test`, `make check-web`, and `make build` for frontend integration
changes, and backend checks when changing Python code or the shared Makefile.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
