"""从 tests/cases/*.yaml 加载测试用例。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TestCase:
    id: str
    category: str
    task_type: str
    question: str
    expected: dict[str, Any]
    rubric: list[str]

    @property
    def tools_must_include(self) -> list[str]:
        return list(self.expected.get("tools_must_include", []))

    @property
    def jit_categories(self) -> list[str]:
        v = self.expected.get("jit_category", [])
        if isinstance(v, str):
            return [v]
        return list(v or [])

    @property
    def min_tool_calls(self) -> int:
        return int(self.expected.get("min_tool_calls", 0))

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.expected.get("requires_confirmation", False))


CASES_DIR = Path(__file__).resolve().parents[4] / "tests" / "cases"


def load_cases(cases_dir: Path | None = None) -> list[TestCase]:
    d = cases_dir or CASES_DIR
    all_cases: list[TestCase] = []
    for yml in sorted(d.glob("*.yaml")):
        with yml.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cat = raw.get("category", yml.stem)
        task_type = raw.get("task_type", "analysis")
        for item in raw.get("cases") or []:
            all_cases.append(
                TestCase(
                    id=item["id"],
                    category=cat,
                    task_type=task_type,
                    question=item["question"],
                    expected=item.get("expected") or {},
                    rubric=list(item.get("rubric") or []),
                )
            )
    return all_cases


def load_cases_by_category(category: str, cases_dir: Path | None = None) -> list[TestCase]:
    return [c for c in load_cases(cases_dir) if c.category == category]
