# 生命周期：持久维护
# 覆盖的业务场景：status=fixed 事故无回归测试引用必须阻塞，有引用或 open 状态放过，台账缺失不阻塞。
# 依赖的服务/环境：本地 Python、monkeypatch 夹具隔离 INCIDENTS/TESTS 路径；不依赖外部服务。
# 运行方式：uv run pytest tests/test_regression.py
# oracle 输出形状：pytest 断言失败给出 main() 退出码或缺失事故 ID 的期望/实际；pytest 汇总用时。
"""Regression tests for the incident-regression forcing function."""

from __future__ import annotations

from tools import check_regression

_TABLE = (
    "| ID | 根因 | 状态 | 修复 |\n"
    "|---|---|---|---|\n"
    "| INC-001 | 根因A | fixed | 修复A |\n"
    "| INC-002 | 根因B | open | - |\n"
)


def _setup(monkeypatch, tmp_path, incidents_text: str | None, test_files: dict[str, str]):
    incidents = tmp_path / "INCIDENTS.md"
    if incidents_text is not None:
        incidents.write_text(incidents_text, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for name, body in test_files.items():
        (tests_dir / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(check_regression, "INCIDENTS", incidents)
    monkeypatch.setattr(check_regression, "TESTS", tests_dir)


def test_fixed_incident_with_regression_test_passes(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, _TABLE, {"test_x.py": "# regression: INC-001\n"})

    assert check_regression.main() == 0


def test_fixed_incident_without_regression_test_blocks(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, _TABLE, {"test_x.py": "# unrelated\n"})

    assert check_regression.main() == 1


def test_open_incident_does_not_require_test(monkeypatch, tmp_path):
    table = "| INC-002 | 根因B | open | - |\n"
    _setup(monkeypatch, tmp_path, table, {"test_x.py": "# nothing\n"})

    assert check_regression.main() == 0


def test_missing_ledger_does_not_block(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, None, {})

    assert check_regression.main() == 0


def test_test_name_reference_counts(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, _TABLE, {"test_x.py": "def test_inc_001_does_not_recur():\n    pass\n"})

    assert check_regression.main() == 0
