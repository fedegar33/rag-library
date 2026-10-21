# AI Engineering Diary

## 2026-10-21

- **Judge selection:** User review found GPT-5.4 handled the selected name, timeframe, and abstention cases better; reported full-run cost of about $2.20 motivates selective rescoring.
- **Judge calibration:** Explicit steps were recorded in run 7 and Hanratty passed, but several explanations still penalized verbosity; rubric compliance remains unreliable on the reviewed cases.
- **Evidence annotation:** Drafting narrative evaluation cases exposed why gold answers must preserve plans, timing, and exceptions; Church’s purring passage qualifies its initial apparent absolute.

## 2026-10-20

- **Hybrid search:** Combined BM25 and vector rankings with RRF to mix lexical and semantic matches without comparing incompatible scores.
- **RAG evaluation:** Reviewed retrieval and answer metrics together; inspecting saved cases exposed judge errors and ambiguous references that scores alone missed.
- **Comparable experiments:** Saved answers and retrieval settings separately from scoring, enabling judge comparisons on frozen outputs and separate runs for retrieval changes.
