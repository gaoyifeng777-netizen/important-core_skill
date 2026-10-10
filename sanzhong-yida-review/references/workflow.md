# 工作流与角色交接

协议版本：1.0.0；适用包版本：1.0.0。本文件约定角色路由、来源登记和成果采用，不是独立调度引擎。角色输出以各自提示词为准，任务台账使用 [task-ledger.json](../templates/task-ledger.json)。

## 1. 运行顺序与范围

| 节点 | 主控动作 | 下游条件 |
|---|---|---|
| S0 建档 | 固定用户目标、终点、对象期间、工具与版本 | 技术编号由主控形成，不要求用户手填 |
| S1 资料预处理 | 独立调用 read_adjust，收取分类、范围、来源和缺口 | G1 记录真实可用范围、混合文件分派及限制；未处理依赖暂停 |
| S2 规则预处理 | 独立调用 base_rule，整理候选、冲突及目录对应建议 | G2 确认具体条款、来源版本、主体期间、参数及对应关系；候选不能自批 |
| S3 四路识别 | 向新上下文分别下发对应提示词及互斥白名单 | 不接收其他路成果、旧答案、判定规则或预设疑点；准备就绪的任务可并行 |
| S4 接收检查 | 留存原始输出与输入，运行四路提取校验 | 主控只登记、校验和转办，不补事实、不统一口径、不预并事项 |
| S5 判定 | 交付有效采用清单、完整原始成果、确认规则和获准来源 | rule_judge 形成关系、比较、控制判定及获准线索扫描 |
| S6 独立复核 | 新上下文核验待复核成果、依据、来源和遗漏 | 必需来源未核验不能 pass；已触发转控制的扫描也须覆盖 |
| S7 交付 | 依据有效采用清单整合结果、限制与证据索引 | 本次终点以用户授权为准；正式认定和定级由评价人员确认 |
| S8 结束评测 | 保存运行记录、真实失败与复核反馈 | RRSI 未配置时仅保存建议，不在正式任务中自动改规则或发布 |

G1/G2 可沿用明确覆盖当前版本和范围的既有真实确认，不重复索取；没有适用确认时不得以沉默、程序通过或候选状态替代。仅事实提取任务不因缺规则而阻塞获准提取，但须如实记录未执行的制度处理和判定环节。补件、跨会阅读、会外执行核查和总体反查均不自动扩大用户授权。

read_adjust 只接收 [material_sorting.md](../rules/material_sorting.md) 的中性分类内容；base_rule 只按本次授权接收中性 CONTROL 卡。LEAD、预设问题及他路成果不回灌资料分拣或四路。

## 2. 来源版本、hash 与阅读范围

### 2.1 source_manifest

台账 source_manifest 每项登记一个原件身份：

- `source_key`：原件身份唯一键；同名不等于同源，路径相同而内容变化也须登记新版本。
- `original`：`{path, version, sha256}`。version 保留实际原件版本，未载明或未取得为 null；sha256 由真实字节计算，未知为 null 并在 limitations 说明。
- `reading_artifacts`：每项 `{artifact_id, path, version, sha256, artifact_kind, origin_map}`。artifact_kind 为 original/crop/ocr/text_export；artifact_id 唯一。version 为实际阅读件版本，可用受控 OCR/转换批次标识，不冒充文件正式签发版本。
- `limitations`：来源身份、摘要、映射或可读性的限制数组。

原件直接阅读时也登记 reading_artifacts 的 original 行，路径、版本、hash 与原件一致。OCR 重做、裁切边界或转写内容变化，即使原件没变，也新增阅读件版本、artifact_id 和真实 hash，旧文件保留；原件版本不因此递增。没有创建并核验派生件，不预填“已生成”。

### 2.2 转换到角色输入

read_adjust.files.file_version **只指原件版本**。主控先将 assigned_scope.path 对应到 source_manifest 中实际阅读件，再形成四路 files：

| 四路输入 | 取值来源 |
|---|---|
| file_id / document_type | 已放行的 read_adjust 索引行，保持唯一 |
| path / assigned_scope | read_adjust.assigned_scope.path / .scope |
| version | 对应 reading_artifacts.version；不能无条件复制原件 file_version |
| origin_source | `{source_key, original_path, version}`，取原件身份及 original.version |
| origin_map | 本阅读件逐段到原件的真实定位映射 |

