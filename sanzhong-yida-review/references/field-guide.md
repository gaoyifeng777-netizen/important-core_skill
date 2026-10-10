# 字段的业务含义与填写分工

这些英文词是资料和成果的标签，类似底稿编号、文件索引和处理状态，不是需要用户编写的程序。编号用于“找得到”，状态用于“知道处理到哪一步”；二者都不能代替证据或人工决定。

## 用户主要需要提供什么

用户提供评价对象、业务期间、资料目录、任务终点及具体业务规则，并对需人工处理的资料和规则作决定。规则可以先用自然语言编写。主控和专业角色负责生成内部编号、整理字段、补充来源索引；未知事实不得为了填表而补造。

## 与规则有关的字段

| 字段 | 中文含义 | 由谁形成 | 使用边界 |
|---|---|---|---|
| rule_id | 一条规则的编号，例如 RULE-001 | base_rule 或主控编排，后续稳定沿用 | 编号不代表规则正确、有效或批准 |
| rule_candidates | 从制度中整理出的规则候选集合 | base_rule | 供编写与确认正式规则使用，不能直接覆盖正式规则 md |
| match_state | 规则材料的匹配情况：clear / ambiguous / conflicting | base_rule | 分别表示明确、含糊、冲突；clear 仍不表示人工已确认 |
| confirmation_status | 人工处理状态：pending / confirmed / rejected | 根据真实人工记录由主控登记 | 待确认 / 已确认 / 不采用；不能由 Agent 自批 |
| confirmation_ref | 人工确认记录在哪里 | 主控 | 需能对应具体规则、版本和范围，不是笼统“用户同意做 Skill” |
| rule_version | 单条规则版本 | 主控按实际变更登记 | 用于保留规则变更历史 |
| rules_version | 整份规则包版本 | 主控 | 与单条规则版本、制度原件版本分别保存 |

旧图稿中的 **rule_confirm** 原意是“比对后明确、未发现冲突的规则集合”，而后来的人工确认又使用“确认”一词，容易误解。整合版不再用这个名称作正式输出字段：旧的明确候选转为 rule_candidates + match_state=clear；没有对应人工记录时 confirmation_status 仍是 pending。

旧的 rule_tobeconfirm1、rule_tobeconfirm2 统一整理到 comparisons 和 requests，保存具体冲突、歧义、来源及所需人工处理，不丢失原来两类比对信息。历史文件保留原样，不用字段改名伪造已经完成的确认。

## 与资料和任务有关的字段

| 字段 | 中文含义 | 由谁处理 |
|---|---|---|
| project_task_id / task_id | 总任务编号 / 子任务编号 | 主控生成 |
| run_id | 某个子任务“这一次运行”的编号；重跑换新号 | 主控生成 |
| meeting_package_id | 一个会议资料包的编号 | 主控登记；归属不明保留待确认 |
| file_id | 某份获准阅读资料的编号 | 预处理登记、主控确认 |
| source_key | 在本次来源清单中唯一的原件或来源标识 | 主控维护，防止同名资料混淆 |
| subject_ref | 识别角色自己整理的议题或文档上下文编号 | 识别 Agent 生成，不等于公司正式事项号 |
| record_id | 一条提取事实的编号 | 识别 Agent 生成；跨角色引用要连同 run_id |
| decision_id / lead_id | 判定项编号 / 待核查线索编号 | 判定 Agent 生成 |
| input_snapshot | 本次输入的留存副本 | 相应角色输出，主控保存输入文件和版本 |

例如，两次运行都可能有 record_id=R01；它们不是同一事实。完整引用分别是“运行甲的 R01”和“运行乙的 R01”。source_key 与上游 (run_id, file_id) 的映射也是为避免这种混淆，并非要求用户手工维护多套账。

## 三种状态不要混为一谈

| 层次 | 回答的问题 | 常用取值 |
|---|---|---|
| 任务执行状态 status | 分派的工作完成到哪一步 | completed 已处理完；partial 部分完成；blocked 前提受阻；failed 执行故障 |
| 业务判定 result | 现有规则和证据支持什么判断 | 符合、存在偏差、证据不足、不适用、规则待确认 |
| 复核意见 review_disposition | 待复核成果可否在本次范围使用 | pass、return_for_revision、limited、not_reviewed |

一项工作可以 completed，同时业务结果为“证据不足”；复核也可以 completed，同时要求退回修改。每个角色关于状态的具体边界以其提示词为准。状态和编号均不能证明企业内控无问题。


## 字段字典和比较

`tags`是分类；`values.items.field`是具体属性；`raw`是原文值；`normalized`是允许的格式整理值；`qualifiers`是比较时不可丢的限定；`evidence_indexes`指向同记录证据。完整定义与示例见[四路字段字典与串联比较](四路字段字典与串联比较.md)。

`links`是判定者确认的材料/事项关联；`comparisons`是字段比较底稿。二者由判定者产生，不交给并行识别者借鉴。`item_index`只是数组内0起始位置，不需用户编号码。`logic`固定通用判定方法，`dictionary`固定字段定义；均不代替正式业务规则或人工确认。

## 规则库与线索检查字段

规则目录编号Cxx标记一张控制测试卡；本次正式判定rule_id指向经确认的企业/适用外部规则，主控保留二者映射。Lxx标记一项线索分析方法，lead_scan.rule_id使用该方法号，不等于公司制度编号。编号格式用于追溯，用户主要维护中文规则内容。

lead_scope是本次任务是否以及对哪些事项开展线索分析的范围；lead_scan记每事项/方法是否实际检查及其状态；leads保存真实形成的线索。程序符合的事项仍可能有值得补证的线索，未形成线索也必须保留检查范围和不足。方法启用不代表公司义务已获确认。

## 容易混淆的证据字段

| 字段 | 正确含义与边界 |
|---|---|
| amount_basis / scope_raw / stage | 金额性质 / 项目或标的范围 / 业务阶段。原文“QL-A1项目拟申请投资上限120万元”分别是“投资上限”/“QL-A1项目”/requested，不互相代填。 |
| condition.content | 原文明确约束审议、批准或实施的条件；普通同意上会意见、测算不确定性分别保留在本角色意见或分析字段。 |
| file.version / origin_source.version | 实际阅读件版本 / 原件版本；OCR重做不等于原件变更。二者hash和定位分别登记于source_manifest。 |
| field_checks.search_scope | 本项实际搜索范围；局部已读未见与其他部分未读可以并存，不能将局部结果外推全文件。 |
| links.relation=same_group | 共同计划或需求组下的不同事项关系，仍保留各自matter_id；不代表same_matter。 |
| lead_scan.linked_decision_ids | 已触发并转入CONTROL的扫描所关联判定；state仍为lead_found，避免重复输出同一线索或计缺陷。 |
| effective_results / invalidation_log | 当前成果采用清单 / 上游变更导致的依赖失效记录；不能用latest_run替代局部采用和旧复核重做。 |

source_checks.quote 每条必须是一个连续原文片段，不连续行分条登记。主控按 [工作流](workflow.md) 保存身份、版本、hash、映射和采用记录；它不替专业角色补事实、判定关联或选定规则。完整字段定义见 [fact_dictionary.json](fact_dictionary.json)，角色输出版本见工作流版本表。
