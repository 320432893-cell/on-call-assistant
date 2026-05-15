# Agent 工具：readFile / writeFile
# 题面约束：只能读写 data/ 下任意文件；不能列目录、不能通配；只按文件名

import os
from pathlib import Path


# 工具描述（统一 schema，3 个 Provider 各自转换）
READ_FILE_TOOL_SCHEMA = {
    "name": "readFile",
    "description": (
        "读取 data/ 目录下指定文件的内容（如 SOP 文档 HTML）。"
        "仅支持单个文件名，不支持目录列举或通配符。"
        "示例 fname: 'sop-001.html'、'raw/sop-002.html'。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fname": {
                "type": "string",
                "description": "文件名（可含 raw/ 等子目录前缀），不允许 .. 或绝对路径",
            }
        },
        "required": ["fname"],
    },
}


WRITE_FILE_TOOL_SCHEMA = {
    "name": "writeFile",
    "description": (
        "向 data/ 目录写入文件。可用于：保存用户提供的新 SOP、记录处理过程等。"
        "默认写入 data/ 根目录；如需写入 raw/ 子目录请显式带上 'raw/' 前缀。"
        "不允许 .. 或绝对路径；同名文件会被覆盖。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fname": {
                "type": "string",
                "description": "文件名（可含子目录前缀如 raw/），不允许 .. 或绝对路径",
            },
            "content": {
                "type": "string",
                "description": "要写入的文本内容（UTF-8）",
            },
        },
        "required": ["fname", "content"],
    },
}


# data 根目录（题面允许 data/ 下任意文件，含 raw/ 子目录）
DATA_ROOT = Path("data").resolve()


def _safe_resolve(fname: str) -> tuple[Path | None, str | None]:
    """统一路径校验：返回 (resolved_path, error_msg)，二选一"""
    if not fname or not isinstance(fname, str):
        return None, "[Error] fname 必须是非空字符串"
    if os.path.isabs(fname):
        return None, "[Error] fname 不允许是绝对路径"
    if ".." in Path(fname).parts:
        return None, "[Error] fname 不允许包含 ..（路径穿越）"

    target = (DATA_ROOT / fname).resolve()
    try:
        target.relative_to(DATA_ROOT)
    except ValueError:
        return None, f"[Error] fname '{fname}' 解析后超出 data/ 范围"
    return target, None


def read_file_tool(fname: str) -> str:
    """读取 data/ 下的文件并返回内容字符串

    返回值约定：
      - 成功：文件内容（最长 50KB 截断）
      - 失败：以 "[Error] " 开头的错误信息，让 Agent 自己恢复
    """
    target, err = _safe_resolve(fname)
    if err:
        return err

    # 自动补 raw/ 前缀（用户友好：直接传 sop-001.html）
    if not target.exists() and not fname.startswith(("raw/", "raw\\")):
        alt = (DATA_ROOT / "raw" / fname).resolve()
        try:
            alt.relative_to(DATA_ROOT)
            if alt.exists():
                target = alt
        except ValueError:
            pass

    if not target.exists():
        return f"[Error] 文件不存在: {fname}（已尝试 data/{fname} 与 data/raw/{fname}）"

    if not target.is_file():
        return f"[Error] 不是文件: {fname}"

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"[Error] 文件 {fname} 非 UTF-8 文本"
    except Exception as e:
        return f"[Error] 读取失败: {e}"

    # 截断防止超长（保留前 50KB）
    MAX_BYTES = 50 * 1024
    if len(content.encode("utf-8")) > MAX_BYTES:
        content = content[:25000] + "\n\n[... 文件过长，已截断 ...]"

    return content


def write_file_tool(fname: str, content: str) -> str:
    """向 data/ 下写入文件

    返回值约定：
      - 成功：'[OK] 已写入 {path}（{N} 字节）'
      - 失败：以 '[Error] ' 开头的错误信息
    """
    target, err = _safe_resolve(fname)
    if err:
        return err
    if content is None or not isinstance(content, str):
        return "[Error] content 必须是字符串"

    # 限制单文件最大 1MB，防 LLM 滥用
    MAX_WRITE_BYTES = 1024 * 1024
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        return f"[Error] 写入内容超过 1MB 上限（当前 {len(encoded)} 字节）"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"[Error] 写入失败: {e}"

    rel = target.relative_to(DATA_ROOT)
    return f"[OK] 已写入 data/{rel}（{len(encoded)} 字节）"
