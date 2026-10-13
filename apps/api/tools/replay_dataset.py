"""DEV ONLY: replay a saved forecast INPUT (from /debug/dataset) through the engine.

Usage (from repo root):
    python apps/api/tools/replay_dataset.py path/to/dataset.json

Prints the same decision the app would compute for that input, hour by hour.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.models import ForecastDataset


def main(path: str) -> int:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    dataset = ForecastDataset.model_validate(raw)
    result = DecisionEngine().evaluate(dataset)
    print("decision:", result.decision.value, "| reason:", result.decision_reason_code.value)
    print("windows:", len(result.recommended_windows))
    for window in result.recommended_windows:
        print("  -", window.safety.value, window.headline_ar)
    print("hours (time, safety, caution/critical factors):")
    for item in result.hourly:
        codes = sorted(
            {f.code for f in item.factors if f.severity.value in ("caution", "critical")}
        )
        print(f"  {item.time:%H:%M}  {item.safety.value:<8} {', '.join(codes) or '-'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
