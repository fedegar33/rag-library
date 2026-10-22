# RAG Library web

Minimal Next.js App Router starter with TypeScript, Tailwind CSS v4,
shadcn/ui, and the AI Elements conversation component. Python remains at the
repository root. LangChain.js and API integration are deferred.

Use Node 24 and pnpm 10.33.2. From the repository root:

```bash
make setup
cp web/.env.example web/.env.local
make web
```

Open http://localhost:3000. The starter runs without the API, database, or
model credentials. `BACKEND_API_URL` is reserved for future server-side API
calls and is not read yet. Keep model keys in the root `.env`.

Run the API separately with `make api`. `POST /chat` accepts
`{ message, book_ids }` and streams AI SDK SSE events for text, tool activity,
and sources. Frontend integration and conversation history remain deferred.

## Commands

| Repository root | Inside `web/` | Purpose |
| --- | --- | --- |
| `make web` | `pnpm dev` | Development server |
| `make check-web` | `pnpm lint` and `pnpm typecheck` | ESLint and TypeScript |
| `make build` | `pnpm build` | Production build |
| — | `pnpm start` | Serve the production build |

`pnpm-workspace.yaml` records dependency build-script policy for this app;
there is no root JavaScript workspace or monorepo framework.

Add UI components individually from this directory:

```bash
pnpm dlx shadcn@latest add button
pnpm dlx shadcn@latest add https://elements.ai-sdk.dev/api/registry/message.json
```

Routes live in `src/app/`; UI primitives in `src/components/ui/`;
AI Elements in `src/components/ai-elements/`; helpers in `src/lib/`.
See [AGENTS.md](AGENTS.md) for frontend conventions and
[the root README](../README.md) for backend setup and workflows.
