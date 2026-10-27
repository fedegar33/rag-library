# Curated book evaluation dataset

`basic.json` now contains **29 reviewed English Pet Sematary cases**: 27
answerable questions and two unanswerable questions (29 and 30). On 2026-10-21,
the ten previously audited cases and nineteen user-verified additions were
promoted from the review draft. Case 28 remains in the draft as `needs_review`.
The `sematary-11` placeholder was replaced with the reviewed burial-plan question.
The expanded Ludlow excerpt includes Louis Creed's name; added display quotation
marks were removed so the excerpt remains exact EPUB text.

The runner executes all cases unless filtered with `--id`. It preserves boolean
`answerable` labels for grouped scoring; `category` and `review_status` remain
human annotations. Answerable and unanswerable cases receive separate DeepEval
reports and stored runs with the success rules described below.

## Expanded dataset for manual review

An expanded **review draft**, separate from the active starter file, lives in
[`drafts/pet-sematary-expanded.review.json`](drafts/pet-sematary-expanded.review.json).
It retains all thirty proposed cases, including the one still awaiting review.
Use the [review checklist and question table](drafts/pet-sematary-expanded-review.md)
to verify proposed answers and supporting evidence before promotion.

The draft preserves the existing core fields and adds `category`, `answerable`,
and `review_status` annotations. Existing cases are `previously_audited`;
nineteen additions are `verified`, and case 28 is `needs_review`. The reviewed
unanswerable cases have empty evidence lists. Their absence claims were marked
verified by the user; an empty evidence list alone does not establish absence.

These annotations are not execution guards: the current runner ignores them.
Use `basic.json` for the promoted cases rather than running the full draft.
Questions sharing the same scene should stay together when separating
development and held-out cases; they are related diagnostics, not independent
measurements. Expanding the question set establishes a new dataset baseline.

## Original starter cases

The original starter set contained ten English Pet Sematary questions. Each case runs
against the book attached through its exact EPUB SHA-256 reference. Questions
omit the title because attachment selection happens outside the model.

The original ten cases were audited against the local English EPUB on 2026-10-19.
Supplied excerpts in the active expanded set have also been mechanically checked
as exact substrings of the indicated extracted chapters.

## Case fields

- `id`: stable case label. An ID alone does not identify a dataset revision.
- `question`: a self-contained question asking for a specific fact.
- `expected_answer`: the minimal fact needed to answer it, not a required output
  format. Equivalent phrasing and additional correct detail should be accepted.
- `book_refs`: nonempty list of attached EPUB `content_sha256` values.
- `reference_evidence`: manually verified supporting passages. Each contains a
  `book_ref` from the case's attachments, numbered `chapter`, EPUB
  `document_path`, and exact excerpt `text`. Document paths are relative to the
  EPUB archive, not the workspace. Avoid numeric chunk IDs here: they can change
  when the chunking implementation changes.
- `answer_notes`: optional human-review guidance for aliases or interpretation.
- `answerable`: whether the attached edition supplies the requested information;
  reviewed unanswerable cases have empty `reference_evidence` lists.
- `category`: the behavior exercised by the case, for human review.
- `review_status`: `previously_audited` or `verified` for active cases;
  `needs_review` cases stay in the review draft.

Reference evidence and answer notes are for dataset review and future retrieval
checks. The current runner passes only the question and attached-book context to
the agent; DeepEval's `retrieval_context` still contains only passages actually
retrieved at runtime. These new reference fields do not currently enter judge
prompts. `answerable` is saved with answers and copied into DeepEval metadata to
select the scoring rule. Other reference annotations stay out of saved answer
rows and judge metadata. In particular, `answer_notes`
does not automatically change scoring behavior. Judge calibration remains a
separate task.

## Audit changes

| Case | Adjustment |
| --- | --- |
| 01 | Expected answer is Ludlow; the question asks for a town, not its state. |
| 02 | Chicago retained and supported by the explicit account of the move in chapter 1. |
| 03 | Ask for the wife's first name and expect Rachel. |
| 04 | Identify the bull's location as the Micmac burial ground, distinct from the pet cemetery. |
| 05 | Winston Churchill retained, supported by the explicit explanation of Church's nickname. |
| 06 | Ask which child owns Church and expect Ellie; document Eileen as an acceptable equivalent. |
| 07 | Specify the physical fight at the viewing, rather than the later graveside burial. The requested relationship is father-in-law. |
| 08 | Ask about the moment immediately before the truck strikes Gage. Correct the answer to running into the road, supported by chapter 36's recollection of the actual accident. Kite flying is a separate earlier outing; chapter 40 also contains a counterfactual rescue and imagined future. |
| 09 | Replace the ambiguous list of people buried in the pet cemetery with a question about where Jud takes Louis to bury Church. Expect the Micmac burial ground. |
| 10 | Require the previous owners giving Jud a set of keys; their surname is optional. |

