# Curated starter dataset

`basic.json` contains ten English Pet Sematary questions. Each question runs
against the book attached through its exact EPUB SHA-256 reference. Questions
omit the title because attachment selection happens outside the model.

The dataset was audited against the local English EPUB on 2026-10-19. Every
reference excerpt is an exact substring of the indicated extracted chapter.

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

Reference evidence and answer notes are for dataset review and future retrieval
checks. The current runner passes only the question and attached-book context to
the agent; DeepEval's `retrieval_context` still contains only passages actually
retrieved at runtime. These new reference fields do not currently enter judge
prompts, saved answer rows, or DeepEval metadata. In particular, `answer_notes`
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
evidence metrics and additional reranking are deferred.

## Compare agent answers with hybrid retrieval

The agent and evaluation generation now default to hybrid retrieval: up to 20
candidates from each method, equal-contribution RRF with constant 60, and five
final passages supplied to the answer model. The model chooses only the content
question; attachments and retrieval settings are application-owned.

Save comparison runs to separate answer files:

```bash
uv run python eval.py all --method hybrid --candidate-limit 20 --output evals/results/hybrid/answers.json
uv run python eval.py all --method vector --output evals/results/vector/answers.json
```

`--method bm25` is also supported. `--candidate-limit` applies only to hybrid and
must be at least five. Changing candidate depth is a separate experiment; keep
the dataset, model, judge, and final passage count fixed for retrieval comparisons.
System instructions and scoring rubrics are unchanged; context headers identify
the applicable score type instead of treating RRF scores as cosine similarities.

Each new answer row records `retrieval.method`, `top_k`, effective
`candidate_limit`, and `rrf_constant`. Source records preserve original scores
and branch ranks. DeepEval metadata copies the saved retrieval settings; judge
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
