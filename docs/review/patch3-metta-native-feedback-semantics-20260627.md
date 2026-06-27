# Patch 3: Minimal Skill Result Telemetry

Patch 3 adds a tiny MeTTa-owned status annotation beside the existing command
result transport.

The existing `COMMAND_RETURN` path still owns payloads. Search results, file
contents, shell output, and syntax cards are not duplicated inside telemetry.

Patch 3 adds only fixed-width atoms:

```metta
(SKILL_RESULT command status)
```

Examples:

```metta
(SKILL_RESULT search success)
(SKILL_RESULT query empty)
(SKILL_RESULT shell timeout)
(SKILL_RESULT syntax-error rejected)
(SKILL_RESULT send success)
```

The loop still compiles `LAST_SKILL_USE_RESULTS` in the existing location, but
delegates evaluation to `feedback-eval-results` and rendering to
`feedback-render-lastresults`. Empty no-action cycles preserve the previous
`LAST_SKILL_USE_RESULTS` value instead of erasing useful recent results.

Python is limited to mechanical syntax and payload transport membranes already
needed by the harness: command-head shape extraction from `swrite` text and the
existing `helper.normalize_string` payload normalization. Python does not decide
task intent, recovery policy, readiness, or model-specific behavior.

The command-head helper exists because the runtime must classify an unevaluated
command atom before calling `eval`, and direct PeTTa `case` matching over command
forms did not reduce reliably in the imported harness function during smoke
testing. The helper returns only an inert `(CommandShape head)` atom from syntax;
all result-status meaning stays in `src/harness_feedback.metta`.

This patch intentionally does not implement context compaction, descriptor
decompression, accountability/readiness, autonomy behavior, provider routing,
benchmark plumbing, or payload summarization.
