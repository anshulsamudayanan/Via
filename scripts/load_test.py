#!/usr/bin/env python3
# ruff: noqa: E501
"""Load test against a running VIA stack (Docker Compose): concurrent uploads, analyses and reads.

    .venv/bin/python scripts/load_test.py --base http://localhost:3000 --email you@example.com --designs 8 --readers 8

It signs in (or registers when --register is given), then:

1. creates one project per design and uploads the board to each (duplicates are per project);
2. starts an analysis on every design at the same moment, plus a burst of identical duplicate
   starts that must all return the same run;
3. while the worker processes the queue, ``--readers`` threads read summaries, runs and
   findings in a loop and record latency;
4. waits until every run is terminal and prints throughput, latency percentiles and outcomes.

Exit status is non-zero if any run failed, any request errored (5xx or network) or the duplicate
starts created more than one run. Everything it creates is in projects named "load-test-*".
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json as jsonlib
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HEADERS = {"X-VIA-Request": "1"}


class Resp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code, self.content = status, body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        return jsonlib.loads(self.content)


class HTTPError(Exception):
    pass


class Client:
    """Minimal cookie-keeping HTTP client on the standard library (no extra dependency)."""

    def __init__(self, base: str) -> None:
        if not base.startswith(("http://", "https://")):
            raise SystemExit("--base must be an http(s) URL")
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _send(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None) -> Resp:
        req = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self.base + path, data=body, method=method, headers={**HEADERS, "Accept": "application/json"}
        )
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with self.opener.open(req, timeout=120) as r:
                return Resp(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise HTTPError(str(e)) from e

    def get(self, path: str) -> Resp:
        return self._send("GET", path)

    def post(self, path: str, json: dict | None = None, data: dict | None = None, files: dict | None = None) -> Resp:
        if files is None:
            return self._send("POST", path, jsonlib.dumps(json or {}).encode(), "application/json")
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (data or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, (name, content, ctype) in files.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
                + content
                + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send("POST", path, b"".join(parts), f"multipart/form-data; boundary={boundary}")


def session(base: str, email: str, password: str, register: bool) -> Client:
    c = Client(base)
    if register:
        r = c.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Load test"})
        if r.status_code not in (201, 409):
            raise SystemExit(f"register failed: {r.status_code} {r.text[:200]}")
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"login failed: {r.status_code} {r.text[:200]}")
    return c


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--email", default=os.environ.get("VIA_LOAD_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("VIA_LOAD_PASSWORD", "correct horse battery staple"))
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--board", default="tests/engineering/real/video_8.0.8.kicad_pcb")
    ap.add_argument("--designs", type=int, default=6)
    ap.add_argument("--readers", type=int, default=6)
    ap.add_argument("--duplicates", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    if not args.email:
        raise SystemExit("--email (or VIA_LOAD_EMAIL) is required")
    board = Path(args.board)
    data = board.read_bytes()
    c = session(args.base, args.email, args.password, args.register)
    errors: list[str] = []
    tag = uuid.uuid4().hex[:6]

    # 1. Uploads (concurrent).
    def upload(i: int) -> tuple[str, str]:
        p = c.post("/api/v1/projects", json={"name": f"load-test-{tag}-{i}"}).json()
        t0 = time.perf_counter()
        r = c.post(
            "/api/v1/pcb/import",
            data={"project_id": p["id"]},
            files={"file": (board.name, data, "application/octet-stream")},
        )
        if r.status_code not in (200, 202):
            raise RuntimeError(f"upload {i}: {r.status_code} {r.text[:200]}")
        body = r.json()
        print(f"upload {i}: {r.status_code} in {time.perf_counter() - t0:.2f}s")
        return body["design"]["id"], body["revision"]["id"]

    t_start = time.perf_counter()
    with ThreadPoolExecutor(args.designs) as ex:
        designs = list(ex.map(upload, range(args.designs)))
    for _, rev in designs:  # wait for parsing
        while (st := c.get(f"/api/v1/revisions/{rev}").json()["status"]) not in ("ready", "failed"):
            time.sleep(1)
        if st != "ready":
            errors.append(f"revision {rev} failed to parse")
    t_parsed = time.perf_counter()

    # 2. Concurrent analysis starts + duplicate burst on the first design.
    barrier = threading.Barrier(args.designs + args.duplicates)

    def start(design_id: str) -> str:
        barrier.wait()
        r = c.post(f"/api/v1/designs/{design_id}/analysis-runs", json={})
        if r.status_code not in (200, 202):
            raise RuntimeError(f"start: {r.status_code} {r.text[:200]}")
        return r.json()["id"]

    targets = [d for d, _ in designs] + [designs[0][0]] * args.duplicates
    with ThreadPoolExecutor(len(targets)) as ex:
        run_ids = list(ex.map(start, targets))
    first = run_ids[0]
    dup_ids = {run_ids[0], *run_ids[args.designs :]}
    if len(dup_ids) != 1:
        errors.append(f"duplicate starts created {len(dup_ids)} runs")
    runs = set(run_ids)

    # 3. Readers while the queue drains.
    stop = threading.Event()
    latencies: list[float] = []
    lock = threading.Lock()

    def reader(i: int) -> None:
        design_id = designs[i % len(designs)][0]
        while not stop.is_set():
            for path in (
                f"/api/v1/pcb/{design_id}",
                f"/api/v1/designs/{design_id}/analysis-runs",
                f"/api/v1/analysis-runs/{first}",
            ):
                t0 = time.perf_counter()
                try:
                    r = c.get(path)
                    ok = r.status_code < 500
                except HTTPError as exc:
                    ok, r = False, exc
                dt = time.perf_counter() - t0
                with lock:
                    latencies.append(dt)
                    if not ok:
                        errors.append(f"GET {path}: {r}")

    readers = [threading.Thread(target=reader, args=(i,), daemon=True) for i in range(args.readers)]
    for t in readers:
        t.start()
    status: dict[str, str] = {}
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        status = {rid: c.get(f"/api/v1/analysis-runs/{rid}").json()["status"] for rid in runs}
        if all(s in ("succeeded", "failed") for s in status.values()):
            break
        time.sleep(2)
    stop.set()
    for t in readers:
        t.join(10)
    t_done = time.perf_counter()

    failed = [r for r, s in status.items() if s != "succeeded"]
    if failed:
        errors.append(f"{len(failed)} runs did not succeed: {failed}")
    print()
    print(
        f"board: {board.name} ({len(data) / 1e6:.1f} MB) x {args.designs} designs, {args.readers} readers, {args.duplicates} duplicate starts"
    )
    print(
        f"uploads + parsing: {t_parsed - t_start:.1f}s; analyses: {t_done - t_parsed:.1f}s for {len(runs)} runs ({len(runs) / max(t_done - t_parsed, 1e-9) * 60:.1f}/min)"
    )
    print(
        f"reads during processing: {len(latencies)} requests, p50 {pct(latencies, 50) * 1000:.0f} ms, p95 {pct(latencies, 95) * 1000:.0f} ms, max {max(latencies, default=0) * 1000:.0f} ms, mean {statistics.fmean(latencies) * 1000 if latencies else 0:.0f} ms"
    )
    print(f"run outcomes: {sorted(status.values())}; distinct runs from duplicate burst: {len(dup_ids)}")
    print("errors:" if errors else "errors: none")
    for e in errors[:20]:
        print("  ", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
