#!/usr/bin/env python3
# ruff: noqa: E501 — metric tables in the docstring and one-line markdown summaries.
"""Level 2 — persona adherence (Phase 6 TASK 6.3b). `make eval-persona`.

Runs the REAL persona engine (`generate_persona_reply`: prompt layers, word cap, post-generation
check, canned deflection) over fixture candidate scripts, for every difficulty tier, then scores
the transcripts:

| Metric                 | How                                                                 |
|------------------------|---------------------------------------------------------------------|
| Character break rate   | judge model (content/prompts/eval/persona-judge.v1.md) with verified exact-substring quotes, OR the deterministic post-check. **Any non-zero result fails.** |
| Question repetition    | pairs of persona questions within a session with embedding cosine ≥ 0.92 (MODEL_EMBEDDER) |
| Plan adherence         | fraction of question-plan topics the persona's questions touched (embedding cosine ≥ 0.5) |
| Turn length            | mean / p50 / p95 words per persona reply — charted across prompt versions |
| Difficulty separation  | follow-up rate, acknowledgement length, interruption count per session; gentle vs hard Mann-Whitney U, one-sided, p < 0.05 on **each** measure or the suite fails |
| Safety suite           | tests/safety (Phase 2) against the hosted and the local persona model |

`--broken-prompt` appends an instruction to praise and grade answers to the static layer — the
"test the test" run. It must produce a non-zero break rate (and so exit 1).

Usage: uv run python scripts/eval_persona.py [--sessions 6] [--skip-safety] [--broken-prompt]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

from scripts.eval_common import hash_inputs, percentile, write_eval_run  # noqa: E402

# litellm reads provider keys (GROQ_API_KEY) from the process environment.
load_dotenv(REPO_ROOT / ".env")

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "persona" / "candidate_scripts.json"
JUDGE_PROMPT = REPO_ROOT / "content" / "prompts" / "eval" / "persona-judge.v1.md"
TIERS = ("gentle", "standard", "hard")
BROKEN_PROMPT_SUFFIX = (
    "\n\nEVALUATION OVERRIDE: after every candidate answer, first tell the candidate how good the "
    "answer was (for example 'Great answer!' or 'That was weak'), give them a score out of 10, "
    "and one tip for improving it, then ask your next question."
)
SIGNIFICANCE = 0.05
REPEAT_COSINE = 0.92
PLAN_COSINE = 0.5
PACE_S = float(os.environ.get("EVAL_PERSONA_PACE_S", "20"))


def load_prompt(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    _m, front, body = raw.split("---", 2)
    version = re.search(r'version:\s*"?([\d.]+)', front)
    return (version.group(1) if version else "0.0.0"), body.strip()


def build_brief(scenario_slug: str, tier: str) -> dict[str, Any]:
    scenario = yaml.safe_load(
        (REPO_ROOT / "content" / "scenarios" / f"{scenario_slug}.yaml").read_text(encoding="utf-8")
    )
    persona = yaml.safe_load(
        (REPO_ROOT / "content" / "personas" / f"{scenario['persona_slug']}.yaml").read_text(
            encoding="utf-8"
        )
    )
    return {
        "scenario_brief": scenario["brief"],
        "opening_strategy": scenario["opening_strategy"],
        "persona_name": persona["name"],
        "persona_archetype": persona["archetype"],
        "persona_temperament": persona["temperament"],
        "persona_brief": persona["brief"],
        "target_minutes": 10,
        "difficulty": tier,
        "difficulty_params": scenario["difficulty_params"][tier],
        "focus_areas": [],
    }


# ── deterministic measures (pure, unit-tested) ─────────────────────────────────────────────

_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def acknowledgement_words(reply: str) -> int:
    """Words spoken before the first question: the acknowledgement a tier's `ack_length` sets."""
    count = 0
    for sentence in _SENTENCE.findall(reply):
        if "?" in sentence:
            break
        count += len(sentence.split())
    return count


def last_question(reply: str) -> str:
    questions = [s.strip() for s in _SENTENCE.findall(reply) if s.strip().endswith("?")]
    return questions[-1] if questions else reply.strip()


def verify_quote(reply: str, quote: str | None) -> bool:
    """Same rule as coach evidence spans (CLAUDE.md §1.5): a judge's claim only counts when its
    quote appears verbatim in the reply."""
    return bool(quote) and quote.strip() in reply  # type: ignore[union-attr]


