# Agent system prompt 与文件目录

from pathlib import Path
from bs4 import BeautifulSoup


def build_file_catalog() -> str:
    """生成可读的文件目录注入 system prompt。
    题面禁止 Agent 自己列目录，但 prompt 工程师可以提供清单提示。

    实现：直接扫 data/raw/*.html，解析每份 HTML 的 <title>，给出 (id, 标题) 列表。
    避免依赖可能与实际 HTML 失配的 metadata.json。
    """
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return "（暂无可用文件清单）"

    lines = []
    for html_file in sorted(raw_dir.glob("sop-*.html")):
        doc_id = html_file.stem
        try:
            soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")
            title_tag = soup.find("title")
            h1_tag = soup.find("h1")
            title = (title_tag.get_text(strip=True) if title_tag
                     else (h1_tag.get_text(strip=True) if h1_tag else doc_id))
        except Exception:
            title = doc_id
        lines.append(f"- {doc_id}.html  {title}")
    return "\n".join(lines) if lines else "（暂无可用文件清单）"


SYSTEM_PROMPT_TEMPLATE = """你是 On-Call 助手，帮助工程师快速定位故障处理方案。

【可用工具】
- readFile(fname: string) -> string
  读取 data/ 目录下的指定文件。fname 例如 'sop-001.html'。
  不能列目录、不能用通配符。
- writeFile(fname: string, content: string) -> string
  向 data/ 目录写入文件。可用于保存用户提供的新 SOP、记录处理结论等。
  仅在用户明确要求"保存/记录/创建文件"时调用，普通问答不要主动写文件。

【可用 SOP 文档清单】
{file_catalog}

【工作规范】
1. 根据用户问题，判断需要查阅哪一份或几份 SOP。
2. 使用 readFile 工具读取对应 HTML 文件，提取处理步骤。
3. 综合多个 SOP 给出条理化的回答，必要时引用文档 ID（如 sop-001.html）。
4. 如果用户问题不在已知清单内，明确告知"未在 SOP 库中找到相关内容"，不要编造。
5. 回答使用中文，简洁、结构化（要点列表 / 编号步骤）。
"""


def get_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(file_catalog=build_file_catalog())


# 兼容旧引用
SYSTEM_PROMPT = get_system_prompt
