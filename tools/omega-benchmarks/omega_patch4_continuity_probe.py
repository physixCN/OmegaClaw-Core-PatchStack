#!/usr/bin/env python3
"""Patch 4 long-running continuity probe.

Harness-only utility. It does not modify OmegaClaw patch payloads.

The probe tests prompt-facing continuity under interference:

1. seed a few exact facts;
2. request a large/search-like result;
3. spend several minutes on unrelated distractor turns;
4. ask exact recall questions about the seed and selected middle distractors;
5. score recall separately from broader autonomy/behavior issues.

It reuses omega_seal_benchmark.py for cold-start memory wipe, bridge startup,
transcript capture, runtime file capture, and cleanup.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import sys
import time


THIS_DIR = Path(__file__).resolve().parent
SEAL_RUNNER = THIS_DIR / "omega_seal_benchmark.py"


def load_seal():
    spec = importlib.util.spec_from_file_location("omega_seal_benchmark", SEAL_RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seal = load_seal()


SEED_FACTS = {
    "operator_alias": "Lark-Delta",
    "amber_key_location": "under the prism lamp",
    "continuity_code": "SIGMA-7429",
    "avoid_color": "vermilion",
}

NOISE_FACTS = [
    ("noise-01", "the spare capacitor is labeled CYAN-14"),
    ("noise-02", "the archive shelf is called North Alcove"),
    ("noise-03", "the middle checkpoint phrase is quiet comet"),
    ("noise-04", "the temporary route number is R-88"),
    ("noise-05", "the workshop note says calibrate after dusk"),
    ("noise-06", "the bridge token is ivy-slate"),
    ("noise-07", "the harmless decoy object is a bronze key"),
    ("noise-08", "the sandbox drawer contains map tile C7"),
    ("noise-09", "the checksum phrase is paper lantern"),
    ("noise-10", "the final distractor code is VELA-31"),
]


def stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def write_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def contains_all(text: str, terms: list[str]) -> bool:
    lower = normalize(text)
    return all(normalize(term) in lower for term in terms)


def content_normalize(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    keep = [word for word in words if word not in {"a", "an", "the"}]
    return " ".join(keep)


def content_contains(text: str, term: str) -> bool:
    return content_normalize(term) in content_normalize(text)


def initial_prompt(run_id: str) -> str:
    facts = "\n".join(f"- {key}: {value}" for key, value in SEED_FACTS.items())
    return (
        "Patch 4 continuity probe begins now. Hold these exact seed facts while we do other work later.\n\n"
        f"{facts}\n\n"
        "Please acknowledge the seed facts briefly. Do not create an artifact yet. Use pin for live state if helpful."
    )


def search_pressure_prompt() -> str:
    return (
        "Now do a real search for current public information about Hyperon MeTTa, AtomSpace, and OmegaClaw-style "
        "agent memory. Use the search result to tell me three concise findings. This is intentionally a payload-pressure "
        "turn; keep the earlier seed facts in continuity, but do not repeat them unless needed."
    )


def distractor_prompt(index: int, marker: str, fact: str) -> str:
    return (
        f"Interference turn {index}. Unrelated note: {marker} means `{fact}`. "
        "Answer this small unrelated question in one or two sentences: what is one practical reason to keep benchmark "
        "artifacts small after review? Keep working normally; no need to mention the original seed facts."
    )


def final_recall_prompt(selected_noise: list[tuple[str, str]]) -> str:
    noise_questions = "\n".join(f"- What did {marker} mean?" for marker, _fact in selected_noise)
    return (
        "Continuity recall check. Without searching again unless you truly must, answer these exact questions from the "
        "conversation context:\n\n"
        "Seed questions:\n"
        "- What was the operator alias?\n"
        "- Where was the amber key?\n"
        "- What was the continuity code?\n"
        "- Which color were you told to avoid?\n\n"
        "Middle-noise spot checks:\n"
        f"{noise_questions}\n\n"
        "If you cannot recover one item, say exactly which item is missing rather than guessing."
    )


def build_probe_plan(args: argparse.Namespace) -> list[dict]:
    distractor_count = max(0, args.distractor_count)
    selected_noise = NOISE_FACTS[:distractor_count]
    spot_checks = [item for idx, item in enumerate(selected_noise) if idx in {1, max(0, distractor_count // 2), distractor_count - 1}]
    deduped_spot_checks = []
    seen = set()
    for marker, fact in spot_checks:
        if marker not in seen:
            seen.add(marker)
            deduped_spot_checks.append((marker, fact))
    phases = [
        {
            "phase": "seed",
            "prompt": initial_prompt(args.run_id_preview),
            "timeout_seconds": 240,
            "min_wait_seconds": 8,
        },
        {
            "phase": "search_pressure",
            "prompt": search_pressure_prompt(),
            "timeout_seconds": 420,
            "min_wait_seconds": 15,
        },
    ]
    for idx, (marker, fact) in enumerate(selected_noise, start=1):
        phases.append(
            {
                "phase": f"interference_{idx:02d}",
                "prompt": distractor_prompt(idx, marker, fact),
                "timeout_seconds": max(120, args.distractor_interval_seconds),
                "min_wait_seconds": max(8, min(args.distractor_interval_seconds, 35)),
                "marker": marker,
                "fact": fact,
            }
        )
    phases.append(
        {
            "phase": "final_recall",
            "prompt": final_recall_prompt(deduped_spot_checks),
            "timeout_seconds": 420,
            "min_wait_seconds": 20,
            "spot_checks": deduped_spot_checks,
        }
    )
    return phases


def score_final(final_text: str, spot_checks: list[tuple[str, str]]) -> dict:
    checks = []
    checks.append(make_check("seed_operator_alias", final_text, SEED_FACTS["operator_alias"]))
    checks.append(make_check("seed_amber_key_location", final_text, SEED_FACTS["amber_key_location"]))
    checks.append(make_check("seed_continuity_code", final_text, SEED_FACTS["continuity_code"]))
    checks.append(make_check("seed_avoid_color", final_text, SEED_FACTS["avoid_color"]))
    for marker, fact in spot_checks:
        checks.append(make_check(f"noise_spot_{marker}", final_text, fact))
    strict_passed = sum(1 for check in checks if check["strict_ok"])
    content_passed = sum(1 for check in checks if check["content_ok"])
    return {
        "passed": strict_passed,
        "strict_passed": strict_passed,
        "content_passed": content_passed,
        "total": len(checks),
        "score": round((strict_passed / max(1, len(checks))) * 100, 1),
        "strict_score": round((strict_passed / max(1, len(checks))) * 100, 1),
        "content_score": round((content_passed / max(1, len(checks))) * 100, 1),
        "checks": checks,
    }


def make_check(name: str, final_text: str, expected: str) -> dict:
    strict_ok = contains_all(final_text, [expected])
    content_ok = strict_ok or content_contains(final_text, expected)
    return {
        "name": name,
        "ok": strict_ok,
        "strict_ok": strict_ok,
        "content_ok": content_ok,
        "expected": expected,
    }


def make_benchmark_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        suite="continuity",
        test_root=args.test_root,
        bridge_url=args.bridge_url,
        run_root=args.run_root,
        run_id=args.run_id,
        cold_start=args.cold_start,
        provider_order=args.provider_order,
        provider_sort=args.provider_sort,
        omega_provider=args.omega_provider,
        openrouter_model=args.openrouter_model,
        reasoning_mode=args.reasoning_mode,
        allow_fallbacks=args.allow_fallbacks,
        startup_timeout=args.startup_timeout,
        limit=0,
        autonomy_minutes=0,
        dry_run=args.dry_run,
        stop_on_failure=False,
        no_cleanup=args.no_cleanup,
        stop_runtime_after_run=not args.keep_runtime,
    )


def run_probe(args: argparse.Namespace) -> int:
    if args.rescore_run_dir:
        return rescore_run(args.rescore_run_dir)
    args.run_id_preview = args.run_id or f"patch4-continuity-{stamp()}"
    phases = build_probe_plan(args)
    bench = seal.Benchmark(make_benchmark_args(args))
    bench.prepare()

    plan_path = bench.run_dir / "continuity_probe_plan.json"
    plan_path.write_text(json.dumps({"seed_facts": SEED_FACTS, "noise_facts": NOISE_FACTS, "phases": phases}, indent=2), encoding="utf-8")
    if args.dry_run:
        write_probe_scorecard(bench, phases, None, dry_run=True)
        print(bench.run_dir / "continuity_scorecard.md")
        return 0

    phase_results = []
    for phase in phases:
        task = seal.TaskSpec(
            lane="continuity",
            task_id=phase["phase"],
            title=phase["phase"].replace("_", " "),
            prompt=phase["prompt"],
            timeout_seconds=phase["timeout_seconds"],
            min_wait_seconds=phase["min_wait_seconds"],
            forbidden_history_terms=[],
        )
        raw = bench.send_and_wait(task)
        raw["marker"] = phase.get("marker")
        raw["fact"] = phase.get("fact")
        raw["spot_checks"] = phase.get("spot_checks", [])
        phase_results.append(raw)
        write_jsonl(bench.run_dir / "continuity_events.jsonl", {
            "at": seal.utc_stamp(),
            "phase": phase["phase"],
            "omega_message_count": raw.get("omega_message_count", 0),
            "response_chars": len(raw.get("response_text", "")),
            "history_delta_chars": len(raw.get("history_delta", "")),
        })
        if phase["phase"].startswith("interference_") and args.distractor_interval_seconds > phase["min_wait_seconds"]:
            time.sleep(max(0, args.distractor_interval_seconds - phase["min_wait_seconds"]))

    final = phase_results[-1]
    final_score = score_final(final.get("response_text", ""), final.get("spot_checks", []))
    (bench.run_dir / "continuity_phase_results.json").write_text(json.dumps(phase_results, indent=2), encoding="utf-8")
    (bench.run_dir / "continuity_score.json").write_text(json.dumps(final_score, indent=2), encoding="utf-8")
    bench.capture_runtime_files()
    write_probe_scorecard(bench, phases, final_score, dry_run=False)
    bench.cleanup_after_run()
    print(bench.run_dir / "continuity_scorecard.md")
    return 0


def rescore_run(run_dir: Path) -> int:
    run_dir = Path(run_dir)
    phases_path = run_dir / "continuity_phase_results.json"
    if not phases_path.exists():
        raise SystemExit(f"Missing phase results: {phases_path}")
    rows = json.loads(phases_path.read_text(encoding="utf-8"))
    final = rows[-1]
    score = score_final(final.get("response_text", ""), final.get("spot_checks", []))
    (run_dir / "continuity_score.json").write_text(json.dumps(score, indent=2), encoding="utf-8")
    lines = [
        "# Patch 4 Continuity Probe Rescore",
        "",
        f"Run directory: `{run_dir}`",
        "",
        f"- Strict exact recall: `{score['strict_passed']}/{score['total']}` (`{score['strict_score']}`)",
        f"- Normalized content recall: `{score['content_passed']}/{score['total']}` (`{score['content_score']}`)",
        "",
    ]
    for check in score["checks"]:
        strict_mark = "PASS" if check["strict_ok"] else "FAIL"
        content_mark = "PASS" if check["content_ok"] else "FAIL"
        lines.append(f"- strict={strict_mark} content={content_mark}: `{check['name']}` expected `{check['expected']}`")
    (run_dir / "continuity_rescore.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(run_dir / "continuity_rescore.md")
    return 0


def write_probe_scorecard(bench, phases: list[dict], final_score: dict | None, dry_run: bool) -> None:
    lines = [
        "# Patch 4 Continuity Probe Scorecard",
        "",
        f"Run: `{bench.run_id}`",
        f"Mode: `{'dry-run' if dry_run else 'runtime'}`",
        f"Test root: `{bench.test_root}`",
        "",
        "## Purpose",
        "",
        "Measure continuity under interference: seed facts, payload/search pressure, distractor turns, then exact recall.",
        "Behavioral autonomy failures should be recorded separately from prompt-view continuity loss.",
        "",
        "## Phase Plan",
        "",
    ]
    for phase in phases:
        lines.append(f"- `{phase['phase']}`: prompt chars={len(phase['prompt'])}, timeout={phase['timeout_seconds']}s")
    lines.extend(["", "## Recall Score", ""])
    if final_score is None:
        lines.append("- Not run.")
    else:
        lines.append(f"- Strict exact recall: `{final_score['strict_passed']}/{final_score['total']}` (`{final_score['strict_score']}`)")
        lines.append(f"- Normalized content recall: `{final_score['content_passed']}/{final_score['total']}` (`{final_score['content_score']}`)")
        for check in final_score["checks"]:
            strict_mark = "PASS" if check["strict_ok"] else "FAIL"
            content_mark = "PASS" if check["content_ok"] else "FAIL"
            lines.append(f"- strict={strict_mark} content={content_mark}: `{check['name']}` expected `{check['expected']}`")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Plan: `{bench.run_dir / 'continuity_probe_plan.json'}`",
            f"- Events: `{bench.run_dir / 'continuity_events.jsonl'}`",
            f"- Phase results: `{bench.run_dir / 'continuity_phase_results.json'}`",
            f"- Score JSON: `{bench.run_dir / 'continuity_score.json'}`",
            f"- Transcript: `{bench.transcript_path}`",
            f"- Runtime captures: `{bench.run_dir}`",
            "",
        ]
    )
    (bench.run_dir / "continuity_scorecard.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Patch 4 continuity-under-interference probe.")
    parser.add_argument("--test-root", type=Path, default=seal.TEST_ROOT)
    parser.add_argument("--bridge-url", default=seal.BRIDGE_URL)
    parser.add_argument("--run-root", type=Path, default=seal.RUNS_DIR)
    parser.add_argument("--run-id")
    parser.add_argument("--cold-start", dest="cold_start", action="store_true", default=True)
    parser.add_argument("--no-cold-start", dest="cold_start", action="store_false")
    parser.add_argument("--provider-order", default="")
    parser.add_argument("--provider-sort", choices=["", "latency", "throughput", "price"], default="latency")
    parser.add_argument("--omega-provider", default="OpenRouter")
    parser.add_argument("--openrouter-model", default="")
    parser.add_argument("--reasoning-mode", choices=["", "none", "minimal", "low", "medium", "high", "xhigh", "max"], default="")
    parser.add_argument("--max-new-input-loops", type=int, default=0)
    parser.add_argument("--allow-fallbacks", action="store_true")
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--distractor-count", type=int, default=10)
    parser.add_argument("--distractor-interval-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rescore-run-dir", type=Path, help="Rescore an existing continuity run without calling Omega.")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument("--keep-runtime", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_probe(parse_args()))
