![OmegaClaw banner](/docs/assets/banner.png)

# OmegaClaw Core PatchStack

This repository is a public review stack for my OmegaClaw autonomy, accountability, prompt, context, and benchmark work.

It is based on upstream [`asi-alliance/OmegaClaw-Core`](https://github.com/asi-alliance/OmegaClaw-Core). The repository root is a full OmegaClaw-Core checkout, then each patch is applied as a separate Git commit so the work can be inspected, cherry-picked, discussed, or pulled back into core later.

This is not a dump of a live VM. Runtime memory, private logs, Chroma state, local credentials, pycache, and raw benchmark artifacts are intentionally excluded.

This work was vibe-coded with Codex through an iterative research session. It should be treated as experimental, review-oriented patch material, not as a properly audited, production-validated, or security-reviewed release.

## Project Goal

The goal of this stack is to move OmegaClaw toward more reliable autonomous cognition without losing accountability.

The target is not merely an agent that does more. The target is an agent that can:

- keep continuity across cycles;
- distinguish saying from doing;
- use memory, MeTTa, search, files, and tools before making important claims;
- recover from malformed model output without executing the wrong thing;
- keep raw history exact while giving the live loop cleaner context;
- communicate naturally without either spamming or disappearing;
- expose enough traces that humans can audit what happened.

## Relationship To Upstream

This repo keeps the upstream OmegaClaw-Core codebase at the root because the patches are meant to be evaluated against the real project, not as isolated snippets.

The original upstream documentation is still present under [`docs/`](./docs/), and the original project can be found at [`asi-alliance/OmegaClaw-Core`](https://github.com/asi-alliance/OmegaClaw-Core). This README explains my patch-stack version and review intent.



## Patch Stack

Read the commits in order. If you cloned this repo directly, add the ASI upstream remote first:

```bash
git remote add upstream https://github.com/asi-alliance/OmegaClaw-Core.git 2>/dev/null || true
git fetch upstream
git log --oneline --reverse upstream/main..HEAD
```

Current stack:

1. **Patch 1: Final Syntax Membrane**
   Hardens the boundary between model text and Omega actions. It adds typed syntax feedback, safer command parsing, bounded failure behavior for malformed file bodies and MeTTa expressions, and regression tests for known parser/model failure modes.

2. **Patch 2: MeTTa-Owned Capability Surface**
   Moves command/capability guidance into MeTTa-owned descriptors. Python mechanically renders cards and parser hints from descriptor atoms, while the command inventory, roles, traps, and recovery guidance live in `src/harness_descriptors.metta`.

3. **Patch 3: Minimal Skill Result Telemetry**
   Adds compact sibling status atoms such as `(SKILL_RESULT search success)` beside existing raw `LAST_SKILL_USE_RESULTS`. This gives the loop a low-noise signal about whether actions succeeded, failed, timed out, or returned empty without replacing the raw result payload.

4. **Patch 4: Continuity Context Candidate**
   Adds a prompt-facing context view that keeps raw history exact while giving the model a cleaner live summary of recent human messages, sends, pins, recall results, artifacts, and errors.

5. **Patch 2b: Evidence Wait Guidance**
   Extends descriptor guidance so tool-grounded claims should wait for `LAST_SKILL_USE_RESULTS` before depending on search, query, episodes, shell, read-file, or MeTTa results. This is guidance, not a hard parser barrier.

6. **Patch 4b: Bounded Error Recall Context**
   Tightens live `ERROR_RECENT` so large syntax/error cards do not dominate future prompt context. Raw history remains exact; the prompt-facing view receives compact fields, hashes, and omission pointers.

7. **Patch 5a: Lean Omega Prompt Refactor**
   Rewrites `memory/prompt.txt` and `memory/prompt_ASICloud.txt` around identity, purpose, autonomy, grounding, ethics, partnership, and accountability. Command syntax and capability details stay in descriptors rather than being duplicated in the prompt.

8. **Patch 5b: Remove Loop Spamguard Injection**
   Removes the repeated live `DO NOT RE-SEND OR SPAM` / `spamShield` injection from the core loop. The loop still marks fresh human input and neutral no-new-human cycles, but no longer scolds the model into wind-down silence every cycle.

9. **Patch 5c: Provider Chat Role Split**
   Preserves the harness prompt as a `system` message and the live turn as a `user` message for chat providers when the `:-:-:-:` separator is present. Also adds OpenRouter model, provider, fallback, sorting, and reasoning-mode controls used by the test harness.

10. **Benchmark Harness and Model-Suite Notes**
    Adds reusable benchmark scripts and documentation under [`tools/omega-benchmarks/`](./tools/omega-benchmarks/) and [`docs/review/`](./docs/review/). This is testing infrastructure, not core runtime behavior.

## Why These Changes Exist

The patches came from repeated failures observed in live runs and model benchmarks:

- model prose being interpreted as commands;
- multiline artifacts swallowing later actions;
- syntax errors reinserting huge prompt scaffolding into live context;
- capability guidance being duplicated across prompt, Python, and MeTTa;
- models claiming tool/search/file results before the results arrived;
- benchmarks rewarding pin churn, keyword mentions, or message presence instead of accountable work;
- anti-spam wording causing excessive silence and wind-down behavior;
- OpenRouter routes receiving the whole harness as one user message instead of preserving system/user role separation;
- artifact capture producing false negatives when models wrote files outside the benchmark's expected artifact pattern.


## Using This Fork

For normal upstream setup, follow the OmegaClaw/PeTTa installation flow, but clone this repository where the instructions would normally clone `asi-alliance/OmegaClaw-Core`:

```bash
git clone https://github.com/trueagi-io/PeTTa
cd PeTTa
mkdir -p repos
git clone https://github.com/physixCN/OmegaClaw-Core-PatchStack.git repos/OmegaClaw-Core
git clone https://github.com/patham9/petta_lib_chromadb.git repos/petta_lib_chromadb
cp repos/OmegaClaw-Core/run.metta ./
```

This keeps the runtime layout expected by PeTTa while using this patch-stack version of OmegaClaw-Core.

## Review And Test

Useful review commands:

```bash
git remote add upstream https://github.com/asi-alliance/OmegaClaw-Core.git 2>/dev/null || true
git fetch upstream
git log --oneline --reverse upstream/main..HEAD
git show --stat <commit>
git show <commit>
```

Core regression tests:

```bash
python3 -m pytest \
  tests/test_patch1_final_syntax_membrane.py \
  tests/test_patch2_capability_surface.py \
  tests/test_patch3_metta_native_feedback.py \
  tests/test_patch4_continuity_context.py \
  tests/test_patch5a_prompt_refactor.py \
  tests/test_patch5b_loop_spamguard.py \
  tests/test_patch5c_provider_role_split.py -q
```

The local stack was last verified with:

```text
88 passed, 5 subtests passed
```

## Benchmark Tooling

Benchmark tooling lives in [`tools/omega-benchmarks/`](./tools/omega-benchmarks/).

Read [`tools/omega-benchmarks/README.md`](./tools/omega-benchmarks/README.md) before running it. The tools include VM/runtime allowances used during development:

- local bridge defaults;
- cold-start memory/chroma isolation;
- assisted wake pulses for loop-budget/sleep behavior;
- provider/reasoning preflight for OpenRouter;
- log archiving between routes;
- narrow artifact capture rules.

Generated scorecards are triage only. Manual review must inspect phase results, transcripts, raw history, syntax logs, and artifacts. The Patch 5 audit used explicit manual categories:

- request handling `/20`;
- continuity and false-memory traps `/15`;
- autonomy and accountability `/20`;
- grounding and tool/action evidence `/12`;
- protocol hygiene `/18`;
- completion/timeouts `/15`.

When manual scoring disagrees with the generated scorecard, the review should cite the phase result, transcript, history action, syntax log, or artifact path that caused the override.

## What This Repo Does Not Claim

This repo does not claim that the benchmark suite proves AGI, full autonomy, or universal model compatibility.

It provides a cleaner substrate and a more honest test harness. Some models still fail badly. Some routes pass mechanically while failing manual review. That is evidence, not something hidden by the stack.

## Safety And Status

OmegaClaw is experimental autonomous-agent infrastructure. It can run tools, inspect files, write memory, call providers, and communicate through channels depending on configuration. Run it in a constrained environment and review permissions carefully.

This patch stack is research and review work. It is not an upstream release. It was produced through Codex-assisted exploratory development and needs independent human review, cleanup, and validation before any serious deployment or upstream merge.

## License And Credits

This work is based on the MIT-licensed upstream OmegaClaw-Core project from ASI Alliance / SingularityNET contributors. The upstream license remains in [`LICENSE`](./LICENSE).
