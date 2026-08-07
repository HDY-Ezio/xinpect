# 煋鉴 Xinpect 变更日志

## [v4.6.0] - 2026-08-06

### 新引擎全面接通

**核心修复：CLI scan 子命令底层从旧引擎切换到 RuleRunner 新引擎，8 大脑架构 + 1949 条可执行规则真正落地。**

此前 v4.5 的 CLI 只是给旧引擎套了壳，新引擎 2000+ 条规则从未被用户实际使用。v4.6 彻底打通。

**引擎升级：**
- 默认引擎切换为 `new`（RuleRunner 新引擎），旧引擎通过 `--engine-mode legacy` 保留
- 1949 条可执行规则全量运行：1142 正则 + 500 Semgrep + 307 语义
- 8 大脑并行扫描架构真正生效

**质量修复：**
- 修复语义规则传参 bug：307 条语义规则之前加载了但未传入扫描器，现已正确接通
- 清理 1082 条纯描述参考规则到 `rules/_reference/semantic/`，规则数量口径真实可信
- 修复 6 组重复规则 ID，全部规则 ID 唯一
- Semgrep 未安装时醒目提示，不再静默跳过

**向后兼容：**
- `--engine-mode legacy` 完全走旧 `qa_framework.py` 主流程
- 直接 `python qa_framework.py --path ...` 调用方式不变
- `hybrid` 模式可对比新旧引擎结果

---

## [v4.5.0] - 2026-08-06

### CLI 子命令化改造

将原本扁平的 20+ 参数 CLI 全面重构为子命令架构，专业感和易用性大幅提升。零行为变更，旧调用方式（`python qa_framework.py ...`）完全兼容。

**新增子命令：**

- `xinpect scan [path]` — 扫描项目（默认子命令，支持直接传路径）
- `xinpect init [path]` — 在目标目录生成 `.xinpectrc.json` 配置模板
- `xinpect rules [keyword]` — 查看规则列表，支持按语言/级别/类别筛选和关键词搜索
- `xinpect config [--config file]` — 查看/校验当前生效配置
- `xinpect version` — 输出版本号和发布日期

**体验优化：**

- 彩色输出：高危红 / 中危黄 / 低危蓝 / 建议灰 / 通过绿，自动识别终端是否支持颜色
- ASCII 表格：规则列表、配置展示均使用带边框的表格
- Banner 标题：扫描启动时显示品牌标识和扫描参数
- 进度条组件：`ProgressPrinter`（轻量零依赖，不依赖 tqdm）
- 退出码语义化：0=成功，1=有高危问题，2=执行错误
- 向后兼容：不传子命令时自动走 scan，保留所有旧参数

**新增文件：**
- `cli/cli.py` — 子命令 CLI 主入口（560 行）
- `cli/utils.py` — 彩色输出 / 进度条 / ASCII 表格 / 汇总表渲染（450 行）
- `xinpect` — 根目录可执行入口脚本

---

## [v4.4.2] - 2026-08-06

### 前端 AST 引擎模块拆分与架构优化

将 v4.4.0 新增的前端 JS/TS AST 规则引擎从单文件（1098 行）拆分为 8 个职责清晰的小模块，解决「过大文件」和「过深嵌套」两项中危，自扫描 100 分满分。

**3S 架构分层（骨架→血肉→皮肤，零行为变更）：**

- **骨架层（依赖单例）**：`js_ast_babel.js` - babel 依赖初始化（27 行）
- **工具层（纯函数）**：
  - `js_ast_utils.js` - 基础工具（位置/makeIssue/模式提取，96 行）
  - `js_ast_analysis.js` - 分析辅助（复杂度判断/变量声明记录，65 行）
  - `js_ast_rule_defs.js` - 16 条规则元数据（112 行）
- **业务层（核心逻辑）**：
  - `js_ast_hook_utils.js` - Hook 识别 + 闭包分析 + setter 收集（363 行）
  - `js_ast_hook_rules.js` - Hook 规则检查函数（161 行）
  - `js_ast_rules_runner.js` - 规则执行器主函数（约 400 行）
- **入口层（门面）**：`js_ast_rules_engine.js` - 对外聚合导出（32 行）

**过深嵌套优化策略（从 30 处降至 0）：**