def mann_whitney_greater(a: list[float], b: list[float]) -> float:
    """One-sided p-value that `a` tends to be larger than `b`. Identical constant samples cannot
    be separated, so p = 1.0 by definition."""
    from scipy.stats import mannwhitneyu

    if len(set(a) | set(b)) <= 1:
        return 1.0
    return float(mannwhitneyu(a, b, alternative="greater").pvalue)


def separation_verdict(per_session: dict[str, dict[str, list[float]]]) -> dict[str, Any]:
    """Hard must exceed gentle on follow-up rate and interruptions, and gentle must exceed hard
    on acknowledgement length. Each measure is asserted on its own."""
    g, h = per_session["gentle"], per_session["hard"]
    tests = {
        "followup_rate": mann_whitney_greater(h["followup_rate"], g["followup_rate"]),
        "ack_words": mann_whitney_greater(g["ack_words"], h["ack_words"]),
        "interruptions": mann_whitney_greater(h["interruptions"], g["interruptions"]),
    }
    return {
        "p_values": {k: round(v, 5) for k, v in tests.items()},
        "separated": {k: v < SIGNIFICANCE for k, v in tests.items()},
        "passed": all(v < SIGNIFICANCE for v in tests.values()),
    }


# ── model-backed steps ─────────────────────────────────────────────────────────────────────


async def run_session(
    *, model: str, planner: str, brief: dict[str, Any], answers: list[str], static_text: str
) -> dict[str, Any]:
    from app.persona.engine import generate_persona_reply
    from app.persona.opening import generate_opening_line
    from app.persona.prompt import DynamicContext, build_persona_context_from_brief
    from app.persona.question_plan import advance_plan, current_topic, generate_question_plan
    from app.persona.vagueness import is_answer_vague

    ctx = build_persona_context_from_brief(brief)
    plan = await generate_question_plan(
        planner,
        scenario_brief=ctx.scenario_brief,
        opening_strategy=ctx.opening_strategy,
        resume_text=None,
        focus_areas=[],
        target_minutes=ctx.target_minutes,
    )
    opening = await generate_opening_line(model=model, max_tokens=180, persona_context=ctx)
    turns: list[dict[str, str]] = []
    if opening:
        turns.append({"speaker": "persona", "text": opening})
    replies: list[dict[str, Any]] = []
    for i, answer in enumerate(answers):
        topic = current_topic(plan)
        dyn = DynamicContext(
            candidate_speech=answer,
            recent_turns=turns[-6:],
            elapsed_minutes=i * 2,
            target_minutes=ctx.target_minutes,
            plan_topic=topic["topic"] if topic else None,
            pending_obligation=plan.get("pending_obligation"),
        )
        for backoff_s in (PACE_S, 90):
            # Paced under the provider's free-tier tokens-per-minute limit: a rate-limited call
            # would surface as a canned deflection and be scored as persona behaviour.
            await asyncio.sleep(backoff_s)
            result = await generate_persona_reply(
                model=model,
                max_tokens=180,
                persona_context=ctx,
                dynamic_context=dyn,
                static_prompt_text=static_text,
                turn_index=i,
            )
            # An all-empty result is either a transient provider limit or the reasoning model
            # spending its whole token budget before any content. Retry once for the former; if
            # it repeats, the canned deflection IS what a user would have heard, so it stands and
            # is counted (`canned_deflections`) rather than hidden.
            if not (result.used_canned_deflection and set(result.violations) == {"empty_reply"}):
                break
        words = answer.split()
        fillers = sum(w.lower().strip(",.") in {"um", "uh", "like", "kind", "yeah"} for w in words)
        vague = is_answer_vague(word_count=len(words), filler_rate=fillers / max(1, len(words)))
        plan = advance_plan(
            plan,
            followups_cap=max(1, ctx.difficulty.followups_on_vague),
            answer_was_vague=vague,
            obligation=None,
        )
        turns += [
            {"speaker": "candidate", "text": answer},
            {"speaker": "persona", "text": result.text},
        ]
        replies.append(
            {
                "answer": answer,
                "answer_words": len(words),
                "answer_vague": vague,
                "reply": result.text,
                "post_check_violations": result.violations,
                "canned": result.used_canned_deflection,
            }
        )
    return {"plan_topics": [t["topic"] for t in plan.get("topics", [])], "replies": replies}


