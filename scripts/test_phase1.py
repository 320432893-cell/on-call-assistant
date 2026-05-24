#!/usr/bin/env python3
# Phase1 功能测试脚本

import os
import sys

# Windows 控制台 GBK 编码不下 emoji，强制 stdout 用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from app.services import close_indexer, get_indexer, get_preprocessor


def test_preprocessor():
    """测试预处理功能"""
    print("\n=== 测试预处理功能 ===")

    preprocessor = get_preprocessor()

    # 读取一个HTML文件测试
    raw_path = Path(__file__).parent.parent / "data" / "raw" / "sop-001.html"
    with open(raw_path, encoding="utf-8") as f:
        html = f.read()

    processed = preprocessor.parse_html(html, "sop-001")

    print(f"文档ID: {processed.id}")
    print(f"标题: {processed.title}")
    print(f"部门: {processed.department}")
    print(f"标签: {processed.tags}")
    print(f"章节数: {len(processed.sections)}")
    print(f"内容长度(分词后): {len(processed.content)}")
    print(f"内容前100字(分词): {processed.content[:100]}...")

    assert processed.id == "sop-001"
    assert "后端" in processed.title or "OOM" in processed.title
    print("✅ 预处理测试通过")


def test_indexer():
    """测试索引功能"""
    print("\n=== 测试索引功能 ===")

    indexer = get_indexer()
    preprocessor = get_preprocessor()

    # 导入所有文档
    raw_dir = Path(__file__).parent.parent / "data" / "raw"

    for i in range(1, 11):
        doc_id = f"sop-{i:03d}"
        file_path = raw_dir / f"{doc_id}.html"

        if not file_path.exists():
            print(f"⚠️ 文件不存在: {file_path}")
            continue

        with open(file_path, encoding="utf-8") as f:
            html = f.read()

        processed = preprocessor.parse_html(html, doc_id)

        success = indexer.add_document(
            doc_id=processed.id,
            title=processed.title,
            content=processed.content,
            content_raw=processed.content_raw,
            department=processed.department,
            tags=processed.tags,
        )

        if success:
            print(f"✅ 已索引: {doc_id} - {processed.title}")
        else:
            print(f"❌ 索引失败: {doc_id}")

    # 提交索引
    indexer.commit()
    print("✅ 索引提交完成")


def test_search():
    """测试搜索功能"""
    print("\n=== 测试搜索功能 ===")

    indexer = get_indexer()

    test_cases = [
        ("OOM", "sop-001", "应返回后端服务文档"),
        ("故障", None, "应返回多个文档"),
        ("replication", "empty", "应返回空（script标签内容被过滤）"),
        ("CDN", "sop-003,sop-010", "应返回前端和网络CDN文档"),
        ("&", None, "应返回正文中含&的文档"),
        ("主从延迟", "sop-002", "应返回数据库文档"),
    ]

    for query, expected, desc in test_cases:
        print(f"\n查询: '{query}' - {desc}")
        results = indexer.search(query, limit=10)

        if not results:
            if expected == "empty":
                print("  ✅ 返回空（符合预期）")
            else:
                print("  ⚠️ 未找到结果")
            continue

        result_ids = [r.id for r in results]
        print(f"  结果数: {len(results)}")
        print(f"  结果ID: {result_ids}")

        for r in results[:3]:
            print(f"    - {r.id}: {r.title[:30]}... (score: {r.score:.4f})")

        # 验证期望
        if expected and expected != "empty":
            expected_ids = expected.split(",")
            for exp_id in expected_ids:
                if exp_id in result_ids:
                    print(f"  ✅ 包含期望: {exp_id}")
                else:
                    print(f"  ⚠️ 缺少期望: {exp_id}")


def test_edge_cases():
    """测试边界情况"""
    print("\n=== 测试边界情况 ===")

    indexer = get_indexer()

    # 空查询
    print("\n测试空查询...")
    results = indexer.search("")
    print(f"  结果: {len(results)} 条（空查询应返回0条）")

    # 特殊字符
    print("\n测试特殊字符...")
    for special in ["<", ">", '"', "'", "/"]:
        try:
            results = indexer.search(special, limit=5)
            print(f"  '{special}': {len(results)} 条结果")
        except Exception as e:
            print(f"  '{special}': 查询失败 - {e}")


def main():
    print("=" * 50)
    print("Phase1 功能测试")
    print("=" * 50)

    try:
        test_preprocessor()
        test_indexer()
        test_search()
        test_edge_cases()

        print("\n" + "=" * 50)
        print("✅ 所有测试完成")
        print("=" * 50)

    finally:
        close_indexer()


if __name__ == "__main__":
    main()
