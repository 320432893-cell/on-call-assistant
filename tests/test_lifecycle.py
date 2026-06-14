# 生命周期：持久维护
# 覆盖的业务场景：临时件/兼容别名缺机器可读过期标注必须被逮，已过期/旧格式必须报，正常文件不误报。
# 依赖的服务/环境：本地 Python、tmp_path 夹具；不依赖外部服务或 git 状态（scan 直接喂文件）。
# 运行方式：uv run pytest tests/test_lifecycle.py
# oracle 输出形状：pytest 断言失败给出 scan 命中类型的期望/实际；pytest 汇总用时。
"""Regression tests for the lifecycle debt forcing function."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tools import check_lifecycle


def _today():
    return datetime.now(UTC).date()


def _kinds(path) -> set[str]:
    return {kind for kind, _ in check_lifecycle.scan(path)}


def test_temp_file_without_expiry_is_flagged(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("# lifecycle: temp\nx = 1\n", encoding="utf-8")

    assert "MISSING-EXPIRY" in _kinds(probe)


def test_temp_file_with_future_expiry_is_clean(tmp_path):
    future = (_today() + timedelta(days=30)).isoformat()
    probe = tmp_path / "probe.py"
    probe.write_text(f"# lifecycle: temp\n# expires: {future}\nx = 1\n", encoding="utf-8")

    assert _kinds(probe) == set()


def test_expired_date_is_flagged(tmp_path):
    past = (_today() - timedelta(days=1)).isoformat()
    probe = tmp_path / "probe.py"
    probe.write_text(f"# lifecycle: temp\n# expires: {past}\nx = 1\n", encoding="utf-8")

    assert "EXPIRED" in _kinds(probe)


def test_legacy_freetext_is_backlog(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("# 删除条件：迁移完成后删\nx = 1\n", encoding="utf-8")

    assert "BACKLOG" in _kinds(probe)


def test_expires_when_needs_manual_review(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("# lifecycle: temp\n# expires-when: rag 索引迁移完成\nx = 1\n", encoding="utf-8")

    assert "MANUAL" in _kinds(probe)


def test_normal_file_is_clean(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("# 职责：正式能力\nx = 1\n", encoding="utf-8")

    assert _kinds(probe) == set()
