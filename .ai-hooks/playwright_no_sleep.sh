#!/usr/bin/env bash
# PostToolUse hook (Edit/Write/MultiEdit): playwright 文件禁 time.sleep
# 对应 web-automation.md § 3 — Playwright 等待策略,禁硬编码 time.sleep
#
# 工作原理:
#   - 文件 import playwright/playwright.sync_api → 标记为 Playwright 文件
#   - 文件含 time.sleep( → stderr 报警
#   - playwright 自带 wait_for_selector / page.wait_for_timeout,后者用于明确节流也比 time.sleep 好

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
  *.py) ;;
  *) exit 0 ;;
esac

# 判定 Playwright 文件
if ! grep -qE "(from playwright|import playwright)" "$file_path" 2>/dev/null; then
  exit 0
fi

# 找 time.sleep( 调用
sleeps=$(grep -nE "(^|[^a-zA-Z_])time\.sleep\(" "$file_path" 2>/dev/null | head -5)
[ -z "$sleeps" ] && exit 0

echo "" >&2
echo "[playwright_no_sleep] 文件 $file_path 含 time.sleep(,违反 web-automation.md § 3 等待策略" >&2
echo "$sleeps" | sed 's/^/    /' >&2
echo "" >&2
echo "[playwright_no_sleep] 处置:" >&2
echo "    ① 元素出现等待: page.wait_for_selector(sel, state='visible')" >&2
echo "    ② 网络空闲等待: page.wait_for_load_state('networkidle')" >&2
echo "    ③ 必须延时节流: page.wait_for_timeout(ms)(显式标注节流原因)" >&2

exit 0
