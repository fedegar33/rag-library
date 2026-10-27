# Agent behavior evaluation suite

## Agreed scope

This suite isolates agent decisions from retrieval quality. It runs the configured
model through the real single-turn agent graph, registered tool names and schemas,
runtime attachment context, and existing limits (three model calls, two tool
calls). Tool middleware returns controlled fictional catalog entries and passages;
it never invokes PostgreSQL, embeddings, or Cohere. The prompt remains unchanged:
new expectations may expose current failures rather than silently changing behavior.

The existing RAG suite continues to use real EPUBs and its current success rules.
Conversation history, sliding-window behavior, recommendations, and automatic
summaries remain outside this first behavior suite.

## Dataset

`evals/agent_behavior.json` defines versioned fixtures, shared presentation
instructions, and 14 independent cases:

| Category | Cases | Expected behavior |
| --- | --- | --- |
| Catalog | 4 | Full catalog, attachments ignored for discovery, empty library, missing author |
| Content | 4 | Explicit fact, equivalent wording, missing evidence, empty library |
| Social | 2 | Brief greeting or thanks, without tools |
| Out of scope | 2 | Gentle redirection toward the library, without tools |
| Clarification | 2 | Ask for an ambiguous referent, without tools |

An unanswerable content question must still call `answer_book_question` and then
abstain based on its empty result. A missing tool and an unnecessary tool are both
failures. Catalog answers introduce cards briefly without repeating the book list. These are expected behaviors, not measured results.

## Metrics

| Metric | Role |
| --- | --- |
| Tool Correctness | Exact ordered tool names, threshold 1.0; determines pass/fail |
| Argument Correctness | Semantic diagnostic, native `threshold=None`; only when tools were called |
| Agent Response Correctness (GEval) | Diagnostic of factual agreement and support in actual tool outputs |
| Prompt Alignment | Diagnostic of catalog presentation and response instructions |

The three semantic metrics have no pass/fail threshold until reviewed against
human judgments. No tool calls means Argument Correctness is **not applicable**;
no artificial perfect score is inserted. Cases with and without calls are scored
in separate native DeepEval runs. Generation or judge errors fail the command.

## Run deliberately

Generation calls the configured response model. Scoring calls the configured
judge (`EVAL_JUDGE_MODEL`, falling back to `OPENAI_CHAT_MODEL`). Both can cost money.
The usual environment settings are loaded, but no running database is needed.

```bash
uv run python eval.py generate --suite agent
uv run python eval.py score --suite agent
```

Inspect generated answers before scoring. Both stages default to
`evals/results/agent-behavior/answers.json`; generation replaces this file.
Scoring reports go to `evals/results/agent-behavior/scores`. Use `--output` and
`--results-folder` to retain experiments. To run both stages explicitly:

```bash
uv run python eval.py all --suite agent
```

Select exact case IDs with repeated `--id`; dataset order is preserved and
repeated IDs run once. Unknown IDs fail before agent calls or output replacement.
`--manual` aliases generation. For example:

```bash
uv run python eval.py generate --suite agent --id catalog-02 --id social-01
uv run python eval.py score --suite agent --id catalog-02 --max-concurrent 2
```

Retrieval flags and `--metrics` are rejected for this suite because its fixtures
and metric set are fixed. Omitting `--suite` preserves the existing RAG defaults.

## Reproducibility and limits

Generation freezes the case expectations, fixture data, shared instructions,
actual tool arguments and outputs, assistant text, model name, prompt, registered
schemas, and dataset hash. Score-only reads that file; it does not consult the
current dataset or run the response agent again. A new generation still depends
on the current model and application code; frozen outputs do not pin a provider's
model implementation.

Offline tests exercise the graph using scripted model responses and assert that
production catalog/retrieval functions are never called. They verify wiring and
failure handling, not real-model quality. No paid baseline was run during this
implementation. Review real outputs and diagnostic scores before choosing any
semantic thresholds or claiming improvement.
