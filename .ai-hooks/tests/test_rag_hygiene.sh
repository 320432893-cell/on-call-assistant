#!/usr/bin/env bash
# rag_hygiene.sh 单测：hook 只保留 BGE encode 缺 is_query。
set -u

HOOK="$(cd "$(dirname "$0")/.." && pwd)/rag_hygiene.sh"
PASS=0; FAIL=0; TOTAL=0
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

assert_contains() {
  local desc="$1" expected="$2" actual="$3"
  TOTAL=$((TOTAL + 1))
  if echo "$actual" | grep -qF "$expected"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected stderr contains '$expected'" >&2
    echo "  actual: $(echo "$actual" | head -3)" >&2
  fi
}

assert_empty() {
  local desc="$1" actual="$2"
  TOTAL=$((TOTAL + 1))
  if [ -z "$actual" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected empty stderr" >&2
    echo "  actual: $(echo "$actual" | head -3)" >&2
  fi
}

run_hook() {
  local file_path="$1"
  echo "{\"tool_input\":{\"file_path\":\"$file_path\"}}" \
    | bash "$HOOK" 2>&1 1>/dev/null
}

cat > "$TMP_ROOT/missing_is_query.py" <<'PY'
from sentence_transformers import SentenceTransformer

bge_embedder = SentenceTransformer("BAAI/bge-m3")

def encode_query(text):
    return bge_embedder.encode(text)
PY

out=$(run_hook "$TMP_ROOT/missing_is_query.py")
assert_contains "BGE encode missing is_query" "缺 is_query" "$out"

cat > "$TMP_ROOT/has_is_query.py" <<'PY'
from sentence_transformers import SentenceTransformer

bge_embedder = SentenceTransformer("BAAI/bge-m3")

def encode_query(text):
    return bge_embedder.encode(text, is_query=True)
PY

out=$(run_hook "$TMP_ROOT/has_is_query.py")
assert_empty "BGE encode with is_query" "$out"

cat > "$TMP_ROOT/semgrep_owned.py" <<'PY'
from qdrant_client.models import Distance, VectorParams

def f(embedder, vs, text):
    embedder.encode(text, normalize_embeddings=False)
    VectorParams(size=1024, distance=Distance.COSINE)
    return vs.search(query_vector=[0.1], limit=1)
PY

out=$(run_hook "$TMP_ROOT/semgrep_owned.py")
assert_empty "semgrep-owned checks are not hook-owned" "$out"

echo ""
echo "========================================="
echo "  result: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
