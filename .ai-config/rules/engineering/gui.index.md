# GUI 分层骨架(通用)

本文件是 `AGENTS.md` 代码身份(§3)在桌面/客户端 GUI 上的下放。仅 GUI 项目读;纯后端/库/CLI 不读。
目标:层级清晰、依赖单向、可逆好改——加任何新功能只按角色起名,自动守规矩,不必每次重想架构。
框架无关(PySide6/PyQt/Tk/Electron 同理),"UI 框架"指当前所用那套。

## 1. 七个角色(按文件/目录名识别,不靠注释)

| 角色 | 典型文件 | 干什么 |
|---|---|---|
| `models` | `models.py` `constants.py` | 纯数据 + 常量,无行为 |
| `infra` | `core/` 下 config/storage/task/notification/error | 公共底座:配置、持久化、任务线程、通知 |
| `ui-kit` | `core/ui_*` 或 `ui/` | 可复用 UI 组件/弹窗/输入行 |
| `domain` | `engine` `*_core` `matching_*` `report*` 等 | 业务算法、数据处理 |
| `service` | `service.py` | 业务入口:**界面唯一的调用点** |
| `view` | `page.py` `view_*` `display_*` | 界面:装配组件、显示、转发点击 |
| `shell` | `main_window` `registry_init` `app` | 组合根:装配并注入一切 |

新模块 = 按这套角色名建文件,即自动落入规范。

## 2. 一条主规则:只能从上往下依赖,禁跳级、禁横向

```
shell → view → service → domain → models
                  ↘ infra ↙        ↑
        ui-kit ─────────────────────┘(view/ui-kit 用)
```

- `[机器]` view 不得直接依赖 domain(必须经 service);service 不得依赖 UI 框架;domain 不得依赖 UI 框架/service/view;infra·ui-kit 不得依赖业务模块(modules)。
- `[机器]` 模块间不互相 import 对方内部(`模块A` 不引 `模块B.*`);跨模块共享 → 下沉 infra 或 models。
- `[机器]` infra 数据层(config/storage)保持 UI 框架无关;任务线程(QThread 等)单列为 infra-runtime,是唯一可碰 UI 框架的 infra。

## 3. 三条行为规则(import 看不出,靠 semgrep/复核)

- `[机器]` **view 不直接写持久化**:`store.save(...)` / `history.append(...)` 等写入必须经 service 或编排层(presenter/handler),view 只读不写。
- `[机器]` **domain 不留魔法数**:业务阈值/容差(如 `0.01`、分数线)只许定义在 `constants.py`/`models`,不散落字面量。
- `[机器]` **禁 `time.sleep` 轮询**:等待按客观信号(窗口/PID/DOM/端口)轮询。

## 4. 可逆性约定

- view 越胖越难改:`page.py` 只做装配 + 信号转发,任务生命周期/结果处理/持久化放编排层(presenter/handler/form_state)。
- 一处职责一个文件:拆分时保留原公开入口或兼容代理,兼容别名 MUST 注明清理条件(见 `AGENTS.md` 生命周期)。
- 状态单一源:同一状态(如"当前步骤")只存一处(view_model/presenter),不在 view 与编排层各存一份。

## 5. 机器执行

- import 规则 → `check_arch.py`(AST 静态、不 import,按角色判层;已知欠债进白名单 green-now/ratchet-later)。
- 行为规则 → semgrep 自定义规则 + 子 agent 复核(语义层)。
- 角色识别:目录+文件名约定为默认;特例可由文件边界块 `# 允许依赖层:` 覆盖。
