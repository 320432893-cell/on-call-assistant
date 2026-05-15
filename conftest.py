# 项目根 conftest.py
# 作用：pytest 启动时自动把项目根加入 sys.path，让 `from app.x import y` 在测试与 IDE 中都能解析。
# 同时让 PyCharm 把该目录识别为 Test Root。

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
