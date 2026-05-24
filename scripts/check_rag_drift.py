#!/usr/bin/env python3
"""Detect RAG data-contract drift from git diffs.

This script is shared by the AI hook and CI/manual checks so RAG drift logic
does not live only inside a PostToolUse shell hook.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

FILE_RE = re.compile(r"(\.py|\.toml|\.env|\.env\.example)$|settings")
RAG_RE = re.compile(r"QdrantClient|sentence_transformers|EMBEDDING_MODEL")
CONTRACT_RE = re.compile(
    r"EMBEDDING_MODEL|CHUNK_SIZE|chunk_size|MAX_CHARS|max_chars|"
    r"OVERLAP|overlap|TOKENIZER|splitter|SentenceTransformer\(|"
    r"QDRANT_COLLECTION|VectorParams\(.*size=|Distance\.(COSINE|EUCLID|DOT)"
)
DIFF_RE = re.compile(
    r"EMBEDDING_MODEL|CHUNK_SIZE|chunk_size|MAX_CHARS|max_chars|"
    r"OVERLAP|overlap|TOKENIZER|splitter|SentenceTransformer\(|"
    r"VectorParams\(|Distance\.(COSINE|EUCLID|DOT)"
)


def run_git(root: pathlib.Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def git_root(path: pathlib.Path) -> pathlib.Path | None:
    start = path if path.is_dir() else path.parent
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return pathlib.Path(proc.stdout.strip())


def has_rag_code(root: pathlib.Path) -> bool:
    skip_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules"}
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            if RAG_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
                return True
        except OSError:
            continue
    return False


def candidate_files(root: pathlib.Path, file_path: pathlib.Path | None) -> list[pathlib.Path]:
    if file_path is not None:
        return [file_path]

    names = set(run_git(root, ["diff", "--name-only"]).splitlines())
    if not names:
        names = set(run_git(root, ["diff", "--name-only", "HEAD~1..HEAD"]).splitlines())

    files: list[pathlib.Path] = []
    for name in sorted(names):
        path = root / name
        if path.is_file() and FILE_RE.search(name):
            files.append(path)
    return files


def changed_lines(root: pathlib.Path, file_path: pathlib.Path) -> list[str]:
    rel = str(file_path.relative_to(root))
    diff = run_git(root, ["diff", "--", rel])
    if not diff:
        diff = run_git(root, ["log", "-1", "-p", "--no-color", "--", rel])
    lines = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            lines.append(line)
    return lines


def find_risky_changes(root: pathlib.Path, file_path: pathlib.Path) -> list[str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    if not CONTRACT_RE.search(text):
        return []
    return [line for line in changed_lines(root, file_path) if DIFF_RE.search(line)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=pathlib.Path)
    parser.add_argument("--quiet-ok", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return 1 when RAG data-contract drift is detected.")
    args = parser.parse_args()

    root = git_root(args.file or pathlib.Path.cwd())
    if root is None or not has_rag_code(root):
        return 0

    findings: list[tuple[pathlib.Path, list[str]]] = []
    for path in candidate_files(root, args.file):
        if not path.exists() or not FILE_RE.search(str(path)):
            continue
        risky = find_risky_changes(root, path)
        if risky:
            findings.append((path, risky[:10]))

    if not findings:
        return 0

    for path, lines in findings:
        print(f"[rag_drift] 文件 {path} 改动了 RAG 数据契约关键字段:", file=sys.stderr)
        for line in lines:
            print(f"    {line}", file=sys.stderr)
        print("", file=sys.stderr)

    print("[rag_drift] 提醒(不阻断):", file=sys.stderr)
    print("    EMBEDDING_MODEL 改动 -> 语义空间变,collection 必须全量重灌", file=sys.stderr)
    print("    chunk_size/overlap/splitter 改动 -> 旧 chunk 与新切分不一致,必须 reindex", file=sys.stderr)
    print("    VectorParams.size/Distance 改动 -> collection schema 不兼容,必须 drop+recreate", file=sys.stderr)
    print("[rag_drift] 处置:确认是否需要 reindex,或说明仅重命名/重构且语义不变", file=sys.stderr)
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
