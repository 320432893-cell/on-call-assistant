#!/usr/bin/env bash
# Regression tests for rule_activator.sh and exploration_gate.sh marker flow.
set -u

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RULE_ACTIVATOR="$HOOK_DIR/rule_activator.sh"
EXPLORATION_GATE="$HOOK_DIR/exploration_gate.sh"
PROJECT_ROOT="$(cd "$HOOK_DIR/.." && pwd -P)"
TASK_HASH=$(printf '%s' "$PROJECT_ROOT" | md5sum | cut -c1-12)
EXPLORATORY_MARKER="/tmp/ai_task_exploratory_${TASK_HASH}"
CONFIRMED_MARKER="/tmp/ai_task_confirmed_${TASK_HASH}"
PASS=0; FAIL=0; TOTAL=0
trap 'rm -f "$EXPLORATORY_MARKER" "$CONFIRMED_MARKER"' EXIT

json_prompt() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps({"prompt": sys.argv[1]}))
PY
}

json_edit() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps({"tool_name": "Edit", "tool_input": {"file_path": sys.argv[1]}}))
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

assert_file_exists() {
  local desc="$1" file="$2"
  TOTAL=$((TOTAL + 1))
  if [ -f "$file" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: expected marker $file" >&2
  fi
}

rm -f "$EXPLORATORY_MARKER" "$CONFIRMED_MARKER"

echo "--- rule_activator: creates project-scoped exploratory marker ---"
json_prompt "设计一个新项目方案" | bash "$RULE_ACTIVATOR" >/tmp/rule_gate_out 2>/tmp/rule_gate_err
assert_file_exists "rule_activator creates exploratory marker" "$EXPLORATORY_MARKER"

echo "--- exploration_gate: blocks code edit while unconfirmed ---"
set +e
json_edit "$PROJECT_ROOT/app/example.py" | bash "$EXPLORATION_GATE" >/tmp/rule_gate_out 2>/tmp/rule_gate_err
rc=$?
set -e
assert_exit "exploration_gate blocks unconfirmed code edit" 2 "$rc"

echo "--- exploration_gate: allows docs/config edit while unconfirmed ---"
set +e
json_edit "$PROJECT_ROOT/docs/example.md" | bash "$EXPLORATION_GATE" >/tmp/rule_gate_out 2>/tmp/rule_gate_err
rc=$?
set -e
assert_exit "exploration_gate allows md edit" 0 "$rc"

echo "--- rule_activator: confirmation marker releases gate ---"
json_prompt "可以" | bash "$RULE_ACTIVATOR" >/tmp/rule_gate_out 2>/tmp/rule_gate_err
set +e
json_edit "$PROJECT_ROOT/app/example.py" | bash "$EXPLORATION_GATE" >/tmp/rule_gate_out 2>/tmp/rule_gate_err
rc=$?
set -e
assert_exit "exploration_gate allows confirmed code edit" 0 "$rc"

echo ""
echo "========================================="
echo "  result: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
