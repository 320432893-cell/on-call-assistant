# 复核 — 一个入口·三档

人话:**快速=改完自动(不用喊);另两个你给路径 + 说「阶段」或「大清理」。** 机器供 scope,判断/批准留人。

三档 = `check.py` 三 profile(速度×影响):

| 你说 | 机器跑 | 谁触发 |
|---|---|---|
| (默认) | `check.py fast`(ruff/compile,秒级) | 每次改完·hook 自动 |
| **阶段** | `check.py stage`(import-linter/import-cycles/architecture/naming/detect-secrets) | 你喊 |
| **大清理** | `check.py cleanup`(全量:+vulture/reachability/name-health/layer-drift/radon/basedpyright/semgrep/pytest) | 你喊 |

闸健康先于信任:`check.py --doctor` 验每个闸装了没(假闸=配了没装,红)。

不变量(违则停):
- 时机=人(机器拿不到进度);承重=机器扇入/`check_cohesion`(非人眼);放行批准=人(AI 提议+证据、闸红逼审);行为安全=测试。
- **绿闸 ≠ 架构无恙,只证 L4/L5**;L1–L3 工具够不到,靠人/agent 审。
- **拆分判据=连通度非行数**:拆前跑 `check_cohesion`,最大连通块≥80%=内聚不拆(硬拆=造循环依赖)。
- 成本∝1/频率:per-commit 禁全仓扫;贵活只在大清理。

五层(审从上往下,上层没过别下层):
| 层 | 裁判 |
|---|---|
| L1 依赖方向/分层 | import-linter/import-cycles + 人定契约对不对 |
| L2 归属/双源 | def·class 名近似+签名+扇入(name-health);不同名→子agent对抗 |
| L3 契约/不变量 | 真测试(跑出来) |
| L4 死码/形状 | vulture/reachability/radon/check_cohesion |
| L5 整洁 | ruff/check_naming |

---

## 快速(默认·每次改完·自动)
hook 跑 ruff/compile(秒级)。无需你喊;不过别提交。

## 阶段检查(你喊「阶段」+ 路径)
机器:`check.py stage`。人/agent 审机器判不了的语义层,按**扰动 scope**(git diff+AST→待审面,确定性非察觉):
- 新跨包 import → L1 依赖方向(import-linter 守 + 人定契约对不对)。
- 新顶层 def 近名 / 盖既有能力 → L2 双源(`check_cohesion`+近名+扇入叉乘;近名+一死=删候选;不同名→finder→refuter);入口是否真薄(业务逻辑别混进 tools 入口)。
- 公共签名/返回变 · 碰 save·batch·幂等 → L3 真测试(幂等连调2次副作用=1、部分成功注入第N+1条可区分、返回结构可判别)。
- 新抽象(继承 ABC/注册分发/包装层)→ `code.index.md` §1 索三点证据。
- 四类全空(文档/局部 bugfix)→ 只机器档,不深审。审查量=扰动量。
审法:按亮面喂子agent对抗,finder→refuter(默认存疑)、逐条交一次一条、坐实才动手。
合 main:机器档全过 + 四档结论 + 死码/双源清单 + 放行 pending(待批)。

## 大清理(你喊「大清理」+ 路径)
机器:`check.py cleanup`(全量;假闸自动跳过,`--doctor` 看健康)。人/agent 审 vulture/可达性判不出的语义死码:
- 每条「该删」grep 自验**全仓零 live caller**(无 `getattr`/`__all__`/字符串分发)→ finder→refuter 全局证伪 → 人裁才删。删码近不可逆,举证责任在发现方,**宁漏删不误删**。
- 弃用但仍 live 的旧路径(双源 SSOT)、注册表/反射僵尸、孤儿文件 → 同上证伪。
- 漂移红(超行/skip/白名单涨)、晋升/降级候选(扇入)→ **记待办,不自动改**。
产物:四档结论(逐条)+ 死码/双源/废弃清单(已删 or 放行登记:原因+可判定清除条件)+ 放行 pending(待批)。