- 卫语句早返回替代多层 if 嵌套
- 大函数拆独立子函数（`_trackHookDeclarations` / `_recordImportDeclarations` / `_trackIdentifierUsage` / `_checkEmptyBlocks` / `_checkTsIgnoreComments`）
- 长条件判断改为 Set 查表（`_EMPTY_BLOCK_PARENTS`）

**验证结果**：54 单测全过，自扫描 100/100 分，高危 0，中危 0

---

## [v4.4.1] - 2026-08-06

### 安全审计模块导入 Bug 修复

修复 v4.4.0 发布后发现的安全审计模块运行时崩溃问题，根因是 docstring 内含 import 语句导致循环导入链断裂。

- **根因**：`legacy/checks/mod3_security.py` 文件顶部的 `from qa_framework import ...` 写在三引号 docstring 内部，实际从未执行；模块内函数引用 `_HAS_ARCH_DETECTOR` 时报 `name '_HAS_ARCH_DETECTOR' is not defined`
- **修复**：将 import 移至 docstring 外部，并采用延迟导入模式（`_ensure_imports()` 函数 + 包装函数），彻底避免 `qa_framework → legacy.modules → legacy.checks → qa_framework` 循环导入
- **影响**：v4.4.0 全量扫描时安全审计模块 3.0 异常，直接扣 1 高危；修复后自扫描 97 分，高危 0

---

## [v4.4.0] - 2026-08-06

### 前端 JS/TS AST 引擎（基础设施）

新增前端 AST 规则引擎，复用 Python 调度 + Node.js 执行的混合架构，一次遍历跑所有规则，规则总数 +16 条（54 单测全过）。

- **React Hooks 规则（8 条）**：useEffect 依赖不全、useState 命名不规范、hooks 顺序错误、useCallback/useMemo 误用、无限循环风险等
- **TypeScript 规则（3 条）**：any 滥用、未使用导入、接口命名规范
- **JS 质量规则（5 条）**：console.log 残留、eval 调用、相等运算符误用、未使用变量、嵌套回调地狱
- 新增文件：`rules/web/ast_rules.py`、`core/js_ast_rules_engine.js`、`tests/test_web_ast_rules.py`
- 修改文件：`core/ast_bridge.js`、`core/js_ast_analyzer.py`、`rules/web/__init__.py`

### Python 安全 AST 补强（对齐 bandit）

新增 18 条 Python 安全 AST 规则，硬编码凭据 + 危险函数双维度覆盖，61 单测全过，误报率 0%。

- **硬编码凭据（7 条，PYAST052-058）**：API Key / 密码 / 令牌 / 私钥 / 数据库连接串 / AWS 密钥 / 通用高熵字符串
- **危险函数（11 条，PYAST059-069）**：eval/exec/compile、pickle 反序列化、shell 注入、yaml 不安全加载、md5/sha1 弱哈希、ssl 跳过验证、随机数安全等
- 新增文件：`rules/python/ast_deep/hardcoded_secrets.py`、`rules/python/ast_deep/dangerous_functions.py`、`tests/test_security_ast_rules.py`
- 修改文件：`rules/python/ast_deep/__init__.py`

### 批量降误报治理

构建误报治理基础设施，对 8 个 common 规则文件完成字符串匹配层的误报治理，全量扫描中危从 5 个降至 0 个。

- 基础设施：`core/code_context_utils.py`（docstring 范围识别 / RULES 列表范围识别 / search_in_code 统一入口）
- 五层防护：跳过注释 / docstring / RULES 列表定义 / 字符串字面量内部 / 行内注释
- 已治理文件：injection / crypto / auth / misc_security / code_quality / dead_code_rules / http_security_config

### 验证结果
- 全量自扫描：85 分，中危 0 个
- 新增单测：115 个全部通过

---

## [v4.3.0] - 2026-08-05

### 重大升级：3S 架构全面重构

本轮是煋鉴历史上最大规模的一次内部重构，引入 **骨架(Skeleton) → 血肉(Substance) → 皮肤(Skin)** 三层架构，代码可维护性大幅提升，对外行为零变更。

#### 骨架层（Skeleton）
- `qa_framework.py` 从 11002 行精简到 1362 行（-88%）
- 拆分出 `core/` 子包：report / ai_enhancer / cost / knowledge / rule_loader / rule_health / rule_effectiveness / scan_analyzer / feedback_collector
- 新增 `legacy/` 目录承载存量 checks/ 和 modules/，通过全局符号注入解决循环导入
- 52 项 hybrid 模式全量检查全部通过

