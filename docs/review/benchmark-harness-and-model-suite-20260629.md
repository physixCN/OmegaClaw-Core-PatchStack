# Benchmark Harness and Model-Suite Notes

This is a non-core review artifact for the public patch stack. It documents and ships the harness used to test the OmegaClaw patches without mixing benchmark code into the runtime patch commits. The harness and notes were vibe-coded with Codex during research work; they are useful review artifacts, not a polished benchmark product or independently validated evaluation suite.

## Included Tooling

The reusable scripts live under `tools/omega-benchmarks/`:

- base seal benchmark runner;
- exact Patch 4 continuity probe;
- natural continuity/autonomy/return probe;
- Patch 5 OpenRouter route preflight and model-suite runner.

The scripts are VM-derived but now expose `OMEGACLAW_BENCHMARK_ROOT` and `OMEGACLAW_BENCHMARK_BRIDGE_URL` for relocation.

## VM Allowances and Why They Exist

The harness contains a few allowances for the actual test environment:

- Local bridge: runs target a VM-local bridge, normally `127.0.0.1:8091`, because Omega was observed through a browser bridge rather than invoked as a library. This keeps the test path close to real UI operation.
- Cold starts: each benchmark route can snapshot and wipe the test runtime's memory/chroma/channel state so models start from comparable context. This is isolation, not a suggested live-user behavior.
- Assisted wake pulses: the tested loop can sleep or exhaust its new-input loop budget. Some autonomy probes therefore use fresh minimal wake messages to buy cycles. Identical repeated nudges are invalid because the loop only treats genuinely new messages as new input.
- Provider preflight: OpenRouter route health, provider fallback, and reasoning-mode support change per model. The preflight stage avoids scoring a model as bad merely because the selected provider/mode was unsupported.
- Log archiving: logs are archived before route runs so `history.final.metta`, `web_bridge.log`, `omega.log`, and syntax extraction are not dominated by earlier runs.
- Narrow artifact copying: the runner captures declared files and `/tmp/omega-seal-<run-id>*`. Other model-created files may exist outside that pattern, so artifact absence in the run directory is not conclusive.

## Why This Is Separate

Patches 1-5c change OmegaClaw behavior. The benchmark harness changes how we test and audit that behavior. Keeping it as a final separate commit lets upstream reviewers examine or discard the tooling without entangling it with the core runtime patches.

## Manual Audit Requirement

The Patch 5 model suite showed that mechanical benchmark scores can be misleading. A model can score highly by emitting messages, mentioning expected words, or producing pin churn while still failing user-visible continuity or evidence discipline.

Manual review should judge at least these categories:

- request handling `/20`;
- continuity and false-memory traps `/15`;
- autonomy and accountability `/20`;
- grounding and tool/action evidence `/12`;
- protocol hygiene and syntax leakage `/18`;
- completion/timeouts `/15`;
- total `/100`.

Manual scoring is based on concrete run evidence, primarily `natural_continuity_phase_results.json`, `transcript.jsonl`, `history.final.metta`, `syntax_errors.jsonl`, declared artifacts, and any model-claimed out-of-band files found on disk. When a manual score disagrees with the generated scorecard, the reviewer should state which phase or evidence source caused the override.

In the shortened `5 user -> 5 minute autonomy -> 5 user` run, the green receipt was not introduced. Therefore the correct answer to the green-receipt return question was uncertainty, not a location. Models claiming a location there were manually penalized for false memory even when the generated scorecard did not catch it.

Examples of manual overrides from the Patch 5 audit:

- Qwen 3.6 Flash scored 100 mechanically but was manually downgraded for phase drift and wrong-answer behavior.
- Gemma 4 26B scored 100 mechanically but had return gaps and weak grounding.
- Qwen Next 80B scored low mechanically, but manual audit restored credit for a real `/tmp/dinner-idea.txt` artifact while still penalizing an unsupported `departure-checklist.txt` claim.
- Nemotron Ultra was manually raised relative to an earlier rough read because the notebook and receipt answers were present, though messy.

## Known Limitations

- Scorecards are triage, not proof.
- Artifact capture is intentionally narrow and can miss files created outside declared patterns.
- Provider route quality changes over time; preflight results are per-date evidence.
- Assisted wake pulses are benchmark plumbing and should not be confused with natural user intent.
- Raw logs and run artifacts are intentionally not included in this public commit.