The suite remains a small set of answerable fact questions. It does not yet test
unanswerable questions, multi-book reasoning, long conversation history, or
broad plot analysis.

## Establish a fresh baseline

Questions and references changed, so historical scores are not directly
comparable for the revised cases. The existing results remain historical records.
Regenerate answers and score the revised dataset from the repository root:

```bash
uv run python eval.py
```

The normal command replaces `basic_result.json` with new generated answers and
records a new scored run through DeepEval. Rescoring the old intermediate file
would still evaluate the old questions and answers.

## Compare retrieval manually

Answer generation is sequential; `--max-concurrent` controls DeepEval scoring
only. Cohere trial keys can hit the 10-call/minute rerank limit even with
sequential generation. On a rerank HTTP 429, the application logs a warning,
waits 60 seconds, and retries up to twice. Persistent rate limits and other API
errors still fail the case; reranking is never silently skipped.

The search CLI can compare vector, BM25, and hybrid results without generating answers:

```bash
uv run python -m rag_library.cli.search "What is Church's full name?" --book-id 1 --method vector --limit 10 --verbose
uv run python -m rag_library.cli.search "What is Church's full name?" --book-id 1 --method bm25 --limit 10 --verbose
uv run python -m rag_library.cli.search "What is Church's full name?" --book-id 1 --method hybrid --candidate-limit 20 --limit 10 --verbose
```

Replace `1` with the current ID for the exact EPUB in the case's `book_refs`.
Use the same query, attachments, chapter filters, and limit for both methods.
Inspect whether returned text contains `reference_evidence` at top 5, 10, and 20;
compare source passages and ranking rather than raw scores. Hybrid pools up to
20 candidates per branch by default (at least the final limit), then fuses ranks
using equal-contribution RRF with constant 60. Its verbose output preserves both
branch ranks and scores so consensus and single-branch hits can be inspected.
Candidate depth can affect the fused ranking: record `--candidate-limit` and
keep it fixed when comparing final top-k cutoffs. Single-method `--limit 20`
shows each branch's candidate list for hybrid depth 20. Chunk boundaries can
split an annotated excerpt, so a substring miss alone does not prove evidence
is absent. Keep gold evidence out of search queries and runtime context.

BM25 indexes existing chunks in memory over the attached books together, using
lowercase English tokens, English stopwords, and no stemming. It uses no model
calls; vector and hybrid each make a query embedding request. Automated retrieval
evidence metrics remain deferred. Hybrid additionally calls Cohere's
`rerank-v5.0-pro` by default; use `--no-rerank` for RRF alone.

## Compare agent answers with hybrid retrieval

For a cheaper single-case experiment, select the Church question directly:

```bash
uv run python eval.py all --id sematary-05 --candidate-limit 100 --max-concurrent 1 --output evals/results/church/answers.json
```

Repeat `--id` to select multiple cases. Exact IDs work in `all`, `generate`,
`--manual`, and `score`; score-only selects from saved answers. Unknown IDs fail
before model calls, and repeated IDs run once in dataset order. Generation
replaces its output with the selected cases; use a separate file to retain your
full-run answers. `--max-concurrent 1` reduces parallel judge calls, but provider
rate limits can still apply.

The agent and evaluation generation now default to hybrid retrieval: up to 20
candidates from each method, equal-contribution RRF with constant 60, Cohere
reranking over the full candidate union, and five
final passages supplied to the answer model. The model chooses only the content
question; attachments and retrieval settings are application-owned.

Save comparison runs to separate answer files:

```bash
uv run python eval.py all --method hybrid --candidate-limit 20 --output evals/results/hybrid/answers.json
uv run python eval.py all --method hybrid --candidate-limit 20 --no-rerank --output evals/results/rrf/answers.json
uv run python eval.py all --method vector --output evals/results/vector/answers.json
```