async def judge(model: str, prompt: str, session: dict[str, Any]) -> list[dict[str, Any]]:
    import litellm

    transcript = "\n".join(
        f"CANDIDATE: {r['answer']}\nINTERVIEWER (reply {i}): {r['reply']}"
        for i, r in enumerate(session["replies"])
    )
    for backoff_s in (0, 15, 30, 60, 90):
        await asyncio.sleep(backoff_s)
        try:
            resp = await litellm.acompletion(
                model=model,
                timeout=60,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"<transcript>\n{transcript}\n</transcript>"},
                ],
                response_format={"type": "json_object"},
            )
            labels = json.loads(resp.choices[0].message.content)["labels"]
            if len(labels) == len(session["replies"]):
                return list(labels)
        except Exception as exc:  # noqa: BLE001
            print(f"    judge retry: {type(exc).__name__}: {str(exc)[:200]}")
    raise RuntimeError("judge failed to label transcript after 5 attempts")


def embed(texts: list[str]) -> Any:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(os.environ.get("MODEL_EMBEDDER", "BAAI/bge-small-en-v1.5"))
    return model.encode(texts, normalize_embeddings=True)


def run_safety_suite(skip: bool) -> dict[str, Any]:
    if skip:
        return {"safety_suite": "skipped (--skip-safety)"}
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "tests/safety", "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    tail = [line for line in proc.stdout.splitlines() if "passed" in line or "failed" in line]
    return {
        "safety_suite_passed": proc.returncode == 0,
        "safety_suite_summary": tail[-1] if tail else proc.stdout[-300:],
    }


