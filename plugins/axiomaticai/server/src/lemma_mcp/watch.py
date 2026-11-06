"""The runs ``send_message`` started, and the monitor that prints one line as each one ends."""

import argparse
import asyncio
import json
import sys
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

from filelock import FileLock

from .auth import Session
from .client import LemmaClient
from .client.runs import RUNNING, wait
from .config import TARGET
from .errors import NotFoundError, NotLoggedInError

WATCH_FILE = "watch.json"
SCAN_SECONDS = 5.0
WAIT_CHUNK_SECONDS = 600.0
RETRY_SECONDS = 60.0


@dataclass(frozen=True)
class WatchedRun:
    conversation_id: str
    run_id: str
    project_dir: str


class WatchList:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self._path = data_dir / WATCH_FILE
        self._lock = FileLock(data_dir / f"{WATCH_FILE}.lock", timeout=10)

    def add(self, run: WatchedRun) -> None:
        with self._lock:
            runs = self._read()
            if run not in runs:
                self._write([*runs, run])

    def remove(self, run: WatchedRun) -> None:
        with self._lock:
            self._write([r for r in self._read() if r != run])

    def for_project(self, project_dir: str) -> list[WatchedRun]:
        with self._lock:
            return [r for r in self._read() if r.project_dir == project_dir]

    def _read(self) -> list[WatchedRun]:
        try:
            return [WatchedRun(**entry) for entry in json.loads(self._path.read_text("utf-8"))]
        except (FileNotFoundError, ValueError, TypeError):
            return []

    def _write(self, runs: list[WatchedRun]) -> None:
        partial = self._path.with_name(self._path.name + ".part")
        partial.write_text(json.dumps([asdict(r) for r in runs]), "utf-8")
        partial.replace(self._path)


def finished_line(run: WatchedRun, outcome: str) -> str:
    return (
        f"Lemma run {run.run_id} in conversation {run.conversation_id} finished: {outcome}. "
        "Read it with get_result."
    )


def stopped_line(run: WatchedRun, reason: Exception) -> str:
    return (
        f"Stopped watching Lemma run {run.run_id} in conversation {run.conversation_id}: {reason}"
    )


class Monitor:
    def __init__(self, data_dir: Path, project_dir: str) -> None:
        self._data_dir = data_dir
        self._project_dir = project_dir
        self._watch = WatchList(data_dir)
        self._client: LemmaClient | None = None
        self._waiting: dict[WatchedRun, asyncio.Task[None]] = {}

    async def run(self) -> None:
        while True:
            self.scan()
            await asyncio.sleep(SCAN_SECONDS)

    def scan(self) -> None:
        for run in self._watch.for_project(self._project_dir):
            if run not in self._waiting:
                self._waiting[run] = asyncio.create_task(self._follow(run))

    async def _follow(self, run: WatchedRun) -> None:
        client = self._lemma()
        try:
            while True:
                try:
                    ended = await wait(client, run.conversation_id, run.run_id, WAIT_CHUNK_SECONDS)
                except (NotFoundError, NotLoggedInError) as e:
                    print(stopped_line(run, e), flush=True)
                    break
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    await asyncio.sleep(RETRY_SECONDS)
                    continue
                if ended.outcome != RUNNING:
                    print(finished_line(run, ended.outcome), flush=True)
                    break
            self._watch.remove(run)
        finally:
            self._waiting.pop(run, None)

    def _lemma(self) -> LemmaClient:
        if self._client is None:
            self._client = LemmaClient(Session(TARGET, self._data_dir, interactive=False))
        return self._client


def main() -> None:
    parser = argparse.ArgumentParser(prog="lemma-watch")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(Monitor(args.data_dir, args.project_dir).run())
    except KeyboardInterrupt:
        sys.exit(0)
