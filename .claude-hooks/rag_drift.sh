#!/usr/bin/env bash
# PostToolUse hook: RAG collection drift 提醒
# 覆盖:
#   R1 — EMBEDDING_MODEL 配置改了(切 embedder)→ 必须重灌 collection
#   R3 — chunk 切分常量(chunk_size/overlap/MAX_CHARS 等)在 git 改动 → 提醒重灌
#   R4 — VectorParams.size / Distance.* 改动 → schema 不兼容
#
# 触发:被改文件含相关关键字,且 git diff(未提交+最近一次 commit) 显示改动行有这些关键字
# 输出:stderr 提醒,不阻断(改动可能合法,如重命名/重构)

set -u

input=$(cat)

file_path=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''), end='')
except Exception:
    pass
" 2>/dev/null)

[ -z "$file_path" ] && exit 0
[ ! -f "$file_path" ] && exit 0

case "$file_path" in
  *.py|*.toml|*.env|*.env.example|*settings*) ;;
  *) exit 0 ;;
esac

# git 仓库内
project_root=$(cd "$(dirname "$file_path")" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -z "$project_root" ] && exit 0

case "$project_root" in
  "$HOME/.claude"*) exit 0 ;;
esac

# 项目里有 RAG 代码才有意义
has_rag=$(find "$project_root" -maxdepth 4 -name "*.py" -not -path "*/.venv/*" -not -path "*/.git/*" \
    -exec grep -l -E "QdrantClient|sentence_transformers|EMBEDDING_MODEL" {} \; 2>/dev/null | head -1)
[ -z "$has_rag" ] && exit 0

# 文件本身有相关关键字
hits=$(grep -nE "EMBEDDING_MODEL|CHUNK_SIZE|chunk_size|MAX_CHARS|max_chars|OVERLAP|overlap|TOKENIZER|splitter|SentenceTransformer\(|QDRANT_COLLECTION|VectorParams\(.*size=|Distance\.(COSINE|EUCLID|DOT)" "$file_path" 2>/dev/null | head -5)
[ -z "$hits" ] && exit 0

# 看这些关键字是否在 git diff 改动里
unstaged_diff=$(cd "$project_root" && git diff -- "$file_path" 2>/dev/null | grep -E "^[+-]" | grep -vE "^(\+\+\+|---)" | head -20)
recent_diff=""
if [ -z "$unstaged_diff" ]; then
  recent_diff=$(cd "$project_root" && git log -1 -p --no-color -- "$file_path" 2>/dev/null | grep -E "^[+-]" | grep -vE "^(\+\+\+|---)" | head -20)
fi

combined_diff="${unstaged_diff}${recent_diff}"
[ -z "$combined_diff" ] && exit 0

risky_changes=$(echo "$combined_diff" | grep -E "EMBEDDING_MODEL|CHUNK_SIZE|chunk_size|MAX_CHARS|max_chars|OVERLAP|overlap|TOKENIZER|splitter|SentenceTransformer\(|VectorParams\(|Distance\.(COSINE|EUCLID|DOT)")
[ -z "$risky_changes" ] && exit 0

echo "" >&2
echo "[rag_drift] 文件 $file_path 改动了 RAG 数据契约关键字段:" >&2
echo "$risky_changes" | head -10 | sed 's/^/    /' >&2
echo "" >&2
echo "[rag_drift] 提醒(不阻断):" >&2
echo "    R1 — 切 EMBEDDING_MODEL → 语义空间变,collection 必须全量重灌" >&2
echo "    R3 — chunk_size/overlap/splitter 改动 → 同 doc_id 旧 chunk 与新切分不一致,必须 reindex" >&2
echo "    R4 — VectorParams.size/Distance 改动 → collection schema 不兼容,必须 drop+recreate" >&2
echo "" >&2
echo "[rag_drift] 处置:确认是否需要 reindex,或在 commit message 里说明'仅重命名/重构,语义不变'" >&2

exit 0
