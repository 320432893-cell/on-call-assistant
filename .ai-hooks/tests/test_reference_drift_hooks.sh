#!/usr/bin/env bash
# Regression tests for rename_audit.sh and rag_drift.sh.
set -u

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RENAME_AUDIT="$HOOK_DIR/rename_audit.sh"
RAG_DRIFT="$HOOK_DIR/rag_drift.sh"
PASS=0; FAIL=0; TOTAL=0
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"; rm -f /tmp/rename_pwned' EXIT

assert_exit() {
  local desc="$1" expected="$2" actual="$3"
  TOTAL=$((TOTAL + 1))
  if [ "$actual" -eq "$expected" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected exit $expected, got $actual" >&2
  fi
}

assert_contains() {
  local desc="$1" expected="$2" file="$3"
  TOTAL=$((TOTAL + 1))
  if grep -qF "$expected" "$file"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected $file contains '$expected'" >&2
    head -5 "$file" >&2
  fi
}

assert_not_exists() {
  local desc="$1" file="$2"
  TOTAL=$((TOTAL + 1))
  if [ ! -e "$file" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: unexpected file exists: $file" >&2
  fi
}

json_edit_payload() {
  local file_path="$1" old_string="$2" new_string="$3"
  python3 - "$file_path" "$old_string" "$new_string" <<'PY'
import json
import sys
print(json.dumps({
    "tool_name": "Edit",
    "tool_input": {
        "file_path": sys.argv[1],
        "old_string": sys.argv[2],
        "new_string": sys.argv[3],
    },
}))
PY
}

json_file_payload() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

echo "--- rename_audit: file_path injection is inert ---"
rm -f /tmp/rename_pwned
set +e
json_edit_payload '/tmp/x$(touch /tmp/rename_pwned).py' $'def old_name():\n    pass\n' '' \
  | bash "$RENAME_AUDIT" >/tmp/rename_out 2>/tmp/rename_err
rc=$?
set -e
assert_exit "rename_audit injection payload exits cleanly" 0 "$rc"
assert_not_exists "rename_audit does not execute file_path payload" /tmp/rename_pwned

echo "--- rename_audit: warns on ghost reference ---"
repo="$TMP_ROOT/rename_repo"
mkdir -p "$repo"
git -C "$repo" init -q
cat > "$repo/a.py" <<'PY'
def old_symbol():
    pass
PY
cat > "$repo/b.py" <<'PY'
from a import old_symbol
old_symbol()
PY
set +e
json_edit_payload "$repo/a.py" $'def old_symbol():\n    pass\n' '' \
  | bash "$RENAME_AUDIT" >/tmp/rename_out 2>/tmp/rename_err
rc=$?
set -e
assert_exit "rename_audit ghost reference check exits cleanly" 0 "$rc"
assert_contains "rename_audit reports old symbol" "old_symbol" /tmp/rename_err

echo "--- rag_drift: warns on chunk contract change ---"
rag_repo="$TMP_ROOT/rag_repo"
mkdir -p "$rag_repo"
git -C "$rag_repo" init -q
git -C "$rag_repo" config user.email test@example.com
git -C "$rag_repo" config user.name Test
cat > "$rag_repo/rag.py" <<'PY'
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "BAAI/bge-m3"
CHUNK_SIZE = 800
embedder = SentenceTransformer(EMBEDDING_MODEL)
PY
git -C "$rag_repo" add rag.py
git -C "$rag_repo" commit -q -m init
python3 - "$rag_repo/rag.py" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
path.write_text(text.replace('CHUNK_SIZE = 800', 'CHUNK_SIZE = 1000'))
PY
set +e
json_file_payload "$rag_repo/rag.py" | bash "$RAG_DRIFT" >/tmp/rag_out 2>/tmp/rag_err
rc=$?
set -e
assert_exit "rag_drift hook remains non-blocking" 0 "$rc"
assert_contains "rag_drift reports chunk contract change" "CHUNK_SIZE" /tmp/rag_err

echo ""
echo "========================================="
echo "  result: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