#### 血肉层（Substance）
- 12 个大文件拆分为 31 个子文件，全部 <800 行
- 规则总数保持 1111 条不变（零行为变更）
- 按大脑维度归类：安全 / 质量 / 性能 / 可读性 / 可维护性 / 规范性 / 配置 / 文档 / 测试 / Git / WXML / LLM
- 旧文件已清理，无 bak 残留

#### 皮肤层（Skin）
- `core/report/` 重构为 themes/ + components/ + page_templates/ 三层结构
- 主题系统：内置 light / dark 两套主题，支持自定义扩展
- 组件系统：8 个可复用组件（Header / Summary / IssueList / ScoreCard / RadarChart / TrendChart / Footer / Badge）
- 页面模板：2 套（标准报告 / 极简报告），支持自定义模板
- 向后兼容：原 import 路径全部保留，外部调用无感

### 中危误报修复
- **TODO 自指误报**：新增 `_is_line_self_referential()`，排除规则代码自身对 TODO 的检测
- **硬编码自指误报**：新增 `_find_python_docstring_ranges()`，跳过 docstring 和字符串字面量内部的匹配
- **Python 常量误判**：NAME-004 排除赋值右侧以 `[` `{` `(` 开头的行（列表/字典/元组/集合）
- 验证：三个规则文件扫自身均 0 中危

---

## [v3.0.0] - 2026-08-04

### 新增：生态闭环机制（第6层）

煋鉴从"检测工具"升级为"会学习的质检系统"，新增三大反馈闭环模块：

#### 1. 规则有效性追踪器 (Rule Effectiveness Tracker)
- 文件: `core/rule_effectiveness.py`
- 自动记录每次扫描中各规则的触发情况（JSONL格式）
- 计算规则有效性综合评分（触发频率 × 文件覆盖面 × 项目覆盖面）
- 识别僵尸规则（长期不触发的候选淘汰规则）
- 新命令: `python3 qa_framework.py rule-effectiveness [days]`

#### 2. 扫描历史分析器 (Scan History Analyzer)
- 文件: `core/scan_analyzer.py`
- 解析历史QA报告，提取评分、问题数、类别分布等趋势数据
- 识别改善/恶化的质量类别
- 追踪长期未解决问题 vs 已解决问题
- 新命令: `python3 qa_framework.py scan-trend`

#### 3. 用户反馈收集器 (Feedback Collector)
- 文件: `core/feedback_collector.py`
- 支持记录误报、确认bug、忽略统计
- 所有数据本地存储，不自动上传
- 支持导出匿名反馈数据（仅rule_id + count，不含代码/路径）
- 新命令: `python3 qa_framework.py feedback-summary`

#### 技术细节
- 扫描完成后自动记录规则触发数据（hook in main()）
- 三个新模块均位于 `core/` 目录
- `qa_framework.py` 新增子命令拦截机制（_handle_ecosystem_command）
- 备份文件后缀: .bak_v300
- 不影响现有 rules/ 目录（其他子agent的工作）

---

## [v3.0.0] - 2026-08-04

### 重大升级：规则自管理子系统

从纯规则扫描进化到规则自管理，煋鉴现在能自动评估和优化自身的规则质量。

#### 新增：规则保鲜机制 (Rule Freshness)
- core/rule_health.py 新增 RuleHealthChecker 类
- 扫描 output/ 目录下的历史扫描报告（qa_report_*.md）
- 统计每条规则在最近N次扫描中的触发次数
- 超过90天未触发的规则标记为"过期"(stale)
- 从未触发过的规则标记为"死亡"(dead)
- 检查规则JSON中 references 字段的URL是否可达（urllib，5秒超时）
- 计算健康度分数 = (活跃规则数 / 总规则数) * 100

#### 新增：规则冲突检测 (Rule Conflict Detection)
- core/rule_health.py 新增 RuleConflictDetector 类
- 检测重复的 check_id（同一ID被多个文件定义）
- 检测 file_pattern 高度重叠的规则对（Jaccard相似度>=80%）
- 检测安全规则 vs 性能规则的潜在建议矛盾

#### 新增：CLI子命令 rule-health
- python3 qa_framework.py rule-health [project_path]
- 输出规则健康度总览（活跃/过期/死亡/链接失效统计）
- 输出冲突检测结果（ID重复/建议矛盾/文件模式重叠）
- 自动生成Markdown格式的详细报告到 output/ 目录

