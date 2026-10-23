# AI Engineering Diary

## 2026-10-23

- **Streaming presentation:** Tool completion does not finish an assistant turn; controlled SSE tests verified chronological narration, deferred catalog cards, and retained results after later interruptions.

## 2026-10-22

- **Book-card provenance:** Extracted declared covers and original EPUB subjects into a validated catalog contract; metadata-only enrichment preserves retrieval data, and missing subjects stay empty rather than becoming inferred genres.
- **Catalog discovery and retrieval scope:** Separated full-catalog discovery from application-controlled retrieval scope; requests without attachments snapshot all books, while attached requests retain restricted search and empty catalogs skip retrieval.
- **Agent streaming:** Connected Python SSE to the UI through AI SDK transport; explicit completion distinguishes interrupted answers, while displayed conversation history stays separate from stateless agent context.

## 2026-10-21

- **Evaluation gates:** Separated correctness and grounding requirements from retrieval diagnostics using native score-only metrics; unanswerable cases use correctness alone, with labels preserved for reproducible rescoring.
- **Reranking candidates:** Added reranking using Cohere. In the Church test, Cohere promoted explicit name evidence from RRF positions 41 and 51 to first and second; broader improvement remains unmeasured.
- **Judge selection:** User review found GPT-5.4 handled the selected name, timeframe, and abstention cases better; reported full-run cost of about $2.20 motivates selective rescoring.
- **Judge calibration:** Explicit steps were recorded in run 7 and Hanratty passed, but several explanations still penalized verbosity; rubric compliance remains unreliable on the reviewed cases.
- **Evidence annotation:** Drafting narrative evaluation cases exposed why gold answers must preserve plans, timing, and exceptions; Church’s purring passage qualifies its initial apparent absolute.

## 2026-10-20

- **Hybrid search:** Combined BM25 and vector rankings with RRF to mix lexical and semantic matches without comparing incompatible scores.
- **RAG evaluation:** Reviewed retrieval and answer metrics together; inspecting saved cases exposed judge errors and ambiguous references that scores alone missed.
- **Comparable experiments:** Saved answers and retrieval settings separately from scoring, enabling judge comparisons on frozen outputs and separate runs for retrieval changes.
