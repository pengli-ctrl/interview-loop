import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from interview_loop.evaluation.quality import evaluate_quality


def main() -> None:
    dataset = json.loads(
        (ROOT / "datasets" / "quality_golden.json").read_text(encoding="utf-8")
    )
    report = evaluate_quality(dataset)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
