#!/usr/bin/env bash
# Regression tests for dirty_static_review.sh.
set -u

HOOK="$(cd "$(dirname "$0")/.." && pwd)/dirty_static_review.sh"
PASS=0; FAIL=0; TOTAL=0
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"; rm -f /tmp/dirty_static_pwned' EXIT

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
  if grep -qF -- "$expected" "$file"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected $file contains '$expected'" >&2
    head -20 "$file" >&2
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

json_file_payload() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
}

repo="$TMP_ROOT/repo"
mkdir -p "$repo/bin" "$repo/.ai-config"
git init -q "$repo"

cat > "$repo/bin/ruff" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$TMP_RUFF_ARGS"
echo "fake ruff finding"
exit 1
SH
chmod +x "$repo/bin/ruff"

cat > "$repo/.ai-config/dirty_diff_review.py" <<'PY'
#!/usr/bin/env python3
import sys
print("[dirty_diff] fake diff smell", file=sys.stderr)
raise SystemExit(1)
PY

cat > "$repo/bad.py" <<'PY'
def broken(
PY

TMP_RUFF_ARGS="$TMP_ROOT/ruff_args" PATH="$repo/bin:$PATH" json_file_payload "$repo/bad.py" \
  | TMP_RUFF_ARGS="$TMP_ROOT/ruff_args" PATH="$repo/bin:$PATH" bash "$HOOK" >/tmp/dirty_static_out 2>/tmp/dirty_static_err
rc=$?

assert_exit "dirty_static_review never blocks" 0 "$rc"
assert_contains "prints paradigm prompt" "范式/思想" /tmp/dirty_static_err
assert_contains "reports py_compile" "py_compile failed" /tmp/dirty_static_err
assert_contains "reports ruff findings" "fake ruff finding" /tmp/dirty_static_err
assert_contains "ruff is no-fix" "--no-fix" "$TMP_ROOT/ruff_args"
assert_contains "reports dirty diff smells" "fake diff smell" /tmp/dirty_static_err

echo "plain text" > "$repo/note.txt"
json_file_payload "$repo/note.txt" | bash "$HOOK" >/tmp/dirty_static_txt_out 2>/tmp/dirty_static_txt_err
assert_contains "non-python still prompts paradigm" "范式/思想" /tmp/dirty_static_txt_err

rm -f /tmp/dirty_static_pwned
json_file_payload '/tmp/x$(touch /tmp/dirty_static_pwned).py' | bash "$HOOK" >/tmp/dirty_static_inject_out 2>/tmp/dirty_static_inject_err
assert_not_exists "file_path is not evaluated" /tmp/dirty_static_pwned

echo ""
echo "========================================="
echo "  result: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