origin_map 每项为 `{derived_path, derived_location, source_key, original_path, original_version, original_location}`。同一派生件来自多个原件时，逐段保留各自身份及版本；hash 通过 source_manifest 与实际输入 path/version 精确对应。不凭派生页码猜原件页码。无法建立映射时先修复受影响分派，不能用原件路径替阅读件路径规避四路隔离。

四路输入继续使用 schema 1.1，files.path 与 assigned_scope 是阅读权限；origin_source/映射只供溯源。台账中的其他阅读件和成果不因存在索引就向识别者开放。每个角色保存完整输入副本，主控在 tasks 记录所用 artifact_id 和原件/阅读件摘要；若缺 hash，保存可核对副本并准确记录复现限制，不能伪称摘要已核验。

判定 source_files 每项保留 source_key、file_id、path、version、assigned_scope、origin_map、extraction_refs，并可附 `sha256`、`origin_source`。这里 version/sha256 对应实际打开的 path；origin_source 对应原件。一个原件有多个实际阅读版本时，判定来源清单为各阅读件分配独立 source_key，并以 origin_source 和 extraction_refs 连接上游，不能同键覆盖。复核用 allowed_scope 代 assigned_scope、path_or_attachment_id 代 path，并通过 judge_refs 记录 `(判定 run_id, 原 source_key)`。改字段名不改变授权范围。

base_rule 的 source_files.version 及 source_refs.version 同样对应实际阅读件；原件与派生件版本通过输入 origin_map 和 source_manifest 对应。正式制度版本、阅读件版本、候选规则版本及本次规则快照版本分别留存，不互相代填。

### 2.3 覆盖与连续引文

assigned_scope 是获准范围，processed_scope/read_scope 是实际处理范围；局部未见必须指出本项搜索范围，不能外推至未读页。四路 field_checks 可用 search_scope 明确局部范围；省略时按同 file_id 的 coverage.processed_scope，其为空才回落 assigned_scope。不同文字范围是否重叠、引文是否位于已读范围，仍需人工或独立复核；校验器不解析所有自然语言包含关系。

每条 evidence.quote、source_refs.quote 或 source_checks.quote 只保存一个连续原文片段。一项判断依赖第 2、4、6 行时，登记三条带各自 locator 的引用，不能拼为一条 quote、用换行冒充连续或用省略号补成不存在的原文。相同来源可重复出现，每条仍独立定位；未读/不可读无摘录时用 null。OCR 字符不确定必须回看获准原页或保留 unreadable/限制，不能仅因 OCR 文本可匹配便称原件已核验。

## 3. 判定和复核交接

1. base_rule 新候选均 pending。G2 后主控照录经确认条目、formal_rule_id、目录卡对应关系及 confirmation_ref，不代做语义匹配，也不把目录库写成整份已确认规则。
2. rule_judge 接收 logic、dictionary、rule_catalog、本次独立 rules 快照及各自版本，实际加载必需文件；不能把路径存在写成已读。通用逻辑、CONTROL 候选、正式要求及 LEAD 方法分开。
3. extraction_results 保存 agent_name、run_id、version、path、meeting_package_id；提交完整原始成果，不能只提交主控摘要。多个 run 的同名编号必须保留命名空间。
4. links、comparisons、decisions 由 rule_judge 产生。同计划下不同采购/支付事项可用 same_group 关联，保留各自 matter_id；same_group 不证明 same_matter、同次决定、累计义务或规避。
5. 每个获准事项×LEAD 方法登记 lead_scan。实际触发且转 CONTROL 时仍为 lead_found，linked_decision_ids 指向本判定 run 内同事项 decision；可不另造重复 lead。不将去重改写成 no_signal_in_scope，不把命中扫描数或关联次数当缺陷数。
6. quality_review 读取相同依据版本、有效采用清单、全部分派判定/线索/扫描及必需来源。复核即使 completed 也可以 return_for_revision；四路结构校验通过不能替代原文忠实度或业务复核。

## 4. 局部重跑与有效成果采用

supersedes_run_id 只说明修订来源，**不表示新 run 自动覆盖旧 run 全部成果**。原始输入、输出及旧复核全部保留。台账 `effective_results` 是当前交付采用清单，`invalidation_log` 是依赖失效记录；主控根据专业角色输出登记，不能据采用清单重写事实。

### 4.1 采用清单的最小结构

每个 effective_results 项含：`unit_id`（稳定业务检查单元）、`stage`、`scope`、`selected_refs`、`retained_refs`、`replaced_refs`、`dependency_refs`、`status`、`basis_ref`、`review_refs`。

