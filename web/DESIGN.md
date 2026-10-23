# RAG Library design guidelines

A quiet reading space with the clarity of a chat application. Hardcover inspires
its blue-gray palette and literary typography; Codex inspires its conversation
sidebar and focused composer. These are visual references, not layouts to copy.

## Color and typography

Use the shadcn semantic tokens in `src/app/globals.css`. The app is dark only.
The main surface is `--background` (#202833); the sidebar is deeper (#1a222d).
Raised surfaces use `--card` or `--muted`. Warm gold `--primary` (#d8bc82)
marks the primary action, identity, and selected details. Keep accents sparse.
Use soft off-white for primary text and `--muted-foreground` for secondary text.

Use the system sans-serif stack for interface controls and conversation text.
Use Georgia for the welcome heading and small editorial details. Keep body copy
at 13–14px with generous line height; use smaller text only for metadata. Balance
headings, allow long messages to wrap, and truncate sidebar titles to one line.

## Layout and surfaces

Use a fixed-height app shell with independently scrolling navigation and messages.
The desktop sidebar is 280px; the reading/composer column is at most 816px,
including its gutters. The composer remains beneath the message area.
Below 700px, replace the sidebar with a modal drawer using native dialog focus
management, Escape dismissal, and focus restoration.

Use 8–15px radii on controls and surfaces, subtle translucent borders, and modest
shadows on raised surfaces. Avoid surrounding assistant messages with cards.
User messages have a muted bubble; assistant replies sit directly on the page.
No decorative motion or load animations. Scrolling is instant in this prototype.

## Interaction and accessibility

Provide visible keyboard focus, named icon buttons, 40px minimum action targets,
and a skip link to the composer. Enter sends; Shift+Enter inserts a newline;
composition with an IME must not accidentally send. Empty messages cannot send.
Suggestion cards fill the composer so the user can review before sending.
Preserve each chat's draft when switching conversations.

The live testing UI uses the server-configured book IDs for every conversation;
book labels show catalog IDs until catalog selection is implemented. There is no
attachment picker, upload flow, or citation UI. Source events remain attached to SDK `UIMessage.parts`
on the assistant message in memory, preserving provenance for a future source view.

Stream answer text progressively and show a quiet text status while thinking or
searching. Only one request runs at a time. Switching to another chat cancels the
active stream and retains its partial answer with an interrupted label. Keep
partial output on failure and offer manual Retry only on the latest failed reply;
retry resends the same question as a new turn and retains the original partial
answer. Never
retry automatically. No Stop button or background generation in this milestone.

Make it clear that each question is independent: the message history is for
display only and is not sent to Python. Chats reset on refresh; no browser storage.
Show a useful setup error when test books are unconfigured; never imply a sample
reply is a live answer. Model execution and credentials remain in Python.

Keep app-specific UI in `src/components/`, primitives in `components/ui/`, and
AI Elements in `components/ai-elements/`. Extend the existing tokens and shared
components before adding dependencies or another design system.