#### 技术细节
- 健康度评分采用扣分制：基础分=活跃率*100，每条失效链接扣0.5分
- 文件模式重叠检测提取 *.ext 扩展名计算Jaccard相似度
- 矛盾检测基于安全关键词 vs 性能关键词在同类文件模式上的交叉
- 所有检测支持Python规则和JSON规则两种格式

---



## [v2.10.0] - 2026-08-04

### 新增依赖供应链安全 + CI/CD管道安全规则（+35条，总计3285条）

| 方向 | 目录 | 规则数 | 前缀 | 覆盖范围 |
|------|------|--------|------|----------|
| 依赖供应链攻击检测 | supply_chain/ | 20 | SC-001~020 | 拼写劫持包名、恶意lifecycle脚本、非官方registry、版本锁定缺失、git依赖、scope伪造、废弃包、HTTP明文拉取、Unicode混淆包名 |
| CI/CD管道安全 | ci_cd/ | 15 | CICD-001~015 | Actions非固定版本、硬编码密钥、sudo权限过大、latest标签、依赖未校验、curl\|sh、缓存投毒、回滚缺失、TLS禁用、PR write权限 |

### 技术细节
- supply_chain_rules.json: 20条规则，brain2，覆盖拼写劫持/恶意脚本/非官方源/版本锁定/废弃包/编码混淆
- ci_cd_rules.json: 15条规则，brain7，覆盖Actions安全/密钥管理/Docker/缓存/部署/权限
- 所有规则pattern通过re.compile验证（MULTILINE | IGNORECASE模式）
- 新增 __init__.py 模块文件
- 规则加载器自动发现新目录，无需代码变更

---

## [v2.9.8] - 2026-08-04

### 新增6大盲区方向规则（+125条，总计3250条）

| 方向 | 目录 | 规则数 | 前缀 | 覆盖范围 |
|------|------|--------|------|----------|
| 异步/并发问题检测 | async_concurrency/ | 25 | ASYNC-001~025 | async/await遗漏、Promise未catch、事件循环阻塞、竞态条件、死锁、资源泄漏 |
| 数据流完整性 | data_flow/ | 20 | DF-001~020 | API返回值变更未同步、ORM/Schema不同步、SQL注入、类型断言风险、序列化不一致 |
| 错误处理质量 | error_quality/ | 20 | EQ-001~020 | 假处理catch、错误信息泄露（路径/堆栈/SQL）、无退避重试、过宽catch |
| 依赖链安全 | dep_chain/ | 20 | DEP-CHAIN-001~020 | 高危CVE版本、废弃依赖、GPL传染风险、lock文件缺失、非官方registry |
| 配置/部署完整性 | config_deploy/ | 20 | CD-001~020 | 环境变量无默认值、DEBUG未关、Dockerfile安全、K8s privileged、CORS宽松 |
| 业务逻辑安全 | biz_logic/ | 20 | BIZ-001~020 | 浮点金额计算、IDOR越权、幂等性缺失、频率限制缺失、CSRF缺失 |

### 技术细节
- 所有规则pattern通过re.compile验证
- 所有JSON文件通过json.load验证
- 规则加载器已支持JSON自动发现

---


## [v2.1.0] - 2026-08-03

### 重大变更：8大脑定义最终确认

#### 定义对齐
8大脑定义统一为最终版本，清理所有旧版引用：

| 大脑 | 功能 | 层级 | 规则数 |
|------|------|------|--------|
| Brain 1 | 规则引擎（含UI/UX） | 免费 | 938 |
| Brain 2 | 安全扫描 | 免费 | 200 |
| Brain 3 | AI语义分析（静态规则兜底+LLM增强） | 免费 | 200 |
| Brain 4 | 性能分析 | 付费 | 200 |
| Brain 5 | 依赖审计 | 付费 | 200 |
| Brain 6 | 代码质量 | 付费 | 200 |
| Brain 7 | 架构合规 | 付费 | 200 |

**总计：2138条规则（去重后）**

#### 目录重命名
- `rules/brain2_security/` — 安全扫描规则（11个JSON文件）
- `rules/brain3_semantic/` — AI语义分析静态规则（8个JSON文件，SEM-001~SEM-200）
- `rules/brain4_performance/` — 性能分析规则（9个JSON文件，含frontend/database/caching/network/build）
- `rules/brain5_deps/` — 依赖审计规则（4个JSON文件）
- `rules/brain6_code_quality/` — 代码质量规则（7个JSON文件）
- `rules/brain7_architecture/` — 架构合规规则

