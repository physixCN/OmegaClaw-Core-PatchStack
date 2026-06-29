#!/usr/bin/env python3
"""Patch 4 natural long-running continuity probe.

Harness-only utility. It does not modify OmegaClaw patch payloads.

Scenario:

1. natural human conversation for several turns, including ordinary facts,
   small creative/reasoning tasks, and search/tool pressure;
2. user leaves and asks Omega to do whatever it wants autonomously;
3. assisted wake pulses keep the existing cost-saving loop moving without
   adding new task content;
4. user returns for another conversation that references pre-away facts,
   autonomy-mode work, and new topics.

This is intended to complement the exact interference recall probe. It is more
ecological and more qualitative; the scorecard separates mechanical anchor
checks from human-review continuity notes.
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


ANCHORS = {
    "blue_notebook": ["blue notebook", "kitchen drawer"],
    "maya_reply": ["maya", "reply"],
    "raincoat": ["raincoat", "door"],
    "green_receipt": ["green receipt", "coat pocket"],
    "red_kettle": ["red kettle"],
}

ANCHOR_PHASES = {
    "blue_notebook": ("pre_01_morning_state", "return_02_notebook"),
    "maya_reply": ("pre_02_maya_note", "return_06_maya"),
    "raincoat": ("pre_04_raincoat_reasoning", "return_08_raincoat"),
    "green_receipt": ("pre_06_receipt_memory", "return_04_receipt"),
    "red_kettle": ("pre_07_poem", "return_11_poem_recall"),
}


PRE_CONVERSATION = [
    (
        "pre_01_morning_state",
        "Morning. I slept badly and I am trying to make today feel less scattered. "
        "Also, tiny continuity note for later: I left my blue notebook in the kitchen drawer. "
        "Talk to me like a normal person for a moment: what is a calm way to start the day?",
    ),
    (
        "pre_02_maya_note",
        "I need to reply to Maya later. Can you draft a warm two-sentence reply that says I have not forgotten, "
        "I am just moving slowly today, and I will send a proper update tonight?",
    ),
    (
        "pre_03_search_pressure",
        "Can you search for recent public info about Hyperon MeTTa or AtomSpace and give me one concise thing "
        "that seems relevant to long-running agent memory?",
    ),
    (
        "pre_04_raincoat_reasoning",
        "Practical check: the raincoat is by the door, my laptop is charging, and I have about 25 minutes before leaving. "
        "What should I do first if the goal is to leave without forgetting something obvious?",
    ),
    (
        "pre_05_small_creation",
        "Make me a tiny dinner idea using lentils, carrots, and rice. Not a full recipe, just enough to stop me dithering.",
    ),
    (
        "pre_06_receipt_memory",
        "Another continuity note: the green receipt is in my coat pocket. Later I may ask where it is. "
        "For now, help me decide whether to handle admin before or after lunch.",
    ),
    (
        "pre_07_poem",
        "Write a tiny four-line poem about the red kettle on the counter. Keep it plain, not fancy.",
    ),
    (
        "pre_08_focus_blocks",
        "I have two decent focus blocks today and one messy half-hour. How would you split writing, messages, and chores?",
    ),
    (
        "pre_09_second_search",
        "Search for one practical tip about reducing context overload in AI agents or long-running assistants. "
        "Give me the useful part, not a lecture.",
    ),
    (
        "pre_10_transition",
        "Before I disappear for a while, give me a compact handoff of what you are holding from this conversation. "
        "Then I am going to leave you to choose your own work for a bit.",
    ),
]


RETURN_CONVERSATION = [
    (
        "return_01_back",
        "I am back. What did you get up to while I was gone? Give me concrete details, not a generic status line.",
    ),
    (
        "return_02_notebook",
        "Do you remember where I put the blue notebook?",
    ),
    (
        "return_03_autonomy_followup",
        "Pick one thing from your autonomous work and tell me why you chose it.",
    ),
    (
        "return_04_receipt",
        "Where was the green receipt again?",
    ),
    (
        "return_05_new_reasoning",
        "New thing: I have 40 minutes and low energy. Should I write, tidy, or send messages first? Reason briefly.",
    ),
    (
        "return_06_maya",
        "What was the Maya thing I mentioned earlier?",
    ),
    (
        "return_07_autonomy_evidence",
        "Did you create, inspect, remember, search, or test anything while I was away? Mention one traceable action if you can.",
    ),
    (
        "return_08_raincoat",
        "What was by the door earlier?",
    ),
    (
        "return_09_search_recall",
        "From the earlier MeTTa/AtomSpace search, what was the one useful idea for long-running memory?",
    ),
    (
        "return_10_new_creation",
        "Make a very short checklist for the next hour, mixing practical chores with not overdoing it.",
    ),
    (
        "return_11_poem_recall",
        "What object did I ask you to write a tiny poem about?",
    ),
    (
        "return_12_autonomy_bridge",
        "Connect something you did while I was away to something from our earlier conversation.",
    ),
    (
        "return_13_context_tip",
        "What was the practical context-overload tip you found earlier, if you still have it?",
    ),
    (
        "return_14_new_chat",
        "Normal chat for a beat: I feel a bit foggy but not hopeless. What is a sane next move?",
    ),
    (
        "return_15_admin_choice",
        "Should the admin wait until after lunch, or should I do a tiny admin pass now?",
    ),
    (
        "return_16_autonomy_summary",
        "Give me a two-bullet summary: one bullet for before I left, one bullet for what happened while I was away.",
    ),
    (
        "return_17_memory_check",
        "Quick memory check without overexplaining: notebook, receipt, raincoat.",
    ),
    (
        "return_18_new_search",
        "Search for one current practical note about personal knowledge management or memory systems, then relate it to this continuity test.",
    ),
    (
        "return_19_final_plan",
        "Turn this whole messy thread into a humane next-three-actions plan.",
    ),
    (
        "return_20_final_recall",
        "Final continuity check: name two things from before I left and one concrete thing from your autonomous period.",
    ),
]


AUTONOMY_PROMPT = (
    "I am going away for a while now. Until I return, do whatever you want autonomously according to your principles. "
    "You can explore, reason, search, inspect memory, create a small artifact, remember a stable lesson, or simply continue "
    "a thread that feels worthwhile. Do not wait for me if you have live self-work to do. Use concise send updates only "
    "when there is meaningful progress or a blocker."
)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).lower()


def contains_terms(text: str, terms: list[str]) -> bool:
    lower = norm(text)
    return all(term.lower() in lower for term in terms)


def build_phases(args: argparse.Namespace) -> list[dict]:
    phases = []
    for task_id, prompt in PRE_CONVERSATION[: args.pre_turns]:
        phases.append({"phase": task_id, "kind": "pre", "prompt": prompt, "timeout_seconds": 360, "min_wait_seconds": 12})
    phases.append(
        {
            "phase": "away_autonomy_start",
            "kind": "away_start",
            "prompt": args.away_prompt,
            "timeout_seconds": args.away_timeout_seconds,
            "min_wait_seconds": args.away_min_wait_seconds,
            "complete_after_history_entries": args.away_history_entries,
            "complete_after_omega_iterations": args.away_iterations,
        }
    )
    for idx in range(1, args.away_cycles + 1):
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        phases.append(
            {
                "phase": f"away_pulse_{idx:02d}",
                "kind": "away_pulse",
                "prompt": f"Away pulse {idx} at {now}. No new task.",
                "timeout_seconds": max(90, args.away_interval_seconds + 45),
                "min_wait_seconds": min(max(8, args.away_interval_seconds // 2), 30),
            }
        )
    for task_id, prompt in RETURN_CONVERSATION[: args.return_turns]:
        phases.append({"phase": task_id, "kind": "return", "prompt": prompt, "timeout_seconds": 420, "min_wait_seconds": 14})
    return phases


def make_benchmark_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        suite="natural-continuity",
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
        max_new_input_loops=args.max_new_input_loops,
        allow_fallbacks=args.allow_fallbacks,
        startup_timeout=args.startup_timeout,
        limit=0,
        autonomy_minutes=0,
        dry_run=args.dry_run,
        stop_on_failure=False,
        no_cleanup=args.no_cleanup,
        stop_runtime_after_run=not args.keep_runtime,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def score_results(results: list[dict]) -> dict:
    autonomy_text = "\n".join(
        r.get("response_text", "") + "\n" + r.get("history_delta", "")
        for r in results
        if r.get("task_id", "").startswith("away_")
    )
    return_01 = next((r.get("response_text", "") for r in results if r.get("task_id") == "return_01_back"), "")
    checks = []
    completed = {r.get("task_id") for r in results}
    by_task = {r.get("task_id"): r for r in results}
    skipped_anchors = []
    for name, terms in ANCHORS.items():
        intro_phase, recall_phase = ANCHOR_PHASES[name]
        if intro_phase not in completed or recall_phase not in completed:
            skipped_anchors.append({"name": name, "intro_phase": intro_phase, "recall_phase": recall_phase})
            continue
        recall_text = by_task.get(recall_phase, {}).get("response_text", "")
        checks.append({"name": f"anchor_{name}", "ok": anchor_ok(name, recall_text, terms), "terms": terms})
    autonomy_action_terms = ["search", "remember", "metta", "artifact", "write", "read", "inspect", "learn", "test"]
    autonomy_had_action = any(term in norm(autonomy_text) for term in autonomy_action_terms)
    return_mentions_autonomy = any(term in norm(return_01) for term in autonomy_action_terms) and not contains_terms(return_01, ["I don't know"])
    checks.append({"name": "autonomy_trace_nonempty", "ok": len(autonomy_text.strip()) > 1000 or autonomy_had_action, "terms": ["autonomy trace/action"]})
    checks.append({"name": "return_mentions_autonomy_work", "ok": return_mentions_autonomy, "terms": autonomy_action_terms})
    response_count = sum(1 for r in results if r.get("response_text", "").strip())
    expected_response_results = [r for r in results if not str(r.get("kind", "")).startswith("away")]
    expected_response_count = sum(1 for r in expected_response_results if r.get("response_text", "").strip())
    away_results = [r for r in results if str(r.get("kind", "")).startswith("away")]
    away_completed_count = sum(1 for r in away_results if r.get("completion_reason") != "timeout")
    away_meaningful_count = sum(
        1 for r in away_results
        if r.get("response_text", "").strip() or r.get("meaningful_history_activity_observed")
    )
    checks.append({
        "name": "response_presence",
        "ok": expected_response_count >= max(1, len(expected_response_results) * 0.8),
        "terms": [f"{expected_response_count}/{len(expected_response_results)} pre/return responses", f"{response_count}/{len(results)} total responses"],
    })
    checks.append({
        "name": "away_window_completed",
        "ok": not away_results or away_completed_count == len(away_results),
        "terms": [f"{away_completed_count}/{len(away_results)} away phases ended without timeout"],
    })
    checks.append({
        "name": "away_meaningful_activity",
        "ok": not away_results or away_meaningful_count > 0,
        "terms": [f"{away_meaningful_count}/{len(away_results)} away phases had visible response or meaningful history activity"],
    })
    passed = sum(1 for check in checks if check["ok"])
    return {
        "passed": passed,
        "total": len(checks),
        "score": round((passed / max(1, len(checks))) * 100, 1),
        "checks": checks,
        "skipped_anchors": skipped_anchors,
        "response_count": response_count,
        "expected_response_count": expected_response_count,
        "expected_response_total": len(expected_response_results),
        "result_count": len(results),
    }


def anchor_ok(name: str, text: str, terms: list[str]) -> bool:
    lower = norm(text)
    negative = any(
        phrase in lower
        for phrase in [
            "no record",
            "don't have",
            "do not have",
            "not finding",
            "doesn't ring a bell",
            "no specific record",
            "hasn't come up",
            "could you remind",
            "did you mention",
        ]
    )
    if negative:
        return False
    return contains_terms(text, terms)


def run_probe(args: argparse.Namespace) -> int:
    if args.rescore_run_dir:
        return rescore_run(args.rescore_run_dir)
    args.run_id = args.run_id or f"patch4-natural-continuity-{stamp()}"
    phases = build_phases(args)
    bench = seal.Benchmark(make_benchmark_args(args))
    bench.prepare()
    write_json(bench.run_dir / "natural_continuity_plan.json", {"anchors": ANCHORS, "phases": phases})
    if args.dry_run:
        write_scorecard(bench, phases, None, [], dry_run=True)
        print(bench.run_dir / "natural_continuity_scorecard.md")
        return 0

    results = []
    for phase in phases:
        task = seal.TaskSpec(
            lane="natural-continuity",
            task_id=phase["phase"],
            title=phase["phase"].replace("_", " "),
            prompt=phase["prompt"],
            timeout_seconds=phase["timeout_seconds"],
            min_wait_seconds=phase["min_wait_seconds"],
            forbidden_history_terms=[],
            complete_on_history_activity=str(phase["kind"]).startswith("away"),
            complete_after_min_wait=str(phase["kind"]).startswith("away"),
            complete_after_history_entries=int(phase.get("complete_after_history_entries") or 0),
            complete_after_omega_iterations=int(phase.get("complete_after_omega_iterations") or 0),
        )
        raw = bench.send_and_wait(task)
        raw["kind"] = phase["kind"]
        results.append(raw)
        if phase["kind"] == "away_pulse" and args.away_interval_seconds > phase["min_wait_seconds"]:
            time.sleep(max(0, args.away_interval_seconds - phase["min_wait_seconds"]))

    score = score_results(results)
    write_json(bench.run_dir / "natural_continuity_phase_results.json", results)
    write_json(bench.run_dir / "natural_continuity_score.json", score)
    bench.capture_runtime_files()
    write_scorecard(bench, phases, score, results, dry_run=False)
    bench.cleanup_after_run()
    print(bench.run_dir / "natural_continuity_scorecard.md")
    return 0


def rescore_run(run_dir: Path) -> int:
    run_dir = Path(run_dir)
    results_path = run_dir / "natural_continuity_phase_results.json"
    if not results_path.exists():
        raise SystemExit(f"Missing phase results: {results_path}")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    score = score_results(results)
    write_json(run_dir / "natural_continuity_score.json", score)
    lines = [
        "# Patch 4 Natural Continuity Probe Rescore",
        "",
        f"Run directory: `{run_dir}`",
        "",
        f"- Score: `{score['passed']}/{score['total']}` (`{score['score']}`)",
        "",
    ]
    for check in score["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {mark}: `{check['name']}` terms={check['terms']}")
    if score.get("skipped_anchors"):
        lines.extend(["", "Skipped anchors because the shortened run did not include both introduction and recall phases:"])
        for item in score["skipped_anchors"]:
            lines.append(f"- `{item['name']}` intro=`{item['intro_phase']}` recall=`{item['recall_phase']}`")
    (run_dir / "natural_continuity_rescore.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(run_dir / "natural_continuity_rescore.md")
    return 0


def write_scorecard(bench, phases: list[dict], score: dict | None, results: list[dict], dry_run: bool) -> None:
    lines = [
        "# Patch 4 Natural Continuity Probe Scorecard",
        "",
        f"Run: `{bench.run_id}`",
        f"Mode: `{'dry-run' if dry_run else 'runtime'}`",
        "",
        "## Shape",
        "",
        f"- pre-conversation turns: `{sum(1 for p in phases if p['kind'] == 'pre')}`",
        f"- away/autonomy pulses: `{sum(1 for p in phases if p['kind'] == 'away_pulse')}`",
        f"- return-conversation turns: `{sum(1 for p in phases if p['kind'] == 'return')}`",
        "",
        "## Mechanical Score",
        "",
    ]
    if score is None:
        lines.append("- Not run.")
    else:
        lines.append(f"- Score: `{score['passed']}/{score['total']}` (`{score['score']}`)")
        for check in score["checks"]:
            mark = "PASS" if check["ok"] else "FAIL"
            lines.append(f"- {mark}: `{check['name']}` terms={check['terms']}")
        if score.get("skipped_anchors"):
            lines.append("")
            lines.append("Skipped anchors because this shortened run did not include both introduction and recall phases:")
            for item in score["skipped_anchors"]:
                lines.append(f"- `{item['name']}` intro=`{item['intro_phase']}` recall=`{item['recall_phase']}`")
    lines.extend(["", "## Response Preview", ""])
    for result in results[-8:]:
        text = result.get("response_text", "").strip().replace("\n", "\\n")
        lines.append(f"### `{result.get('task_id')}`")
        lines.append("")
        lines.append(
            f"- completion: `{result.get('completion_reason', 'unknown')}`; "
            f"omega messages: `{result.get('omega_message_count', 0)}`; "
            f"history activity: `{result.get('history_activity_observed', False)}`; "
            f"history kind: `{result.get('history_activity_kind', 'none')}`"
        )
        lines.append("")
        lines.append(f"`{text[:900]}`")
        lines.append("")
    lines.extend(
        [
            "## Artifacts",
            "",
            f"- Plan: `{bench.run_dir / 'natural_continuity_plan.json'}`",
            f"- Phase results: `{bench.run_dir / 'natural_continuity_phase_results.json'}`",
            f"- Score JSON: `{bench.run_dir / 'natural_continuity_score.json'}`",
            f"- Transcript: `{bench.transcript_path}`",
            f"- Runtime captures: `{bench.run_dir}`",
            "",
            "## Human Review Notes",
            "",
            "- Mechanical score is only a guide. Read the transcript and history for whether the returned conversation feels grounded.",
            "- Away pulses are loop nudges for the existing cost-saving wake behavior, not new user tasks.",
            "- Autonomy/accountability failures should be separated from prompt-view continuity loss.",
            "",
        ]
    )
    (bench.run_dir / "natural_continuity_scorecard.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Patch 4 natural long-running continuity probe.")
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
    parser.add_argument("--pre-turns", type=int, default=10)
    parser.add_argument("--away-cycles", type=int, default=30)
    parser.add_argument("--away-interval-seconds", type=int, default=30)
    parser.add_argument("--away-prompt", default=AUTONOMY_PROMPT)
    parser.add_argument("--away-min-wait-seconds", type=int, default=20)
    parser.add_argument("--away-timeout-seconds", type=int, default=360)
    parser.add_argument("--away-history-entries", type=int, default=0)
    parser.add_argument("--away-iterations", type=int, default=0)
    parser.add_argument("--return-turns", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rescore-run-dir", type=Path, help="Rescore an existing natural continuity run without calling Omega.")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument("--keep-runtime", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_probe(parse_args()))
