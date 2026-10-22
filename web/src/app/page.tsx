import { BookOpenIcon } from "lucide-react";

import { ConversationEmptyState } from "@/components/ai-elements/conversation";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col px-6 py-10 sm:py-16">
      <header className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">RAG Library</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          A place to explore your books.
        </h1>
        <p className="max-w-lg text-base leading-relaxed text-pretty text-muted-foreground">
          Ask questions, follow ideas, and find your way back to the source.
        </p>
      </header>
      <section aria-label="Conversation" className="my-10 rounded-2xl border bg-card py-16 sm:py-24">
        <ConversationEmptyState
          icon={<BookOpenIcon aria-hidden="true" className="size-8" />}
          title="Your library conversations start here"
          description="Chat and book selection are coming next."
        />
      </section>
      <footer className="text-sm text-muted-foreground">
        Web starter · Not connected to the library yet
      </footer>
    </main>
  );
}