#### 代码修复
- `brains/__init__.py`：_BRAIN_METADATA和_ensure_loaded对齐新文件名
- `brains/cli.py`：pro_names字典更新，免费版降级逻辑改为B1+B2+B3
- `core/ai_enhancer.py`：brain_focus字典对齐新定义
- `core/cost_manager.py`：brain名称映射对齐
- `core/license_gate.py`：brain_names字典对齐
- `core/result_aggregator.py`：priority_order字典对齐
- `core/task_contract.py`：所有7个TaskContract定义更新
- `rules/brain2_security/*.json`：metadata的brain字段修正
- `rules/brain5_deps/*.json`：metadata的brain字段修正

#### 设计决策
- **免费版 = B1+B2+B3**：B3采用静态规则兜底+LLM增强双模式设计
- **覆盖率优先**：规则数量不是目标，全覆盖才是。200条不够就加，冗余就减
- **Brain 3双模式**：无AI时用静态规则兜底，有AI时LLM增强（用户自带Key，主人零成本）
- **英文名锁定**：Xinpect

#### 统计工具
- 新增 `rules/count_rules.py`：统一计数脚本，支持 --brief / --json / --coverage 模式
- 计数口径：JSON rules数组 + Python RULES列表，按规则ID全局去重

---

## [v2.0.0] - 2026-08-02

### 重大变更：章鱼架构 v2.0

#### 新增
- **Brain6 安全漏洞扫描引擎** (`core/brain6_security_engine.py`)：17项安全检查，含CWE编号
- **Brain7 架构合规引擎** (`core/brain7_architecture_engine.py`)：15项架构检查
- **Brain3 性能分析引擎** (`core/brain3_perf_engine.py`)：35项性能检查（原brain3_lite重构为完整版）
- **Brain4 依赖审计引擎** (`core/brain4_dep_engine.py`)：25+项依赖检查，内置CVE库
- **Brain5 UI/UX审查引擎** (`core/brain5_ui_engine.py`)：35项UI检查（原brain5_basic重构为完整版）
- **8个协调模块**：task_contract, result_aggregator, collaboration_modes, checkpoint_manager, message_bus, cost_manager, adaptive_router, knowledge_base
- **注册表模块**：registry.py，统一管理大脑注册与生命周期

#### 重构
- `brain3_lite` → `brain3_perf_engine`：从轻量版升级为完整性能分析引擎，检查项从8项扩展到35项
- `brain5_basic` → `brain5_ui_engine`：从基础版升级为完整UI/UX审查引擎，检查项从12项扩展到35项
- 大脑接口统一为 `BaseBrain` 抽象类，所有大脑实现同一标准接口
- 中枢调度从"大脑"降级为"神经中枢"，只做路由和聚合

#### 迁移指南
如果你是从 v1.x 升级：
1. `brain3_lite` 已被 `brain3_perf_engine` 替代，旧文件保留但不再使用
2. `brain5_basic` 已被 `brain5_ui_engine` 替代，旧文件保留但不再使用
3. 所有大脑调用接口不变，通过注册表自动路由到新引擎
4. 新增的 Brain6/7 为可选模块，不启用不影响现有功能

### 文档更新
- SKILL.md：更新为七大脑架构描述
- README.md：更新为 v2.0 + 章鱼架构说明
- 本文件（CHANGELOG_v2.md）：新增迁移说明

## v2.9.6 (2026-08-04)
### 🌐 多平台规则全覆盖
- **新增 Web 安全规则**（WEB-SEC-001~020）：CSP、CORS、Cookie安全、XSS防护、WebSocket安全等 20 条
- **新增 Web 性能规则**（WEB-PERF-001~015）：懒加载、CDN、代码分割、资源预加载等 15 条
- **新增 Electron 安全规则**（ELN-SEC-001~020）：nodeIntegration、IPC通信、沙箱隔离等 20 条
- **新增 iOS 安全专项**（IOS-SEC-001~020）：权限声明、ATS、Keychain、深度链接等 20 条
- **新增 Android 安全专项**（AND-SEC-001~020）：权限模型、Intent安全、ContentProvider等 20 条
- **新增 React Native 规则**（RN-SEC-001~015）：Bridge安全、AsyncStorage、原生模块等 15 条
- **新增 Flutter 规则**（FLT-SEC-001~015）：Platform Channel、热更新、Isolate安全等 15 条
- **总计新增 125 条规则**，总规则数达到 **3125 条**

