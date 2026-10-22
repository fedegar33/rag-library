# Web app

Root `AGENTS.md` applies here too. Python remains at the repository root;
`web/` is an independent pnpm-managed Next.js App Router application.

## Commands

From the repository root, use `make setup`, `make web`, `make check-web`,
and `make build`. From `web/`, use `pnpm dev`, `pnpm lint`, `pnpm typecheck`,
`pnpm build`, and `pnpm start` (after a build).
Use Node 24 and pnpm 10.33.2, recorded in `.node-version` and `package.json`.
Commit `pnpm-lock.yaml` with dependency changes.

## Structure and scope

- Keep routes/layouts in `src/app/`, shadcn primitives in `src/components/ui/`,
  AI Elements in `src/components/ai-elements/`, and frontend helpers in
  `src/lib/`. Use the `@/*` import alias.
- Use strict TypeScript, Tailwind CSS v4, and existing shadcn theme tokens.
  Prefer Server Components; add client boundaries for interactive behavior.
- Add individual shadcn or AI Elements components as needed through their
  registries; do not install the entire component catalog by default.
- This is a starter page. Live chat, book selection, streaming, conversation
  persistence, API calls, and LangChain.js are deferred.
- Agent execution, retrieval, database access, and model credentials belong
  to Python. The AI SDK dependency supports AI Elements types; it does not
  establish a second agent. Python owns the streaming backend contract.
- `.env.local` is local configuration. `BACKEND_API_URL` is reserved for future
  server-side calls and is currently unused. Never expose model keys through
  `NEXT_PUBLIC_*` variables. Keep model keys in the root `.env`.
- Preserve book/chapter/chunk provenance when API integration is added.
  Python `/chat` streams independent messages with explicit book attachments
  using the AI SDK UI message SSE protocol.

Run `make check-web` and `make build` for scaffold changes, and backend checks
when changing Python code or the shared Makefile.
