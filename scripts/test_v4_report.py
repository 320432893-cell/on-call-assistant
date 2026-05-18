"""Phase4 v4 年报 RAG 检索质量验证（HTTP 客户端模式）

通过 HTTP 调用 /v4/search 验证检索质量，避免与 uvicorn 抢 Qdrant 嵌入式锁。

前置：
    1. 另一个终端跑 uvicorn：.venv/bin/python -m uvicorn app.main:app --port 8000
    2. 已通过 POST /v4/ingest 灌库

用法：
    ./.venv/bin/python scripts/test_v4_report.py
    ./.venv/bin/python scripts/test_v4_report.py --base http://127.0.0.1:8000 --limit 5
"""

import argparse
import sys
import json
import urllib.parse
import urllib.request
from urllib.error import URLError, HTTPError

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# 4 类典型 query，每条带"期望命中关键词"用于人眼快速判别召回是否合理
QUERIES = [
    {
        "q": "公司未来三到五年的发展战略是什么",
        "expect": ["战略", "发展", "规划"],
    },
    {
        "q": "董事和高级管理人员的薪酬情况",
        "expect": ["董事", "薪酬", "高级管理"],
    },
    {
        "q": "研发投入金额和研发人员构成",
        "expect": ["研发", "投入"],
    },
    {
        "q": "公司面临的主要风险有哪些",
        "expect": ["风险"],
    },
]


def _http_get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_service(base: str) -> int:
    """检查服务存活 + 返回 collection 已有 chunk 数；服务挂了直接 exit"""
    try:
        h = _http_get_json(f"{base}/v4/health", timeout=5)
    except (URLError, HTTPError) as e:
        print(f"[ERR] 连不上 {base}/v4/health：{e}")
        print("      请先在另一个终端跑 uvicorn：")
        print("        cd ~/data_project/on-call-assistant-20260514")
        print("        .venv/bin/python -m uvicorn app.main:app --port 8000")
        sys.exit(2)
    n = int(h.get("n_indexed", 0) or 0)
    print(f"[setup] 服务存活，collection={h.get('collection')}，n_indexed={n}")
    if n == 0:
        print("[setup] collection 为空，请先 POST /v4/ingest 灌库")
        print("        curl -X POST http://127.0.0.1:8000/v4/ingest "
              "-H 'Content-Type: application/json' "
              "-d '{\"company\":\"移远通信\",\"year\":2025}'")
        sys.exit(3)
    return n


def run_query(base: str, q: str, expect: list, limit: int = 5) -> bool:
    """跑单个 query，打印 top-N 并判断是否命中期望关键词"""
    url = f"{base}/v4/search?q={urllib.parse.quote(q)}&limit={limit}"
    try:
        data = _http_get_json(url, timeout=30)
    except (URLError, HTTPError) as e:
        print(f"[ERR] {q} 请求失败：{e}")
        return False

    hits = data.get("results", [])
    print(f"\n=== Q: {q}")
    print(f"    期望关键词: {expect} | 命中数: {len(hits)}")
    if not hits:
        print("    [FAIL] 0 命中")
        return False

    hit_kw = False
    for i, r in enumerate(hits[:limit], 1):
        title = r.get("section_path", "") or ""
        snippet = r.get("snippet", "") or ""
        p_start = r.get("page_start", "?")
        p_end = r.get("page_end", "?")
        score = float(r.get("score", 0))
        match_marks = [k for k in expect if (k in title or k in snippet)]
        if match_marks:
            hit_kw = True
        flag = "✓" if match_marks else " "
        print(f"  [{i}] {flag} score={score:.3f} p{p_start}-{p_end} {title[:60]}")
        print(f"        snippet: {snippet[:100]}")
        if match_marks:
            print(f"        命中: {match_marks}")
    if not hit_kw:
        print("    [WARN] top-N 未命中任何期望关键词，需人工抽检")
    return hit_kw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="服务地址")
    parser.add_argument("--limit", type=int, default=5, help="每个 query 看几条")
    args = parser.parse_args()

    check_service(args.base)

    n_pass = 0
    for item in QUERIES:
        ok = run_query(args.base, item["q"], item["expect"], limit=args.limit)
        if ok:
            n_pass += 1

    print(f"\n=== 总结：{n_pass}/{len(QUERIES)} 个 query top-N 命中期望关键词 ===")


if __name__ == "__main__":
    main()