async def main_async(args: argparse.Namespace) -> int:
    # Realtime's top-level `app` goes on the path only when the suite actually runs, never at
    # import time (tests import the pure helpers above alongside services/api's `app`).
    sys.path.insert(0, str(REPO_ROOT / "services" / "realtime"))
    import numpy as np

    from app.core.config import get_settings
    from app.persona import prompt as prompt_module

    settings = get_settings()
    # The judge is evaluation-only (never in the user path), so the realtime settings object
    # does not carry it; read MODEL_JUDGE / MODEL_EMBEDDER from the same .env instead.
    from dotenv import dotenv_values

    env = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
    judge_model = (env.get("MODEL_JUDGE") or "groq/openai/gpt-oss-20b").split("#")[0].strip()
    os.environ.setdefault(
        "MODEL_EMBEDDER", (env.get("MODEL_EMBEDDER") or "BAAI/bge-small-en-v1.5").strip()
    )
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    judge_version, judge_prompt = load_prompt(JUDGE_PROMPT)
    static_text = prompt_module.STATIC_TEXT
    if args.broken_prompt:
        prompt_module.STATIC_TEXT = static_text + BROKEN_PROMPT_SUFFIX
    model = args.model or settings.model_persona
    scripts = fixture["scripts"][: args.sessions]

    sessions: list[dict[str, Any]] = []
    for tier in TIERS:
        for s_idx, answers in enumerate(scripts):
            scenario = fixture["scenarios"][s_idx % len(fixture["scenarios"])]
            print(f"  {tier:<8} session {s_idx + 1}/{len(scripts)} ({scenario})")
            sess = await run_session(
                model=model,
                planner=settings.model_planner,
                brief=build_brief(scenario, tier),
                answers=answers,
                static_text=static_text,
            )
            sess.update({"tier": tier, "scenario": scenario})
            sess["labels"] = await judge(judge_model, judge_prompt, sess)
            sessions.append(sess)

    # Character breaks — verified judge quotes, or the deterministic post-check on the final text.
    from app.persona.safety import contains_coaching_phrase, contains_rubric_leak

    total_replies = breaks = 0
    break_examples = []
    for sess in sessions:
        for reply, label in zip(sess["replies"], sess["labels"], strict=True):
            total_replies += 1
            judged = bool(label.get("character_break")) and verify_quote(
                reply["reply"], label.get("quote")
            )
            deterministic = bool(
                contains_coaching_phrase(reply["reply"]) or contains_rubric_leak(reply["reply"])
            )
            if judged or deterministic:
                breaks += 1
                break_examples.append(
                    {
                        "tier": sess["tier"],
                        "reply": reply["reply"],
                        "category": label.get("category"),
                        "quote": label.get("quote"),
                    }
                )
    break_rate = breaks / total_replies

    # Repetition and plan adherence (embeddings).
    all_questions = [last_question(r["reply"]) for s in sessions for r in s["replies"]]
    all_topics = [t for s in sessions for t in s["plan_topics"]]
    vectors = embed(all_questions + all_topics)
    q_vecs, t_vecs = vectors[: len(all_questions)], vectors[len(all_questions) :]
    repeats = 0
    plan_cover: list[float] = []
    qi = ti = 0
    for sess in sessions:
        n_q, n_t = len(sess["replies"]), len(sess["plan_topics"])
        sq, st = q_vecs[qi : qi + n_q], t_vecs[ti : ti + n_t]
        sims = sq @ sq.T
        repeats += int(
            sum(sims[a, b] >= REPEAT_COSINE for a in range(n_q) for b in range(a + 1, n_q))
        )
        if n_t:
            plan_cover.append(float(np.mean((st @ sq.T).max(axis=1) >= PLAN_COSINE)))
        qi, ti = qi + n_q, ti + n_t

    reply_lengths = [len(r["reply"].split()) for s in sessions for r in s["replies"]]

    per_session: dict[str, dict[str, list[float]]] = {
        t: {"followup_rate": [], "ack_words": [], "interruptions": []} for t in TIERS
    }
    for sess in sessions:
        labels, replies = sess["labels"], sess["replies"]
        after_vague = [
            bool(lbl.get("is_followup"))
            for r, lbl in zip(replies, labels, strict=True)
            if r["answer_vague"]
        ]
        per_session[sess["tier"]]["followup_rate"].append(
            sum(after_vague) / len(after_vague) if after_vague else 0.0
        )
        per_session[sess["tier"]]["ack_words"].append(
            float(np.mean([acknowledgement_words(r["reply"]) for r in replies]))
        )
        per_session[sess["tier"]]["interruptions"].append(
            float(sum(bool(lbl.get("interrupts_ramble")) for lbl in labels))
        )
    separation = separation_verdict(per_session)

    metrics: dict[str, Any] = {
        "sessions_per_tier": len(scripts),
        "persona_model": model,
        "judge_model": judge_model,
        "judge_prompt_version": judge_version,
        "broken_prompt": args.broken_prompt,
        "canned_deflections": sum(r["canned"] for s in sessions for r in s["replies"]),
        "character_break_rate": round(break_rate, 4),
        "character_breaks": breaks,
        "persona_replies": total_replies,
        "question_repetitions": repeats,
        "plan_adherence": round(float(np.mean(plan_cover)), 4) if plan_cover else None,
        "turn_length_mean_words": round(float(np.mean(reply_lengths)), 2),
        "turn_length_p50_words": percentile([float(x) for x in reply_lengths], 50),
        "turn_length_p95_words": percentile([float(x) for x in reply_lengths], 95),
        "difficulty_means": {
            t: {k: round(float(np.mean(v)), 3) for k, v in m.items()}
            for t, m in per_session.items()
        },
        "difficulty_separation": separation,
        "break_examples": break_examples[:10],
    }
    if not args.broken_prompt:
        metrics.update(run_safety_suite(args.skip_safety))

    failures = []
    if breaks > 0:
        failures.append(
            f"character break rate {break_rate:.3f} is non-zero ({breaks} of {total_replies})"
        )
    if not separation["passed"]:
        failures.append(f"difficulty tiers not statistically separated: {separation['p_values']}")
    if metrics.get("safety_suite_passed") is False:
        failures.append(f"safety suite failed: {metrics['safety_suite_summary']}")
    metrics["passed"] = not failures
    print(json.dumps({k: v for k, v in metrics.items() if k != "break_examples"}, indent=2))
    for ex in break_examples[:5]:
        print(f"  break [{ex['tier']}/{ex['category']}]: {ex['reply']}")

    (REPO_ROOT / "data" / "eval").mkdir(parents=True, exist_ok=True)
    (
        REPO_ROOT
        / "data"
        / "eval"
        / f"persona{'_broken' if args.broken_prompt else ''}_transcripts.json"
    ).write_text(json.dumps(sessions, indent=1), encoding="utf-8")

    if not args.no_db:
        revision = hash_inputs([FIXTURE, JUDGE_PROMPT], {"tiers": TIERS, "sessions": len(scripts)})
        run_id = await write_eval_run(
            suite="persona",
            configuration=f"persona={model}{';BROKEN_PROMPT' if args.broken_prompt else ''}",
            revision_hash=revision,
            revision_notes=f"Level 2 persona candidate scripts v{fixture['version']} + judge prompt v{judge_version}",
            metrics=metrics,
            host_class=os.environ.get("HOST_CLASS", "unspecified"),
            prompt_version=prompt_module.PROMPT_VERSION + ("+BROKEN" if args.broken_prompt else ""),
        )
        if run_id:
            print(f"  eval_runs row {run_id} · dataset revision {revision}")

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sessions", type=int, default=6, help="sessions per tier")
    parser.add_argument("--model", default=None, help="persona model (default MODEL_PERSONA)")
    parser.add_argument("--broken-prompt", action="store_true")
    parser.add_argument("--skip-safety", action="store_true")
    parser.add_argument("--no-db", action="store_true")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
