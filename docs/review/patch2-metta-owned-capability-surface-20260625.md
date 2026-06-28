# Patch 2 MeTTa-Owned Capability Surface - 2026-06-25

Base: finished locked Patch 1 syntax membrane `a23fc1cb80c59121202a7e3a4f7a4d1513003419`.

## Scope

Patch 2 exposes OmegaClaw's command surface as a MeTTa-owned capability graph
while preserving the locked Patch 1 syntax membrane.

The patch adds `src/harness_descriptors.metta` as the source of truth for:

- capability names;
- command argument contracts;
- body modes for multiline/file commands;
- symbolic roles, affordances, risks, examples, traps, detailed cards, and
  recovery hints.

`src/skills.metta` keeps the existing `getSkills` context hook, but now renders
the model-facing skill surface from those descriptors via a mechanical Python
projection. This avoids touching `src/loop.metta`.

The rendered surface is budgeted rather than exhaustive. The always-on surface
lists available commands, compact argument shapes, and only the highest-risk
syntax invariants that should prevent known first-attempt failures. Detailed
cards such as `send`, `shell`, `write-file`, `append-file`, `episodes`, and
`metta` remain in MeTTa atoms and are rendered only by exact command/error key.

Benchmark feedback also made three capability hints always visible without
adding new Python policy:

- `pin` is RAM/liveness working memory. Frequent concise cycle pins are expected
  and preserve autonomy; this patch does not suppress or discourage them.
- `shell` is only for operating-system command text. Omega commands should be
  emitted as separate top-level commands, not hidden inside a shell payload.
- File bodies are literal bytes until the closing tag. Later Omega actions must
  be emitted after the tag. This note was added after the GLM5.1/BaseTen
  autonomy run repeatedly leaked Omega commands into generated Perl files before
  self-repairing.
- `send` is Omega's natural human-facing speech channel, not a report-only
  command. Multiple sends are valid when natural; files may supplement speech,
  not silence it.
- `metta` is the route to formal reasoning. NAL is exposed as `(|- ...)`, PLN as
  `(|~ ...)`, and truth values as `(stv frequency confidence)`. The descriptor
  also keeps compact guidance for engine choice, thresholds, and proof trails.

Patch 2 also makes syntax correction descriptor-owned. Parser errors still flow
through the existing `syntax-error` / `LAST_SKILL_USE_RESULTS` path, but the
recovery hint is now selected from `CapabilityErrorRecovery` atoms when
available. For known errors, `CapabilityErrorCard` atoms mechanically select the
relevant command card. This gives the intended lifecycle without changing the
loop: first boot sees what is available, first attempt may fail closed, the
MeTTa feedback contains a specific correction/card, and the next attempt can use
that correction.
The always-on surface also tells Omega to use `pin` for immediate correction and
liveness state, while `remember` is reserved for stable reusable lessons.

Patch 2 also exposes tool-local composition guidance: `write-file` can start an
artifact, `append-file` can add later chunks, and `read-file` can inspect the
resulting file. This is deliberately phrased as available capability, not as an
accountability rule. Requirements such as "do not claim success unless verified"
belong to Patch 3.

The 2026-06-28 Max syntax matrix amendment keeps the new parser mechanics in
Patch 1 and adds only descriptor-owned recovery/guidance here: ambiguous inline
file-body quotes select the `write-file` card, `append-file` explicitly states
that it does not insert newlines, and MeTTa guidance names top-level
bang-prefixed MeTTa as accepted syntax without making it the preferred form.

Patch 2 also removes the duplicated Python command-name/body-mode constants.
The normal source of truth is now `src/harness_descriptors.metta`; Python derives
command names, argument contracts, body modes, roles, affordances, error-card
selection, and rendered context from that file. A small descriptor-shaped
fallback remains only so the membrane fails conservatively if the descriptor
file is absent during import or packaging.

## Boundary

Allowed:

- MeTTa-owned capability declarations.
- Python parsing of descriptor atoms.
- Descriptor-derived compact SKILLS context.
- Parser validation against descriptor command names and argument shapes.
- Neutral syntax-error atoms for malformed or unknown commands.
- Tool-local affordance guidance such as accepted file body forms, parser traps,
  and recovery syntax.
- Budgeted always-on guidance and descriptor-owned syntax-error recovery.
- Exact-key command cards rendered from MeTTa-owned descriptor atoms.
- NAL/PLN capability visibility through the existing `metta` command.
- Shell-vs-Omega command separation guidance.
- File-body-vs-Omega command separation guidance.
- Pin-as-RAM/liveness guidance.

Not allowed:

- `src/loop.metta` changes.
- accountability or readiness logic.
- mandatory evidence/verification rules for final claims.
- Python route choice, goal choice, sufficiency judgment, reply timing, or
  personality shaping.
- Python intent inference for card choice. Cards are selected only by explicit
  command name or error key declared in MeTTa.
- `search` to `web-search` renaming.
- imperative harness-control language such as `CLOSE_NOW`, `send now`, or
  `Do not send`.

## Integration

The existing loop already builds context with:

```metta
" SKILLS: " (getSkills)
```

Patch 2 uses that hook. Invalid commands still flow through the existing
syntax-error path and `LAST_SKILL_USE_RESULTS`, so no new loop report channel is
required.

Patch 2 does not predict user intent or choose expanded guides based on task
semantics. That was rejected as hidden harness cognition. Common syntax traps
are always visible; specific recovery appears only after an actual parser error.

## Verification

Expected checks:

```bash
python3 -m unittest tests/test_patch1_final_syntax_membrane.py tests/test_patch2_capability_surface.py
python3 -m py_compile src/helper.py lib_llm_ext.py
git diff --check
git diff -- src/loop.metta
```
