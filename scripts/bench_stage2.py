#!/usr/bin/env python3
# ruff: noqa: E501
"""Measure Stage 2 processing on large boards: parse, analysis, optimization, export.

Each step runs in its own process so peak memory (max RSS) is per step. Usage::

    .venv/bin/python scripts/bench_stage2.py tests/engineering/real/video_7.0.11.kicad_pcb [more boards...]
    .venv/bin/python scripts/bench_stage2.py --make-stress 47 /tmp/stress.kicad_pcb   # build a stress board

Results are printed as a Markdown table (copied into docs/ENGINEERING.md "Stage 2 performance").
The stress board repeats a real board's tracks and vias in a grid next to the original. It is
for timing only: its geometry isn't a meaningful design.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import resource
import sys
import time
from pathlib import Path


def _step(name: str, path: str, queue: mp.Queue) -> None:  # runs in a child process
    from via_pcb.adapters.kicad import KiCadAdapter

    data = Path(path).read_bytes()
    started = time.perf_counter()
    design = KiCadAdapter().parse(data, filename=Path(path).name)
    parsed = time.perf_counter()
    extra: dict[str, object] = {}
    if name == "analysis":
        from via_pcb.analysis import default_engine

        result = default_engine().run(design, options={})
        extra = {"findings": len(result.findings), "slowest": max(result.checks, key=lambda c: c.duration_ms).check_id}
    elif name == "optimize":
        from via_opt import Constraints, Objective, optimize

        out = optimize(design, [Objective.AREA, Objective.MANUFACTURABILITY, Objective.PLACEMENT], Constraints(), None)
        extra = {"candidates": len(out.candidates)}
    elif name == "export":
        from via_opt import Change, ChangeKind, Target
        from via_opt.export import export_changes

        c, t = design.components[0], design.tracks[-1]
        changes = [
            Change(kind=ChangeKind.MOVE_COMPONENT, target=Target(kind="component", id=c.id or ""), before={},
                   after={"x": c.position.x + 1, "y": c.position.y}, reason="bench"),
            Change(kind=ChangeKind.SET_TRACK_WIDTH, target=Target(kind="track", id=t.id or ""), before={},
                   after={"width": t.width + 0.05}, reason="bench"),
        ]  # fmt: skip
        res = export_changes(data, Path(path).name, changes)
        extra = {"applied": len(res.applied)}
    done = time.perf_counter()
    queue.put({
        "step": name, "parse_s": round(parsed - started, 2), "step_s": round(done - parsed, 2) if name != "parse" else 0.0,
        "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024), "tracks": len(design.tracks), **extra,
    })  # fmt: skip


def run(path: str, steps: list[str]) -> list[dict]:
    rows = []
    ctx = mp.get_context("spawn")
    for step in steps:
        q: mp.Queue = ctx.Queue()
        p = ctx.Process(target=_step, args=(step, path, q))
        p.start()
        p.join()
        rows.append(q.get() if not q.empty() else {"step": step, "error": f"exit {p.exitcode}"})
    return rows


def make_stress(source: Path, target_mb: float, out: Path) -> None:
    text = source.read_text(encoding="utf-8")
    items = re.findall(r"^\t\((?:segment|via)\b.*?^\t\)$", text, flags=re.S | re.M)
    if not items:
        items = re.findall(r"^\s*\((?:segment|via) .*\)$", text, flags=re.M)
    xs = [float(x) for x in re.findall(r"\(start ([-\d.]+) ", text)]
    width = (max(xs) - min(xs)) * 1.1 if xs else 100.0
    chunks, size, k = [], len(text), 1
    block = "\n".join(items)
    while size < target_mb * 1024 * 1024:
        dx = width * k
        shifted = re.sub(
            r"\((start|end|at|mid) ([-\d.]+) ", lambda m, dx=dx: f"({m.group(1)} {float(m.group(2)) + dx:.4f} ", block
        )
        shifted = re.sub(r'\((uuid|tstamp) "?[0-9a-fA-F-]+"?\)', "", shifted)  # copies must not reuse UUIDs
        chunks.append(shifted)
        size += len(shifted)
        k += 1
    end = text.rstrip().rfind(")")
    out.write_text(text[:end] + "\n".join(chunks) + "\n)\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {k - 1} copies)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*")
    ap.add_argument("--steps", default="parse,analysis,optimize,export")
    ap.add_argument("--make-stress", nargs=2, metavar=("MB", "OUT"))
    ap.add_argument("--source", default="tests/engineering/real/video_8.0.8.kicad_pcb")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.make_stress:
        make_stress(Path(args.source), float(args.make_stress[0]), Path(args.make_stress[1]))
        return 0
    print("| Board | Size | Tracks | Step | Parse (s) | Step (s) | Peak RSS (MB) | Notes |")
    print("|---|---|---|---|---|---|---|---|")
    for b in args.boards:
        size = Path(b).stat().st_size / 1e6
        for r in run(b, args.steps.split(",")):
            notes = {k: v for k, v in r.items() if k not in {"step", "parse_s", "step_s", "max_rss_mb", "tracks"}}
            print(f"| {Path(b).name} | {size:.1f} MB | {r.get('tracks', '')} | {r['step']} | {r.get('parse_s', '')} | "
                  f"{r.get('step_s', '')} | {r.get('max_rss_mb', '')} | {json.dumps(notes) if notes else ''} |")  # fmt: skip
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
