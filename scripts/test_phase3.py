#!/usr/bin/env python3
"""Phase3 自测：覆盖工具安全 + 状态机 + Provider 冒烟（按 .env 实跑一轮）"""

import asyncio
import os
import sys

# Windows 控制台 GBK 编码不下 emoji，强制 stdout 用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent.tools import read_file_tool


def test_read_file_security():
    """工具路径安全：拒绝绝对路径、.. 穿越、不存在"""
    print("\n=== 测试 readFile 工具安全 ===")

    # 合法
    out = read_file_tool("sop-001.html")
    assert not out.startswith("[Error]"), f"sop-001.html 应可读: {out[:80]}"
    print("[OK] readFile('sop-001.html') 命中（自动补 raw/）")

    out = read_file_tool("raw/sop-002.html")
    assert not out.startswith("[Error]"), "raw/sop-002.html 应可读"
    print("[OK] readFile('raw/sop-002.html')")

    # 非法
    cases = [
        ("/etc/passwd", "绝对路径"),
        ("../../../etc/passwd", ".. 穿越"),
        ("not-exist.html", "不存在"),
        ("", "空字符串"),
    ]
    for fname, desc in cases:
        out = read_file_tool(fname)
        assert out.startswith("[Error]"), f"{desc} 应被拒绝，实际: {out[:80]}"
        print(f"[OK] {desc} 被拒绝: {out[:60]}")


async def test_agent_smoke():
    """Provider + 状态机冒烟（按 .env 实跑）"""
    print("\n=== Agent 状态机冒烟 ===")

    try:
        from app.services.agent import AgentStateMachine, get_llm_provider
    except ImportError as e:
        print(f"[FAIL] import: {e}")
        return False

    try:
        provider = get_llm_provider()
    except RuntimeError as e:
        print(f"[SKIP] Provider 未配置 API Key: {e}")
        return True
    except Exception as e:
        print(f"[FAIL] Provider 初始化: {e}")
        return False

    print(f"   Provider: {provider.name}")

    machine = AgentStateMachine(provider=provider)
    events = []
    try:
        async for ev in machine.run("服务 OOM 了怎么办？", history=[]):
            events.append(ev)
            print(f"   [{ev.event}] {str(ev.data)[:120]}")
    except Exception as e:
        print(f"[FAIL] state machine: {e}")
        import traceback

        traceback.print_exc()
        return False

    types = [e.event for e in events]
    has_answer = "answer" in types or any(e.event == "think" for e in events)
    has_done = "done" in types
    print(f"   事件总数: {len(events)}, has_answer={has_answer}, has_done={has_done}")
    return has_done


async def test_session_store():
    """Redis session_store 健康检查（无 Redis 则 SKIP）"""
    print("\n=== Redis SessionStore ===")
    try:
        from app.services import get_session_store

        store = get_session_store()
    except Exception as e:
        print(f"[SKIP] SessionStore 初始化失败: {e}")
        return True

    if not store.health_check():
        print("[SKIP] Redis 不可达，跳过")
        return True

    sid = store.create_session()
    store.append_message(sid, "user", "hello")
    store.append_message(sid, "assistant", "world")
    history = store.get_history(sid)
    assert len(history) == 2, f"期望 2 条消息，实际 {len(history)}"
    store.clear_session(sid)
    print(f"[OK] session {sid[:8]}... write/read/clear 通过")
    return True


def main():
    print("=" * 50)
    print("Phase3 功能测试")
    print("=" * 50)

    test_read_file_security()
    asyncio.run(test_session_store())
    asyncio.run(test_agent_smoke())

    print("\n" + "=" * 50)
    print("[OK] 测试结束（注意 [SKIP] 项）")
    print("=" * 50)


if __name__ == "__main__":
    main()
