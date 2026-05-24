#!/usr/bin/env python3
"""Phase2 功能测试：Embedding + Qdrant"""

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from app.services import get_embedder, get_preprocessor, get_vectorstore


def test_embedding():
    """测试Embedding服务"""
    print("\n=== 测试 Embedding 服务 ===")

    embedder = get_embedder()

    # 健康检查
    print("\n1. 健康检查...")
    healthy = embedder.health_check()
    print(f"   健康: {healthy}")
    assert healthy, "Embedding服务不健康"

    # 维度检查
    print(f"\n2. 向量维度: {embedder.dimension}")

    # 单条编码
    print("\n3. 单条编码测试...")
    text = "OOM故障排查流程"
    vec = embedder.encode(text)
    assert vec is not None, "编码失败"
    print(f"   文本: {text}")
    print(f"   维度: {len(vec)}")
    print(f"   L2范数: {(vec**2).sum() ** 0.5:.6f}")

    print("[OK] Embedding测试通过")


def test_qdrant():
    """测试Qdrant向量服务"""
    print("\n=== 测试 Qdrant 服务 ===")

    vectorstore = get_vectorstore()
    embedder = get_embedder()

    # 健康检查
    print("\n1. 健康检查...")
    healthy = vectorstore.health_check()
    print(f"   健康: {healthy}")
    assert healthy, "Qdrant服务不健康"

    # 统计当前数量
    print(f"\n2. 当前文档数: {vectorstore.count()}")

    print("[OK] Qdrant健康检查通过")


def test_vector_index_and_search():
    """测试向量索引和检索"""
    print("\n=== 测试向量索引与检索 ===")

    preprocessor = get_preprocessor()
    embedder = get_embedder()
    vectorstore = get_vectorstore()

    # 读取并索引文档
    print("\n1. 索引文档...")
    raw_dir = Path(__file__).parent.parent / "data" / "raw"

    indexed = 0
    for i in range(1, 11):
        doc_id = f"sop-{i:03d}"
        file_path = raw_dir / f"{doc_id}.html"

        if not file_path.exists():
            print(f"   [跳过] {doc_id} 文件不存在")
            continue

        with open(file_path, encoding="utf-8") as f:
            html = f.read()

        # 预处理
        processed = preprocessor.parse_html(html, doc_id)

        # 生成向量
        vector = embedder.encode(processed.content_raw)
        if vector is None:
            print(f"   [失败] {doc_id} 向量生成失败")
            continue

        # 存入Qdrant
        success = vectorstore.upsert(
            doc_id=doc_id,
            vector=vector,
            payload={
                "title": processed.title,
                "department": processed.department,
                "tags": processed.tags,
                "content_raw": processed.content_raw[:500],  # 截断
            },
        )

        if success:
            indexed += 1
            print(f"   [OK] {doc_id} - {processed.title}")
        else:
            print(f"   [失败] {doc_id}")

    print(f"\n   共索引: {indexed} 篇文档")
    print(f"   总文档数: {vectorstore.count()}")

    # 语义检索测试
    print("\n2. 语义检索测试...")

    test_queries = [
        ("内存溢出怎么排查", "sop-001"),
        ("数据库主从同步问题", "sop-002"),
        ("网站打开白屏怎么办", "sop-003"),
        ("服务器部署运维", "sop-004"),
    ]

    for query, expected_id in test_queries:
        print(f"\n   查询: '{query}'")
        query_vec = embedder.encode(query)
        if query_vec is None:
            print("      [失败] 向量生成失败")
            continue

        results = vectorstore.search(query_vec, limit=5)
        if not results:
            print("      [空] 无结果")
            continue

        print(f"      结果数: {len(results)}")
        for j, r in enumerate(results[:3]):
            mark = "<-- 期望" if r.id == expected_id else ""
            print(f"      {j + 1}. {r.id}: {r.payload.get('title', '')[:25]}... (score: {r.score:.4f}) {mark}")

        # 检查期望
        top_ids = [r.id for r in results[:3]]
        if expected_id in top_ids:
            print(f"      [OK] 期望 {expected_id} 在Top3")
        else:
            print(f"      [WARN] 期望 {expected_id} 不在Top3")

    print("\n[OK] 向量检索测试完成")


def test_department_filter():
    """测试部门过滤"""
    print("\n=== 测试部门过滤 ===")

    embedder = get_embedder()
    vectorstore = get_vectorstore()

    query = "故障处理流程"
    query_vec = embedder.encode(query)

    print(f"\n查询: '{query}'")
    print("\n无过滤结果:")
    results = vectorstore.search(query_vec, limit=5)
    for r in results[:3]:
        dept = r.payload.get("department", "")
        print(f"   {r.id}: [{dept}] {r.payload.get('title', '')[:20]}...")

    print("\n过滤 [后端服务]:")
    results = vectorstore.search(query_vec, limit=5, department_filter="后端服务")
    for r in results[:3]:
        dept = r.payload.get("department", "")
        print(f"   {r.id}: [{dept}] {r.payload.get('title', '')[:20]}...")

    print("\n[OK] 部门过滤测试完成")


def main():
    print("=" * 50)
    print("Phase2 功能测试")
    print("=" * 50)

    try:
        test_embedding()
        test_qdrant()
        test_vector_index_and_search()
        test_department_filter()

        print("\n" + "=" * 50)
        print("[OK] Phase2 所有测试完成")
        print("=" * 50)

    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        return 1

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