### 🔧 架构优化
- 新增 JSON 规则加载器（rule_loader.py），支持静态正则规则文件自动发现与加载
- 新增 react_native/、flutter/ 规则目录

## v2.9.7 (2026-08-04)
### 🔧 自扫问题修复
- **ast_bridge.js 拆分**: 520行 → 主文件112行 + 3个子模块（ast_helpers/js_parser/wxml_parser）
- **硬编码误报标注**: 规则生成脚本中的示例代码添加 `[示例代码]` 注释
- **魔法数字消除**: ui_checks.py 提取11个命名常量
- **测试覆盖增强**: 新增 tests/test_core_modules.py（11个测试用例，覆盖knowledge_base/trend_tracker/incremental/cache_manager）
- **扫描评分**: 98分 → 100分（中危清零）

## v2.9.9 (2026-08-04)
### 🔒 安全加固：影子实现清除 + 检测规则
- **清除旧版完整实现**：将Brain4/5/6/8的旧版本地完整实现（共5个文件，271KB）移出分发包含
  - brain4_dep_engine.py (22KB) → 备份
  - brain4_deps.py (72KB) → 备份
  - brain5_ui.py (91KB) → 备份
  - brain5_ui_engine.py (16KB) → 备份
  - brain6_performance.py (16KB) → 备份
  - brain8_extra_analyzers.py (91KB) → 备份
- **新增影子实现检测规则** (SEC-SHADOW-001~008)：
  - 未注册但含register装饰器的文件
  - 单文件超1000行（可能含完整引擎）
  - 同一Brain ID被多文件注册
  - 备份文件残留
  - PRO大脑本地完整实现
  - 硬编码端口暴露
  - 死代码可调用入口
  - 测试桩/mock残留
- PRO大脑(B4-B8)包内现在只有薄客户端(5-6KB)，完整逻辑仅在服务端

## v3.0.1 (2026-08-04) - 架构归一化

### 新增
- **15条架构卫生规则** (ARCH-HYG-001~015)：重复注册检测/临时文件残留/孤儿模块/目录命名一致性/废弃代码/编码不一致/__pycache__残留/模块ID不匹配/过大文件/循环依赖/空模块/测试混源码/硬编码地址/重复定义/异常吞没
- 架构卫生规则合入Brain 7（架构审查）

### 修复
- **Brain 2重复注册**：brain2_security_engine.py(345行完整实现)替换为薄客户端，合并至brain2_ai_engine.py统一入口
- **Brain 3重复注册**：brain3_perf.py(2094行完整实现)替换为Helper类，去除重复@register_brain("3")
- **清理.bak文件**：rules/(6个) + core/(9个) + root/(11个) = 26个备份文件全部清理
- **清理__pycache__**：全项目清除
- 项目体积从11M降至8.9M

### 架构优化
- 8个Brain各有且仅有1个@register_brain注册点
- 所有旧版完整实现备份至/opt/starwang/xinpect_backup/normalization_v300/
- 分发包无.bak/__pycache__/冗余文件

---

## v3.0.1 (2026-08-04) - 架构归一化 + 重复ID清零

### 架构归一化
- **Brain注册统一**：8个Brain各有且仅有1个@register_brain注册点
  - Brain 2：纯安全扫描（合并brain2_security_engine→brain2_ai_engine）
  - Brain 3：纯AI语义（brain3_perf.py降为Helper，去除重复注册）
- **目录归属调整**：
  - agent/ → security/agent_llm/ (Brain 2)
  - ai_code_check/ → common/ai_quality/ (Brain 1)
  - miniprogram/ → common/miniprogram/ (Brain 1)
  - python_deep/ → brain6_code_quality/python_deep/ (Brain 6)
  - skill/ → common/skill/ (Brain 1)
  - javascript/ → 归档(非规则文件)
- **RuleLoader递归扫描**：支持子目录规则自动发现
- **清理.bak文件26个 + __pycache__全清**
- 项目体积 11M → 8.9M

### 重复ID清零
- 修复200对重复规则ID（SEC-001~200在security和semgrep中重复）
- 重复ID加后缀区分（如SEC-001-semg）
- 修复后重复ID: 0

### 新增
- 15条架构卫生规则 (ARCH-HYG-001~015)
