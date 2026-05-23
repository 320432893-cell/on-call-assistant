#!/usr/bin/env bash
# Regression tests for dangerous_bash.sh and git_commit_safety.sh.
set -u

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DANGEROUS="$HOOK_DIR/dangerous_bash.sh"
GIT_SAFETY="$HOOK_DIR/git_commit_safety.sh"
PASS=0; FAIL=0; TOTAL=0
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT
RUN_RC=0

json_command() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps({"tool_input": {"command": sys.argv[1]}}))
PY
}

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

run_dangerous() {
  local command="$1"
  json_command "$command" | bash "$DANGEROUS" >/tmp/bash_safety_out 2>/tmp/bash_safety_err
  RUN_RC=$?
}

run_git_safety() {
  local repo="$1" command="$2"
  (cd "$repo" && json_command "$command" | bash "$GIT_SAFETY" >/tmp/git_safety_out 2>/tmp/git_safety_err)
  RUN_RC=$?
}

echo "--- dangerous_bash: blocks newline JSON command ---"
run_dangerous 'printf "x\ny" && rm -rf /tmp/nope'
assert_exit "dangerous_bash blocks rm -rf after JSON decode" 2 "$RUN_RC"

echo "--- dangerous_bash: allows harmless command ---"
run_dangerous 'printf "git reset --hard"'
assert_exit "dangerous_bash does not inspect quoted text as command" 0 "$RUN_RC"

repo="$TMP_ROOT/repo"
mkdir -p "$repo"
git -C "$repo" init -q
git -C "$repo" config user.email test@example.com
git -C "$repo" config user.name Test
echo "SECRET=x" > "$repo/.env"
git -C "$repo" add .env

echo "--- git_commit_safety: blocks real git commit with staged secret ---"
run_git_safety "$repo" 'git commit -m test'
assert_exit "git_commit_safety blocks risky staged commit" 2 "$RUN_RC"

echo "--- git_commit_safety: ignores quoted git commit text ---"
run_git_safety "$repo" 'printf "git commit -m test"'
assert_exit "git_commit_safety uses token-level command parsing" 0 "$RUN_RC"

echo "--- git_commit_safety: detects git global options ---"
run_git_safety "$repo" "git -C '$repo' commit -m test"
assert_exit "git_commit_safety detects git -C commit" 2 "$RUN_RC"

echo ""
echo "========================================="
echo "  result: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
