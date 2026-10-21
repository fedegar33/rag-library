# Expanded Pet Sematary dataset — manual review

Draft prepared from the local English EPUB. This is a review artifact, not the active evaluation dataset.
The ten existing cases are copied from the working starter dataset; IDs 11–30 are proposals.
Every supplied excerpt was mechanically checked against the indicated extracted chapter and EPUB path. That checks transcription, not semantic sufficiency or human approval.

## Review checklist

- Check that the question has one clear interpretation and specifies time/location where needed.
- Verify the proposed answer against the full scene, including speaker attribution, plans, imagined events, and exceptions.
- Check that evidence establishes every required fact, not just matching names. Add passages if the answer needs them.
- Review acceptable aliases and incorrect alternatives in `answer_notes`.
- Mark `review_status` as `verified` only after checking the question, answer, and all evidence together.
- For provisional unanswerable cases 29–30, review the entire edition; an empty evidence list is not evidence of absence.

## Cases to review

| Reviewed | ID | Category | Question | Proposed answer | Evidence chapters |
| --- | --- | --- | --- | --- | --- |
| ☑ | sematary-11 | plans_vs_events | Before Jud takes him into the woods, where does Louis initially plan to bury Church? | In the Pet Sematary. | 22 |
| ☑ | sematary-12 | explanation | Why does Louis initially plan to bury Church without telling Ellie that the cat has died? | To avoid confronting Ellie with the finality of the cat’s death; he hopes she will think Church has wandered off. | 22 |
| ☑ | sematary-13 | plans_vs_events | What explanation does Louis initially plan to suggest to Ellie for Church’s disappearance? | That Church may have wandered off. | 22 |
| ☑ | sematary-14 | location_distinction | Which burial ground lies beyond the Pet Sematary in the woods behind the Creed house? | The Micmac burial ground. | 35 |
| ☑ | sematary-15 | multiple_passages | How does Louis’s initial plan for Church’s burial differ from the place Jud takes him to bury the cat? | Louis initially plans to use the Pet Sematary, but Jud takes him to the Micmac burial ground beyond it. | 22, 22, 35 |
| ☑ | sematary-16 | change_and_exception | After Church returns, what change does Louis notice in the cat’s usual purring, and what exception does he remember? | Church generally no longer purrs, but Louis remembers hearing him purr, or make a similar sound, while curled on his chest on the hide-a-bed. | 30 |
| ☑ | sematary-17 | alias | What longer first name is used for Ellie when she hurts her knee after the family arrives? | Eileen. | 2 |
| ☑ | sematary-18 | relationship | What is Jud Crandall’s wife’s first name? | Norma. | 4 |
| ☑ | sematary-19 | direct_fact | What medical condition makes it difficult for Jud’s wife to get out of the house? | Arthritis. | 3 |
| ☑ | sematary-20 | direct_fact | What does Louis apply to Eileen’s injured leg after the family arrives? | Mercurochrome. | 2 |
| ☑ | sematary-21 | relationship | Which of Louis’s children has a bee sting when he introduces the family to Jud? | Gage. | 3 |
| ☑ | sematary-22 | direct_fact | What illness caused Zelda’s death? | Spinal meningitis. | 8 |
| ☑ | sematary-23 | relationship | How is Zelda related to Rachel? | Zelda is Rachel’s sister. | 8 |
| ☑ | sematary-24 | direct_fact | What is the full name of the dying young man brought into the infirmary on the morning Louis later associates with the nightmare’s beginning? | Victor Pascow. | 12 |
| ☑ | sematary-25 | direct_fact | What kind of factory does Jud say Orinco operates near Orrington? | A chemical fertilizer factory. | 6 |
| ☑ | sematary-26 | approximation | Approximately how long before the Creeds arrive does Jud say the previous owners gave him spare house keys? | About fourteen or fifteen years earlier. | 3 |
| ☑ | sematary-27 | multiple_passages | How was Joan Cleveland connected to Jud’s wife? | Joan Cleveland was Norma’s best friend. | 3, 4 |
| ☐ | sematary-28 | observed_change | What change in Church does Ellie complain about when she picks him up after his return? | He smells bad or unusual. | 28 |
| ☑ | sematary-29 | missing_detail | On what exact calendar date did the previous owners give Jud his spare keys to the house? | The book does not specify an exact calendar date. | None — absence requires review |
| ☑ | sematary-30 | missing_detail | What is the exact registration plate number of the truck that strikes Gage? | The book does not specify the truck’s registration plate number. | None — absence requires review |

## Promotion and comparison

On 2026-10-21, the ten previously audited cases and nineteen user-verified additions were promoted into `evals/basic.json` (29 cases). The `sematary-11` placeholder was replaced with the reviewed question. Case 28 remains here as `needs_review`. Historical outputs were preserved.
Once reviewed, copy only approved cases into a new versioned dataset, or deliberately merge them into the starter set. Preserve existing IDs for unchanged cases; historical scores are not directly comparable after adding or changing questions.
The runner currently ignores `review_status`, `answerable`, and `category`; these are annotations, not execution guards. It also does not supply `answer_notes` or reference evidence to the judge. Do not run this draft just because its JSON parses.
Before scoring unanswerable questions, calibrate refusal handling and decide how recall/precision metrics should treat cases with no positive evidence. Do not report zero evidence recall for a case whose correct behavior is abstention.
Related questions deliberately share scenes and evidence: 09/11–15 (burial plans and locations), 06/17/21 (family), 10/26/27/29 (keys and previous owners), and 22/23 (Zelda). These are paired diagnostics, not independent samples. Keep related families together if splitting development and held-out tests, and inspect results by category.
This expands application evaluation. It is separate from a judge-calibration set, which needs deliberately correct/incorrect answer variants and human labels on frozen outputs.

## What was preserved

- The exact EPUB SHA-256 attachment reference.
- The core fields: `id`, `question`, `expected_answer`, `book_refs`, `reference_evidence`.
- Exact excerpt text plus chapter and archive-relative document path; no unstable numeric chunk IDs.
- Gold evidence stays out of normal retrieval and answer generation.