`--method bm25` is also supported. `--candidate-limit` applies only to hybrid and
must be at least five. Changing candidate depth is a separate experiment; keep
the dataset, model, judge, and final passage count fixed for retrieval comparisons.
Retrieval-method comparisons should keep system instructions and the scoring
rubric fixed; context headers identify the applicable score type instead of
treating RRF scores as cosine similarities.

Each new answer row records `retrieval.method`, `top_k`, effective
`candidate_limit`, `rrf_constant`, effective `rerank`, and `rerank_model`.
Source records preserve original scores
and branch ranks, plus rerank scores and prior RRF positions when enabled.
DeepEval metadata copies the saved retrieval settings; judge
retrieval context still contains only passages actually supplied at runtime.
Historical results without retrieval settings remain readable and are not
retroactively labeled.

To rescore hybrid answers without running retrieval or the agent again:

```bash
uv run python eval.py score --output evals/results/hybrid/answers.json
```

Score-only rejects `--method` and `--candidate-limit` because it uses frozen
answers. The default `uv run python eval.py` now generates hybrid answers and
replaces `basic_result.json`; use distinct output files to retain comparisons.

## Answer Correctness rubric — explicit evaluation steps

Scoring defaults to `--metrics core` (Correctness and Faithfulness); `--metrics all`
adds the three retrieval metrics. Answerable cases require both core scores to
reach 0.70. Unanswerable cases require only Correctness; Faithfulness is score-only.
Retrieval metrics always use `threshold=None`, preserving scores/reasons while
leaving case pass/fail unchanged. DeepEval displays `NONE` verdicts and `N/A`
pass rates for these diagnostics. Each nonempty group creates its own report
and stored run, labeled `answerable` or `unanswerable` in case metadata.

Legacy answer files without `answerable` are treated as answerable with a CLI
notice, without consulting the current dataset or guessing from answer wording.
Generate fresh answers to preserve the labels; scoring never edits frozen files.

DeepEval 4.3.0's terminal report and raw stored metric rows support score-only
metrics. Its legacy `metrics_scores` aggregate counts verdict-less rows as
errors; use raw metric rows when comparing stored diagnostic scores, rather than
that legacy aggregate. A `NONE` metric verdict alone is not a judge failure.

On 2026-10-21, Answer Correctness switched from prose `criteria` with generated
steps to explicit `evaluation_steps`. The expected answer defines the minimum
requested facts, not a required response format. Equivalent wording, complete
sentences, citations, and extra information absent from that minimal reference
do not alone justify deductions. Missing requested facts and contradictions do.
An abstention is accepted when the expected answer says information is unavailable;
it omits the requested fact when the reference supplies an answer.

Correctness still receives only the question, actual answer, and expected answer.
It does not verify extra claims using outside knowledge or retrieved passages;
Faithfulness separately evaluates support from the actual retrieval context.
`answer_notes`, `answerable`, and reference evidence are not newly injected into
the judge prompts. The judge model, correctness threshold, and correctness steps
are unchanged by the new success rules. Retrieval scores for unanswerable cases
are diagnostic and need separate interpretation.

To isolate this rubric change, rescore the same saved outputs:

```bash
uv run python eval.py score
```

Use `--output` if the frozen answers are stored elsewhere. This does not regenerate
answers or retrieve again; it reruns the selected metrics and appends one
DeepEval run per nonempty answerability group.
Judge outputs can vary even with unchanged configurations. A score increase after
rescoring is a measurement change, not evidence that retrieval improved. Establish
a new scoring baseline after checking agreement with human-reviewed examples.

## Agent behavior suite

A separate 14-case suite uses fictional books and controlled tool results to
measure tool selection, argument quality, response correctness, and presentation.
It runs the real single-turn agent graph without database or retrieval calls.

```bash
uv run python eval.py generate --suite agent
uv run python eval.py score --suite agent
```

Generation and scoring make model calls; run them deliberately. The tool-name
sequence is an exact pass/fail gate. Semantic metrics remain score-only pending
calibration; Argument Correctness is omitted when no tools were called.
Defaults are isolated under `evals/results/agent-behavior/`. Expectations and tool
outputs are frozen during generation; scoring never reloads the current dataset.
See [the agreed design and commands](../docs/agent-behavior-evals.md). Existing
RAG defaults and verdicts are unchanged.
