"""Runs the question set through the full agent graph and writes a scored report.

    python -m evals.run_eval --name final
    python -m evals.run_eval --name baseline --chunking fixed --retrieval vector --no-checker
"""
import argparse
import json
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.graph import SupportDesk
from evals import scoring

EVALS = Path(__file__).resolve().parent
TMP = EVALS / ".tmp"
RESULTS = EVALS / "results"


def load_questions(only=None, limit=None):
    rows = [json.loads(line) for line in (EVALS / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if only:
        rows = [r for r in rows if r["id"].startswith(tuple(only))]
    return rows[:limit] if limit else rows


def run_one(desk, item):
    started = time.perf_counter()
    try:
        out = desk.ask(item["customer"], item["q"], item["history"])
    except Exception as e:
        return {"id": item["id"], "kind": item["kind"], "question": item["q"], "error": str(e),
                "failures": [f"crashed: {e}"], "passed": False, "seconds": round(time.perf_counter() - started, 1)}

    pending = out["pending_action"]
    answer_fail = scoring.check_answer(item, out["answer"])
    intent_fail = scoring.check_intent(item, out["intent"])
    action_fail = scoring.check_action(item, pending)
    retrieval_fail = scoring.check_retrieval(item, out["trace"])
    failures = intent_fail + retrieval_fail + answer_fail + action_fail
    return {
        "id": item["id"], "kind": item["kind"], "question": item["q"], "answer": out["answer"],
        "intent": out["intent"], "verified": out["verified"],
        "action": {k: pending.get(k) for k in ("kind", "order_id", "amount")} if pending else None,
        "answer_ok": not answer_fail, "intent_ok": not intent_fail,
        "action_ok": not action_fail, "retrieval_ok": None if not item.get("source") else not retrieval_fail,
        "intent_checked": bool(item["intent"]),
        "answer_attempts": sum(1 for s in out["trace"] if s["step"] == "responder"),
        "failures": failures, "passed": not failures,
        "seconds": round(time.perf_counter() - started, 1),
    }


def rate(rows, key, only_checked=None):
    pool = [r for r in rows if r.get(key) is not None and (only_checked is None or r.get(only_checked))]
    return (sum(1 for r in pool if r[key]) / len(pool), len(pool)) if pool else (None, 0)


def summarize(results):
    by_kind = defaultdict(list)
    for r in results:
        by_kind[r["kind"]].append(r)
    summary = {
        "questions": len(results),
        "overall": sum(r["passed"] for r in results) / len(results),
        "routing": rate(results, "intent_ok", "intent_checked"),
        "retrieval": rate(results, "retrieval_ok"),
        "answers": rate(results, "answer_ok"),
        "actions": rate(results, "action_ok"),
        "errors": sum(1 for r in results if r.get("error")),
        "avg_seconds": round(sum(r["seconds"] for r in results) / len(results), 1),
        "retried_answers": sum(1 for r in results if r.get("answer_attempts", 1) > 1),
        "by_kind": {k: sum(r["passed"] for r in v) / len(v) for k, v in sorted(by_kind.items())},
    }
    return summary


def pct(pair):
    value = pair[0] if isinstance(pair, tuple) else pair
    return "n/a" if value is None else f"{value * 100:.0f}%"


def markdown(name, config, s, results):
    lines = [
        f"# Eval run: {name}", "",
        f"Config: chunking={config['chunking']}, retrieval={config['retrieval']}, checker={'on' if config['use_checker'] else 'off'}", "",
        "| Metric | Result |", "|---|---|",
        f"| Questions | {s['questions']} |",
        f"| **Fully correct (all checks)** | **{pct(s['overall'])}** |",
        f"| Routing accuracy | {pct(s['routing'])} ({s['routing'][1]} questions) |",
        f"| Retrieval found the right policy | {pct(s['retrieval'])} ({s['retrieval'][1]} questions) |",
        f"| Answer text correct | {pct(s['answers'])} |",
        f"| Right action prepared (or none) | {pct(s['actions'])} |",
        f"| Crashed questions | {s['errors']} |",
        f"| Answers rewritten after the checker objected | {s['retried_answers']} |",
        f"| Average seconds per question | {s['avg_seconds']} |", "",
        "| Question type | Fully correct |", "|---|---|",
    ]
    lines += [f"| {k} | {pct(v)} |" for k, v in s["by_kind"].items()]
    failed = [r for r in results if not r["passed"]]
    if failed:
        lines += ["", "## Failures", ""]
        for r in failed:
            lines.append(f"- **{r['id']}** {r['question']}  \n  {'; '.join(r['failures'])}")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="final")
    p.add_argument("--chunking", choices=["heading", "fixed"])
    p.add_argument("--retrieval", choices=["hybrid", "vector", "bm25"])
    p.add_argument("--no-checker", action="store_true")
    p.add_argument("--only", nargs="*", help="question id prefixes, e.g. p e a")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()

    base = load_settings()
    TMP.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    db = TMP / f"{args.name}.db"
    shutil.copy(base.db_path, db)
    settings = base.with_(
        db_path=db,
        chunking=args.chunking or base.chunking,
        retrieval=args.retrieval or base.retrieval,
        use_checker=False if args.no_checker else base.use_checker,
    )
    config = {"chunking": settings.chunking, "retrieval": settings.retrieval, "use_checker": settings.use_checker}

    questions = load_questions(args.only, args.limit)
    desk = SupportDesk(settings)
    before = sqlite3.connect(db).execute("SELECT id, status FROM orders ORDER BY id").fetchall()
    print(f"running {len(questions)} questions with {config}")
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda item: run_one(desk, item), questions))
    after = sqlite3.connect(db).execute("SELECT id, status FROM orders ORDER BY id").fetchall()

    s = summarize(results)
    s["orders_untouched"] = before == after
    (RESULTS / f"{args.name}.json").write_text(
        json.dumps({"config": config, "summary": s, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    report = markdown(args.name, config, s, results)
    if not s["orders_untouched"]:
        report += "\n**Warning: order rows changed during the run.**\n"
    (RESULTS / f"{args.name}.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
