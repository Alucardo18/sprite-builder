#!/usr/bin/env python3
"""Run the reproducible Phase 0 UI bridge baseline.

Examples from the repository root::

    ./.venv/bin/python scripts/benchmark_ui_performance.py --reruns 5
    ./.venv/bin/python scripts/benchmark_ui_performance.py --reruns 5 --soak-runs 20 \
        --output reports/performance/phase0-ui-baseline.json

The output is JSON and is intentionally limited to the Python component bridge.
It does not start a browser, call an image API, or mutate the application state.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sprite_builder.ui.performance_baseline import run_baseline  # noqa: E402


def _git_metadata() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    return {
        "revision": git("rev-parse", "HEAD"),
        "worktree_dirty": bool(git("status", "--porcelain")),
    }


def _metadata() -> dict[str, Any]:
    try:
        import streamlit

        streamlit_version = str(streamlit.__version__)
    except Exception:
        streamlit_version = None
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "streamlit": streamlit_version,
        "git": _git_metadata(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reruns",
        type=int,
        default=5,
        help="Number of fresh-image rerun samples per flow (default: 5).",
    )
    parser.add_argument(
        "--soak-runs",
        type=int,
        default=0,
        help="Optional tracemalloc soak iterations per flow (default: 0).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the JSON report to this path (relative to cwd unless absolute).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON output for human inspection.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_baseline(rerun_count=max(0, args.reruns), soak_runs=max(0, args.soak_runs))
    result["environment"] = _metadata()
    encoded = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    )
    if args.output is not None:
        output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