- 所有结果引用采用 `{run_id, collection, ids}`，collection 是原成果数组名，ids 明列局部 ID；全量采用可用 `["all"]`，但与局部排除不能同时出现。范围不能只写“相关事项”。
- selected_refs 是当前新增或重新采用的结果；retained_refs 是仍有效的旧结果；replaced_refs 只留被替换历史，不进入当前汇总。每个单元的有效输入由前两项组成，彼此不重叠。
- dependency_refs 使用 `{kind, ref, version, sha256}`，指向实际采用的上游 run/单元/来源阅读件/规则/字典/逻辑。无需 hash 的逻辑引用可为 null；不得省略依赖实际版本。
- status 为 `pending`（尚未决定采用）、`effective`（本阶段可用）、`stale`（依赖改变待重做）。basis_ref 指向判定/复核的采用依据或用户实际决定，review_refs 指向仍有效的复核。effective 不自动表示业务最终认定或人工签认。

subject/record/item_index 不能跨 run 猜测对应；单条 record 重提后，不把新 value 拼入旧 record。事实单元边界不清或记录不可安全分割时扩大到该 subject/文件的完整重提范围，仍须在既有授权内；超出授权先登记请求。

### 4.2 依赖失效顺序

1. 事实错误：主控另建新上下文、新 run，只给获准原件和中性问题。旧答案、复核意见及期待字段值不传四路。
2. 判定者核对新旧事实及实际影响，返回受影响 links、comparisons、decisions、lead_scan、leads 和 coverage 单元；主控照录，不自行补事实或推断“不受影响”。
3. 原件/阅读件 hash、实际读范围、采用事实、规则、字典语义或逻辑改变时，沿已登记 dependency_refs 标记直接和传递依赖 stale。invalidation_log 每项记录 `{invalidation_id, changed_ref, affected_unit_ids, affected_review_refs, reason, disposition_ref}`；缺依赖信息时保持 pending/stale并请求专业核对，不能默认为旧结果有效。
4. 仅重判受影响范围。未受影响且有明确依据的旧单元可保留；新结果不存在的旧单元不得因整轮 supersedes 被删除，也不能因仍在旧文件内就继续当有效。
5. 独立复核核验受影响的新结果与采用边界。凡引用被替换事实、失效判定或变更依据的旧复核标 stale，不能移植旧 pass。新复核有缺口时保留对应状态。
6. S7 只汇总有效采用清单中的当前条目，核对覆盖分母、引用闭合、重复计数及未完成单元；stale/pending 单元作为明确限制，不隐藏或计为符合。满足本次终点后才结束。

例：仅重提事项 A 的金额限定，应明确 A 的金额比较及其依赖扫描/判定/复核失效；事项 B 是否保留须有独立依赖和专业核对依据。主控不能只把 latest_run 改成新值，更不能把全部旧结果或旧复核直接删除。

## 5. 版本和验证边界

| 组件 | 本包版本 |
|---|---|
| 包 / 工作流与台账协议 | 1.0.0 / 1.0.0 |
| 字典及字典指南 | 1.1；48 个事实字段，不新增字段 |
| 四路提示词 / 提取输出 schema | 1.2 / 1.1 |
| 通用判定逻辑 | 1.2 |
| rule_judge 提示词 / 输出 schema | 1.3 / 1.3 |
| quality_review 提示词 / 输出 schema | 1.3 / 1.0 |
| master_control 提示词 | 1.4 |
| read_adjust 提示词 / 输出 schema | 1.2.1 / 1.0 |
| base_rule 提示词 / 输出 schema | 0.3.0 / 1.0.0 |
| 分类参考 / 规则目录 | 按各文件实际版本冻结，不能用包版本代填 |

字典 1.1 澄清金额限定和条件语义；四路 schema 1.1 兼容补充可选 search_scope、request_type、record_ids，不增加事实值字段。判定 schema 1.3 新增 links.relation=same_group 与 lead_scan.linked_decision_ids。旧输出保留原版本，不静默迁移、重标版本或冒充新字典提取；需要重新识别时另开运行。

包内四路提取校验器检查结构、枚举、引用和有限一致性；不能证明原文语义、业务正确、自然语言范围包含、硬隔离或真实执行。判定/复核遵循输出契约及独立业务复核，不因缺完整自动校验引擎而伪称“程序全通过”。本包没有模型调用、自动 OCR、强制文件沙箱或完整 RRSI 发布执行器；配置和能力须按实际运行记录。
