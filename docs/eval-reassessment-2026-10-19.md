# Eval reassessment — 2026-10-19

Reviewed the three runs in `evals/results/deepeval.db` read-only, the latest
`evals/basic_result.json`, current retrieval/generation code, and the local
English Pet Sematary EPUB. No agent or judge calls were made. No datasets or
historical results were changed.

## Scores and comparison limits

| Mean metric | Original (run 1) | Before attachments (run 2) | Latest (run 3) |
| --- | ---: | ---: | ---: |
| Contextual Relevancy | 0.061 | 0.085 | 0.149 |
| Contextual Recall | 0.400 | 0.500 | 0.550 |
| Contextual Precision | 0.123 | 0.408 | 0.542 |
| Faithfulness | 0.980 | 0.781 | 0.830 |
| Answer Correctness | 0.193 | 0.322 | 0.344 |

All runs use gpt-4o-mini as the judge, and all report zero cases passing every
metric. Correctness passes actually decrease from 3/10 in run 2 to 1/10 in run 3,
despite the higher mean. Relevancy passes remain zero. These are directional
observations, not controlled causal comparisons: prompts/questions and corpus
processing have changed, the sample has ten cases, and judge explanations
contain errors.

## What the recent fixes achieved

All ten latest cases call `answer_book_question` once, with only the content
question. All 50 returned passages have book ID 18. Every source text exactly
matches the corresponding chunk from the current local extractor/splitter
(1,085 chunks). The latest run therefore shows no cross-book retrieval or stale
extraction in its returned passages. This does not prove that every stored chunk
matches, but the observed failures now have more specific explanations than an
attachment or corpus-selection bug.

## Case-level findings

| Case | Observation | Main next action |
| --- | --- | --- |
| 01: destination | Ludlow is present at rank 1 and answered correctly as a town. Correctness penalizes missing Maine. | Decide which facts the question requires; avoid treating optional qualifiers as essential. |
| 02: origin | Answer gives Shytown, a nickname, from a later planned return trip. Direct Chicago evidence is available in chapter 1, chunks 5–6; chunk 4 is retrieved but 5–6 are not. | Improve evidence retrieval and test bounded neighboring context. Accept aliases only when the location is established. |
| 03: wife | Agent answers Rachel. Judge penalizes missing Creed and gives recall zero. | Calibrate judge against acceptable short answers; inspect evidence supporting the relationship separately. |
| 04: bull | Hanratty is retrieved and answered, but the question says pet cemetery while the evidence says Micmac burying ground. | Correct the question's location. Correctness passes while faithfulness fails, exposing the reference mismatch. |
| 05: Church's full name | Agent abstains; none of its five passages states the full name. It is available in chunks 4 and 41. | Improve retrieval. Recall's perfect score is a judge error, not successful retrieval. |
| 06: ownership | Agent gives vague family ownership/bond instead of directly identifying Ellie. Nearby opening evidence explicitly links Eileen and Church (chunk 4). | Improve precise evidence retrieval and direct answering. Faithfulness also wrongly claims Ellie does not feed Church; the saved passage explicitly says she does. |
| 07: funeral fight | Core answer father-in-law is present and returned. Output adds unnecessary interpretation and details. Correctness scores only 0.35 largely for verbosity despite the right relationship. | Calibrate correctness and constrain generation to the requested fact. |
| 08: accident | Answer blends running toward Route 15 with an imagined future involving school and camp. The inner RAG answer already makes this error. | Fix narrative interpretation and audit the reference: kite flying occurs in an earlier outing, not the immediate accident scene. |
| 09: burial | Retrieval mixes the pet cemetery, Micmac burial ground, and Gage's ordinary funeral. Answer attributes the ordinary funeral passage to the pet cemetery. | Disambiguate the question and require evidence for both action and location. Restrict the requested entities/time if expecting only Church and Gage. |
| 10: keys | Agent abstains. Direct answer exists in chapter 3, chunk 22, but isn't in the retrieved five. | Improve retrieval. It is not a missing-corpus problem. |

Chunk numbers above describe the current extracted corpus. They are diagnostic
pointers, not permanent references across chunking changes.

## Evaluation reliability

The latest correctness judge penalizes Rachel for missing a surname and the
funeral answer for not matching a very short expected answer. Those reasons do
not follow our intended allowance for paraphrases. Contextual recall awards
Church's full name 1.0 merely because Church appears, while contextual precision
correctly reports no full-name evidence. Faithfulness awards the imagined Gage
biography 1.0. Some ranking explanations also misidentify which node contains
the relevant passage. We should inspect reasons as fallible model outputs.

DeepEval contextual relevancy counts relevant statements divided by all extracted
statements. Five narrative passages can contain the right fact and still score
low because most surrounding sentences concern other things. This is a useful
context-noise signal, but a blanket 0.7 gate needs calibration for this corpus.
Do not optimize solely for that gate or remove context to inflate the score.

## Recommended order of experiments

1. **Repair measurement first.** Audit all ten questions against the EPUB, fix
   location/chronology ambiguities (especially 04, 08, 09), and record short
   supporting passages plus chapter references. Keep these reference passages
   separate from actual runtime `retrieval_context`; never inject gold evidence
   into normal generation. Make correctness use explicit `evaluation_steps`
   accepting equivalent names and harmless wording, while penalizing wrong or
   missing requested facts. Calibrate on manually labeled correct, incorrect,
   partial, and abstaining answers. Compare a stronger judge on frozen outputs
   if inconsistencies remain. Changing golds/rubrics requires a new baseline.
2. **Measure retrieval evidence directly.** Use the annotated supporting passages
   to track answer-bearing evidence in the top 5, 10, and 20 candidates. This
   distinguishes candidate misses from ranking failures without trusting the
   current recall judge alone. Inspect candidate provenance and query text.
3. **Broaden candidates, then rerank.** Experiment with dense candidates plus
   lexical PostgreSQL full-text candidates, fused before reranking to a small
   final context. Keep attachment filters on both branches. More candidates
   alone should not mean sending twenty noisy passages to the answer model.
   Benchmark dense-only candidate expansion and reranking separately so we can
   identify what actually helps this small corpus.
4. **Test bounded context expansion.** The origin question retrieves chunk 4,
   immediately before explicit Chicago evidence in chunks 5–6. Test adjacent
   chunks within the same book/chapter with deduplication and a token budget.
   Also test passage sizes/parent context for unresolved narrative references.
   Larger context can add noise; this is an experiment, not a universal fix.
5. **Improve answer grounding.** Require the requested fact, correct entity and
   location, distinguish imagined/conditional events from actual events, and
   avoid biographies or thematic commentary for short fact questions. Inspect
   inner RAG and outer agent answers separately. For case 08 the failure already
   exists in `ask_question`, so outer-agent prompting alone cannot resolve it.

Make one change at a time. Keep the full-agent end-to-end suite and supplement it
with retrieval diagnostics rather than replacing it. Rescore frozen answers to
calibrate judge/rubric changes; regenerate answers for retrieval/generation
changes. Preserve a fresh baseline after the question/reference audit.

## Sources

- [DeepEval contextual relevancy](https://deepeval.com/docs/metrics-contextual-relevancy)
- [DeepEval G-Eval and explicit evaluation steps](https://deepeval.com/docs/metrics-llm-evals)
- [Anthropic contextual retrieval: dense/lexical candidates and reranking](https://www.anthropic.com/engineering/contextual-retrieval)

These sources support metric interpretation and candidate retrieval experiments;
the case-level diagnoses above come from the local stored outputs and EPUB.
