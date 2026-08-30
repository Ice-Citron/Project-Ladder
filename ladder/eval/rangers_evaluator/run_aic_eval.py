#!/usr/bin/env python3

"""Thin entrypoint for the AIC Gazebo evaluation runner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_SRC = REPO_ROOT / "rangers_evaluator" / "src"
if str(EVALUATOR_SRC) not in sys.path:
    sys.path.insert(0, str(EVALUATOR_SRC))

from errors import EvalRunnerError
from main import main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvalRunnerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
