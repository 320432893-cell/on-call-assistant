"""验证 report_pdf.parse_annual_report 在移远通信年报上的输出"""

import sys
from pathlib import Path

# 兜底 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 项目根入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.report_pdf import parse_annual_report, chunks_to_jsonl

PDF = "data/raw/annual_reports/移远通信_2025.pdf"
OUT = "data/processed/annual_reports/移远通信_2025/chunks.jsonl"


def main():
    chunks = parse_annual_report(PDF, company="移远通信", year=2025)
    print(f"chunks 总数: {len(chunks)}")

    if not chunks:
        return

    # 长度分布
    lens = [c.n_chars for c in chunks]
    print(f"text 长度: min={min(lens)}, max={max(lens)}, avg={sum(lens) // len(lens)}")
    # 表格数
    n_tables = sum(len(c.tables) for c in chunks)
    print(f"表格总数: {n_tables}（attach 在 chunk 上）")
    # 页面覆盖
    pages_covered = sum(c.page_end - c.page_start + 1 for c in chunks)
    print(f"页面覆盖累计: {pages_covered}（含同页多 chunk 重复计数）")

    # 看几个样例
    print("\n--- 前 3 个 chunk 的 section_path / 页范围 / 字数 ---")
    for c in chunks[:3]:
        print(f"  [{c.page_start}-{c.page_end}] ({c.n_chars}字) {c.section_path}")

    print("\n--- 5 个含表格的 chunk ---")
    cnt = 0
    for c in chunks:
        if c.tables and cnt < 5:
            print(f"  [{c.page_start}-{c.page_end}] ({c.n_chars}字, {len(c.tables)}表) {c.section_path}")
            cnt += 1

    print("\n--- 中段一个 chunk 的内容预览 ---")
    mid = chunks[len(chunks) // 2]
    print(f"  chunk_id: {mid.chunk_id}")
    print(f"  section_title: {mid.section_title}")
    print(f"  page_range: [{mid.page_start}-{mid.page_end}]")
    print("  text 前 400 字:")
    print("  " + mid.text[:400].replace("\n", "\n  "))
    if mid.tables:
        print(f"  含 {len(mid.tables)} 个表格，第 1 个前 200 字:")
        print("  " + mid.tables[0][:200].replace("\n", "\n  "))

    # 写入 jsonl
    n = chunks_to_jsonl(chunks, OUT)
    print(f"\n已写入 {n} 条 chunk → {OUT}")


if __name__ == "__main__":
    main()
