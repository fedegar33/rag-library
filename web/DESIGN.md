# RAG Library design guidelines

A quiet, minimal reading space inspired by Claude: a conversation list on the
left, a focused chat area, and a composer at the bottom. Interface text is English.

## Color and typography

Use the shadcn semantic tokens in `src/app/globals.css`. The app is dark only.
The main surface is midnight blue `--background` (#172536), with a deeper
`--sidebar` (#111e2d) and a gently raised composer `--card` (#203247).
Primary text is ivory (#eeeae2), secondary text is muted blue (#a7b5c5), and
interactive accents are pale blue (#b9cfe5). Avoid gold and decorative accents.

Use the system sans-serif stack for controls, sidebar titles, user messages, and
status labels. Use Georgia for assistant replies and the welcome heading.
Assistant replies are 16px on desktop and mobile with generous line height; controls
are 13–15px. Truncate long sidebar titles and allow message text to wrap.

## Layout and surfaces

Use a fixed-height app shell with independently scrolling navigation and messages.
The desktop sidebar is 248px; the reading/composer column is at most 768px,
including its gutters. The composer remains beneath the message area.
Below 700px, replace the sidebar with a modal drawer using native dialog focus
management, Escape dismissal, and focus restoration.

The sidebar has a plain wordmark, a discreet “New chat” button, and a single-line
“Recents” list. Avoid per-conversation icons, book counts, decorative badges,
fake profile controls, and suggestion cards. The welcome state is a short serif
heading and a single supporting line. The header shows only the conversation
title and sidebar toggle. Show the active book scope beside the composer with removable chips.

Use subtle surface differences and soft corners. Assistant replies sit directly
on the page; user messages use a muted blue bubble. The composer has a faint
outline with a clear focus state. No decorative motion or load animations.
Scrolling is instant.

## Interaction and accessibility

Provide visible keyboard focus, named icon buttons, 40px minimum action targets,
and a skip link to the composer. Enter sends; Shift+Enter inserts a newline;
composition with an IME must not accidentally send. Empty messages cannot send.
Preserve each chat's draft when switching conversations.

The Books button opens a modal right panel, full screen below 700px. List
existing books alphabetically with small covers, titles, authors, and checkboxes;
no search or upload in this version. Keep the footer visible while the list
scrolls. Changes are provisional until Apply; dismissal discards them. No
selection means Whole library; selecting books restricts retrieval to those books.
Show at most two removable title chips and +N. Removing the last restores Whole
library. Disable all scope controls while generating. Each new chat starts with
the whole library. Selection and drafts survive chat switches in memory only.
Each user message shows its sent scope; retry uses that original selection.
Loading and catalog errors are explicit; failed loading cannot clear a selection.
Source events remain in SDK message parts for a future citation view.

Stream answer text progressively and show a quiet text status while thinking or
searching. Only one request runs at a time. Switching to another chat cancels the
active stream and retains its partial answer with an interrupted label. Keep
partial output on failure and offer manual Retry only on the latest failed reply;
retry resends the same question and original book selection as a new turn and retains the original partial
answer. Never
retry automatically. The send button becomes Stop during generation; no background generation.

Make it clear that recent conversation is used as context, while chats reset on
refresh. Python bounds model history by whole turns; the full transcript stays
visible. There are no automatic summaries, server persistence, or browser storage.
Show recoverable catalog errors; never imply a sample reply is a live answer. Model execution and credentials remain in Python.

Keep app-specific UI in `src/components/`, primitives in `components/ui/`, and
app-specific chat composition in `components/`. Extend the existing tokens and
shared components before adding dependencies or another design system.


## Chat composition

Use shadcn Message Scroller directly, with the user message as each turn's
scroll anchor. New questions settle near the top. Follow streamed output only
while the reader stays at the live edge; reading earlier messages stops that
follow. Jump to latest restores it. Scrolling and button visibility are instant.

Message and Bubble compose turns; user text stays literal, while assistant
Markdown streams through Streamdown with the existing serif typography. Keep
code blocks scrollable and links visibly underlined. Input Group composes the
existing textarea and send button, preserving drafts, keyboard behavior and IME
handling. There is no upload or model selection UI.

Show one quiet Trace line per tool execution, using friendly pending, complete,
and failed labels. Preserve the chronological order of model text and activity.
The model is asked to announce catalog discovery before calling the tool; do not
invent narration if it omits that sentence. Thinking is transient and disappears
on the first model text or tool activity, without returning between steps.

Catalog success reads "Library checked · N books found" ("1 book found" for one).
Keep that count in the status line rather than repeating it above the cards.
Stream the model's final introduction after the status. Hold validated catalog
results in a waiting-for-response state until the whole turn settles, then show
them beneath the prose. Text-end alone is not a terminal turn event. Valid
cards also remain available after failure or cancellation of later prose, with
the existing interruption notice; a failed tool produces no cards. Tool-only
success can still reveal cards without inventing an introduction. Keep each
result keyed by toolCallId. Do not display raw tool inputs/outputs or put cards
behind a disclosure, and do not add timers to choreograph the live response.
