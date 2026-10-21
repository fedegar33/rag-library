# Answer Correctness judge check

`answer-correctness.json` contains nine examples for checking the evaluator:

- Six saved answers from SQLite run 7, all identified as correct by the user.
  Cases 26, 13, and 07 failed the judge; cases 06, 03, and 04 passed.
- Three deliberately incorrect answers proposed by the assistant: a wrong
  timeframe, a wrong explanation to Ellie, and a wrong bull name. These are
  constructed controls, not actual application outputs or user-approved labels.

The goal is to accept correct answers and reject wrong answers. Merely raising
all scores would not establish better judging.

Saved question, reference answer, and actual answer text are unchanged. In case
07, the saved name is **Irwin Goldman**, not Irving. The user accepts his name
as equivalent to the father-in-law relationship. Review notes document that
equivalence; they are not currently passed to the judge.

Keep the same answers and reference answers when comparing judge configurations.
Assess the requested fact here; evaluate grounding of additional claims
separately with the retrieved passages. This file is not a `basic.json` dataset
and should not be passed to the existing application evaluation command.

No new judge calls were made to create this file. The controls are proposed
examples and can be revised before running the judge comparison.
