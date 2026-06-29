# OmegaClaw Benchmark Harness

This directory contains the reusable benchmark tooling used while evaluating the patch stack. It is intentionally separated from the core OmegaClaw runtime patches. The tooling was vibe-coded with Codex during exploratory research, so treat it as auditable scaffolding rather than a finished benchmark framework.

The harness drives a local OmegaClaw web bridge, sends benchmark prompts, captures transcripts/history/logs, copies declared artifacts, and writes scorecards. It is useful for regression testing, but scorecards are evidence guides rather than final truth.

## Scripts

- `omega_seal_benchmark.py`: base end-to-end runner for syntax, capability, compatibility, autonomy, and capstone lanes.
- `omega_patch4_continuity_probe.py`: exact continuity-under-interference probe.
- `omega_patch4_natural_continuity_probe.py`: natural conversation -> autonomy window -> return quiz probe.
- `omega_patch5_model_suite.py`: OpenRouter route preflight plus short model-suite continuity benchmark.

## Environment

By default the scripts target the VM layout used during development:

```bash
/home/jon/OmegaClaw-patch1-final-test
http://127.0.0.1:8091
```

Override those defaults when running elsewhere:

```bash
export OMEGACLAW_BENCHMARK_ROOT=/path/to/OmegaClaw-test-root
export OMEGACLAW_BENCHMARK_BRIDGE_URL=http://127.0.0.1:8091
```

`omega_patch5_model_suite.py` also needs `OPENROUTER_API_KEY` for route preflight and model runs.

## VM/Runtime Allowances

These scripts include allowances for the development VM and should be read as benchmark plumbing, not OmegaClaw product requirements:

- The benchmark root defaults to `/home/jon/OmegaClaw-patch1-final-test` because the clean test runtime, bridge logs, Chroma folders, and copied ASI checkout lived there. Override it with `OMEGACLAW_BENCHMARK_ROOT` outside that VM.
- The bridge defaults to `http://127.0.0.1:8091` because the browser UI talked to a local `web_bridge.py` process on the VM. Override it with `OMEGACLAW_BENCHMARK_BRIDGE_URL` when needed.
- Cold-start runs snapshot and wipe only the test runtime memory/chroma/channel state under the benchmark root. They are intended to isolate model runs and must not be pointed at a live personal Omega without review.
- Some autonomy runs use assisted wake pulses because the tested loop has cost-saving sleep/loop-budget behavior. Pulses are minimal fresh clock nudges; they are not extra task instructions and should not be scored as user intent.
- Route preflight exists because OpenRouter providers and reasoning modes vary by model/provider. A model failure under the wrong provider or unsupported reasoning effort is not meaningful evidence.
- Log rotation before each route is a harness hygiene allowance to avoid cross-run contamination. It does not change Omega behavior.
- Cleanup copies declared benchmark artifacts first, then removes transient `/tmp/omega-seal-<run-id>*` files and duplicate pre-run backups. Use `--no-cleanup` only for debugging.

## Important Scoring Caveat

The built-in scorecards are deliberately mechanical. They can over-reward models that produce messages, mention keywords, or churn pins while failing continuity, grounding, or protocol discipline. Manual review must inspect:

- `natural_continuity_phase_results.json`
- `transcript.jsonl`
- `history.final.metta`
- `syntax_errors.jsonl`
- copied artifacts under `artifacts/`
- any out-of-band files explicitly claimed by a model

During Patch 5 testing, several routes scored 83-100 mechanically while manual review found phase drift, false memory, protocol leakage, or unsupported artifact claims. Treat automated scores as triage, not acceptance.

Manual rerating should be written beside the run summary or review notes, not silently substituted into the generated scorecard. The manual categories used for the Patch 5 audit were:

- request handling `/20`;
- continuity and false-memory traps `/15`;
- autonomy and accountability `/20`;
- grounding and tool/action evidence `/12`;
- protocol hygiene `/18`;
- completion/timeouts `/15`.

When a manual category score disagrees with the generated scorecard, cite the phase result, transcript line, history action, syntax log, or artifact path that caused the override.

## Artifact Caution

The base runner captures declared `expected_files` and `/tmp/omega-seal-<run-id>*` files. A model may create other files outside those patterns. Absence from the run artifact directory is therefore not proof that the file was never created; manual audits should also inspect command history and likely filesystem paths.

## Wake Pulse Rule

For assisted autonomy runs, wake pulses must be fresh human messages. Repeating the exact same nudge does not count as new input in the loop. Pulses should be minimal clock nudges and must not repeat the autonomy instruction.
