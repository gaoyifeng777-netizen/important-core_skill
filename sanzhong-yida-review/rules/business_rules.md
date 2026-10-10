# “三重一大”控制规则候选与业务线索检查库

规则库版本：1.0.0；发布日期：2026-10-10；字段字典版本以 references/fact_dictionary.json 为准（48个键）；性质：正式发布的控制测试方法与业务线索规则库。适用角色为 base_rule、rule_judge、quality_review。卡片的条件分支、计算式和材料触发是测试方法，不是制度原文。具体企业的权限、阈值、时限、表决比例和适用范围，须依据本次任务的真实来源及确认记录确定。

本库同时服务两个目的：按已确认要求测试控制是否执行；从决策材料主动识别值得延伸了解的业务控制线索。即使程序检查为“符合”，仍须完成本次范围内适用的线索扫描。每个事项都检查，不要求每个事项都有线索，不把“未形成线索”解释为经营无风险。

## 一、启停、身份与两个人工闸门

| 类型 | 本版状态与启用方式 | 输出及边界 |
|---|---|---|
| CONTROL 控制规则候选 | C01—C16：status=candidate、confirmation_status=pending、enabled=false。base_rule整理实际来源、G2人工确认并建立正式规则映射后才执行 | decisions使用“符合 / 存在偏差 / 证据不足 / 不适用 / 规则待确认”。候选卡、测试经验、案例和编制授权都不代表客户义务已确认，不自动定缺陷等级 |
| LEAD 业务线索检查 | L01—L11：status=analytic_method、method_status=designed、enabled=true。只有主控任务明确包含线索分析且材料经G1获准才扫描；enabled仅表示方法可供选用 | 每事项逐卡形成lead_scan；有材料触发时形成leads。不套五种业务结果，不推定违规、损失、利益输送或动机 |

卡片id与catalog_id同值，是本库稳定目录号。CONTROL的formal_rule_id是base_rule整理并经G2确认的本次正式规则号，与C01等目录号、T01等通用方法号不同。一个目录卡可以映射不同主体/期间的多条正式规则，须分别建立检查单元。

- decisions.rule_id及rule_basis.rule_id使用真实formal_rule_id，保留正式规则版本、原件source_key/source_file_id/locator/confirmation_ref。目录号通过明确映射追溯，不代替来源。仅纳入待确认清单且正式号未知时保持null，说明对应目录号。
- LEAD不设confirmation_status或formal_rule_id，避免把方法采用与企业义务确认混淆。lead_scan.rule_id及leads.rule_ids使用L01等方法号；rule_version固定本次卡片版本。
- 规则包、单卡、正式规则、原件和字典的版本分别保存；更新本库不自动修改运行中的正式规则。

本文件是rule_catalog方法目录，与rules指向的本次正式规则快照分开输入。CONTROL的candidate/pending/enabled=false是未绑定客户时的目录默认值。base_rule提出目录与正式规则的专业映射建议，经G2确认后，在本次正式规则快照中明确启用相应formal_rule_id；主控仅照录映射、版本及确认记录，原目录保持不变。judge不能因原目录默认false跳过本次已确认启用的正式规则，也不能仅因目录存在就自行启用。

G1资料闸门由人工确认主体、期间、会议包、文件性质/版本、混合文件分派、可读性、跨会议范围、允许延伸领域和本次终点。主控登记分派，不替四路赋值，不替judge确认事项关联。未提供、未分派、未提取、不可读、已检索未找到分别记录。

G2规则闸门由人工确认来源性质、确切条款、适用主体、行为发生时有效版本、事项条件、参数及例外。企业确认不能排除明确适用的外部强制要求；效力、历史适用或规则冲突未解决时交base_rule处理。规则库正式发布不代替本次任务的G2适用性确认。

会外合同、付款、验收、业务总体、关系证明、档案和落实台账，不因卡片列为“最小补证”就自动进入四路白名单。主控先确认扩展任务、材料范围、专门提取路线及输出契约，再开展核验。既有字典无适用项时保留fact.other及定位并请求扩展，不能暗设“实际付款日”“累计承诺额”等键，不能拿会议纪要代替执行凭证。

### 固定执行顺序

1. 固定任务与版本，登记四路完整成果和field_checks、coverage，不只读疑点摘要。
2. judge确认同会议、同事项、同事件/版本关系；标题、金额、相对方和会议次数仅为辅助。
3. 逐事项建立本次应核CONTROL的coverage：已确认正式规则开展判定，应核但待确认的候选保留“规则待确认”及所需依据，不漏在清单外。同时为本次LEAD维度建立lead_scan；不只查“看起来异常”的事项。
4. 先核字段、属性、阶段、口径、精度和参数，再比较。算子仅eq / le / strict_before / before_or_same / set_compare / semantic / change_trace。
5. comparisons不机械映射decisions：consistent不等于符合，different不等于偏差。回看关键原件、反证及例外；发现漏提退回原路独立重提，不改上游事实。
6. 控制判定与线索分开交独立复核；最终认定及定级由评价人员确认。

事实引用使用(run_id, record_id, item_index)，item_index从0开始，通过evidence_indexes回到同record证据及原件位置。record_refs不替代item_refs或comparisons.input_refs。跨运行同名record_id不自动同源；参数记录为正式规则依据，不伪造上游事实引用充当右端。

## 二、规则总表

| 目录号 | 类型 | 主题 | 主要比较路线 | 通用方法 |
|---|---|---|---|---|
| C01 | CONTROL | 事项归类、决定性质与权限 | 议案→记录/纪要；实际决定→权限参数 | T01 |
| C02 | CONTROL | 明确前置程序与先后 | 前置审批/决定→本次决定 | T02 |
| C03 | CONTROL | 通知、议程及材料提供 | 清单通知→实际会议；送达→时限参数 | T03 |
| C04 | CONTROL | 必要论证和专业审查 | 议案审查→最终提交版本/确认要求 | T04 |
| C05 | CONTROL | 出席资格与议事人数 | 记录/纪要→成员及人数参数 | T05 |
| C06 | CONTROL | 讨论、表达和结论顺序 | 原始记录→讨论规则 | T06 |
| C07 | CONTROL | 表决方式、票数与决定 | 记录/纪要→表决参数 | T07 |
| C08 | CONTROL | 关系触发与回避执行 | 关系事实→实际参与→回避参数 | T08 |
| C09 | CONTROL | 记录要素与签认 | 完整原始记录→记录要求 | T09 |
| C10 | CONTROL | 结论与纪要实质一致 | 原始记录→同次有效纪要 | T10 |
| C11 | CONTROL | 紧急决定及事后程序 | 紧急事实→临时授权/报告追认 | T11 |
| C12 | CONTROL | 附条件决议执行边界 | 决定条件→执行证据（需扩展） | T12 |
| C13 | CONTROL | 重大调整与重新决策 | 原决定→变更→调整参数 | T13 |
| C14 | CONTROL | 正式版本与归档留存 | 记录版本→档案实存（需扩展） | T09 |
| C15 | CONTROL | 跟踪、到期报告和后评估 | 决议安排→履行证据（需扩展） | T12 |
| C16 | CONTROL | 会外总体反查应决策事项 | 会外总体→会议决定（需扩展） | T14 |
| L01 | LEAD | 关键测算假设和数据来源 | 议案测算、风险、审查之间 | 业务内容扫描 |
| L02 | LEAD | 摘要与明细勾稽 | 议案内部；议案→记录/纪要 | 业务内容扫描 |
| L03 | LEAD | 方案选择与风险响应 | 方案/风险→意见/决定条件 | 业务内容扫描 |
| L04 | LEAD | 预算覆盖与累计承诺 | 预算→本次/历史承诺叙述 | 业务内容扫描 |
| L05 | LEAD | 资金到位与承诺节奏 | 资金来源→支出及落实安排 | 业务内容扫描 |
| L06 | LEAD | 附条件决策与执行叙述 | 原条件→后续历史/执行叙述 | 业务内容扫描 |
| L07 | LEAD | 方案、相对方、标的变动 | 已关联事项各版本之间 | 业务内容扫描 |
| L08 | LEAD | 潜在先实施后决策 | 历史行为叙述→本次决策 | 业务内容扫描 |
| L09 | LEAD | 分批安排与临界金额 | 获准多个议题/会议的事项和金额 | 业务内容扫描 |
| L10 | LEAD | 暂缓、异议及反馈吸收 | 历次意见/反馈→新方案及处理 | 业务内容扫描 |
| L11 | LEAD | 年度初始预算审批及时性及事前指导作用 | 预算所属期间→首次审议批准/下达→前期控制安排 | 业务内容扫描 |

C01—C16均未启用。卡片数量不是产出指标。一个事实涉及多卡但控制疑问相同的，合为一条lead并列rule_ids；正式规则已足以判断的关联decisions，不重复计为缺陷。

## 三、字段对照快速索引与比较口径

角色简称在卡片中使用中文：清单通知路=meeting_schedule；议案审批路=proposal_extract；原始记录路=meeting_record；纪要决议路=meeting_minutes。下表覆盖配套字典全部48键；允许角色以fact_dictionary.json为准。列入索引不代表每个事项均必须提到该字段。

| 既有字典键 | 可用角色、用途及限定 |
|---|---|
| meeting.entity、meeting.body、meeting.number、meeting.location、meeting.time | 清单通知/原始记录/纪要决议；会议关联。地点和次数仅辅助；拟开会与实际开会分开；时间核precision |
| agenda.title、agenda.number、matter.code、matter.project、matter.counterparty | 四路；事项关联、C01/C13/C16、L07/L09。序号非全局号，相对方或项目相同不自动同事项 |
| document.number、document.version、document.issued_at | 四路；C03/C09—C14及L02/L07。文号非事项号，较晚日期不必然有效；形成/印发非送达或生效 |
| document.signature | 议案审批/原始记录/纪要决议；C04/C09/C14。只提可辨签审用印，不鉴定真实性 |
| proposal.number、proposal.proposer、proposal.action、proposal.submitted_at | 议案审批；C01/C02/C04/C13及L类。申请、提交、同意上会不等于批准实施 |
| proposal.budget、proposal.analysis、proposal.risk、proposal.review | 议案审批；C04及L01—L05/L10。预算声称非批复；假设、限制和专业保留意见完整保留 |
| approval.action、approval.acted_at | 议案审批；C02/C04/C11、L06/L08。保留节点、角色、意见及条件 |
| schedule.change、schedule.distribution、schedule.changed_at、notice.issued_at、notice.received_at、agenda.scheduled_at | 清单通知；C03/C11。发出/签发非必然送达，名单非回执，计划时点非实际发生 |
| history.reference、history.event_at、fact.event_at、fact.other | 四路；历史/事件关联及L04—L10。历史引用非历史原件；fact.other不自动更名或参与自动数值比较 |
| decision.content、condition.content、condition.due_at | 决定仅清单通知/原始记录/纪要决议；条件仅议案审批/原始记录/纪要决议。清单转述非实际决定；保留否定、暂缓、原则同意及条件 |
| follow_up.action、follow_up.owner、follow_up.due_at、document.amendment | 落实三键仅原始记录/纪要决议；更正仅纪要决议。安排非实际履行，更正需对应旧版和授权 |
| financial.amount | 四路；核currency、unit、amount_basis、scope_raw、tax_basis、bound、stage全部限定；actual_claim亦为材料声称 |
| attendance.person、attendance.count、statement.opinion | 人员/人数仅原始记录/纪要决议；发言仅原始记录。人员核role_raw/presence/voting_right；人数核count_type/basis_raw；发言核speaker_raw/role_raw/sequence_raw |
| voting.count、voting.expression、recusal.content | 票数/表决仅原始记录/纪要决议；回避仅议案审批/原始记录/纪要决议。票数核count_type/basis_raw；一致通过不造票数，未知资格不等于无资格 |

日期均检查precision。只有A最晚可能时点早于B最早可能时点才能确认strict_before；同日无钟点不能定严格先后。before_or_same也须符合规则所需精度，不因同日就把未知先后当已满足事前义务。

金额使用十进制计算，在comparisons.normalization记录已知单位换算，原normalized不改写。申请120、批准100通常是调整，用change_trace；记录批准100而同次纪要批准120才可能建立等值命题。币种、税口径、总额/年度/本次/累计未对齐时停止直接计算，缺值不填零。

L11复用上述预算、申请、决定、时间与历史记载字段。预算年度/覆盖期间及“初始、调整”性质由判定者从所引文本作有据语义识别，记入比较说明；不新增字典键，不把标题猜测或任务年份当事实。详见L11卡。

## 四、参数命名表

P01—P14沿用judgment_logic.md。子名是规则参数标签，不是字典键，不能放入records.values.items.field。每个被使用参数保存原值/口径、来源条款及版本、适用主体期间、确认记录。本版客户参数均待确认，未填经验数字。

| 参数组 | 建议参数名与确认内容 | 来源及主要使用 |
|---|---|---|
| P01 | entity_scope、body_type、effective_period：主体、组织类型及有效期间 | 章程、设立调整、制度生废；全部CONTROL |
| P02 | matter_scope、decision_nature：类别、保留事项、研究/审议/批准/备案性质 | 三重一大及专项清单；C01/C02/C16 |
| P03 | authority_map、delegation_scope：有权主体、转授权、期限及例外 | 章程、授权决议、权限表；C01/C11/C13 |
| P04 | required_steps、step_order：前置节点、参与主体、方案及顺序 | 前置清单、专项流程及外部依据；C02/C04 |
| P05 | amount_basis、threshold_boundary、aggregation_scope：币税、包含边界、累计期间及范围 | 授权、预算、投资采购资金规则；C01/C10/C13/C16、L04/L09 |
| P06 | notice_recipients、notice_start、notice_interval、notice_calendar、agenda_change_rule | 议事/通知规则：对象、起点、时限、日历、临时议题；C03/C11 |
| P07 | required_reviews、opinion_sequence、disagreement_response：论证、表达/结论顺序、严重分歧处理 | 专项/议事规则及适用外部条款；C04/C06 |
| P08 | eligible_members、quorum_basis、quorum_rule、vote_basis、vote_rule：成员、人数及表决分母/比例/包含边界/取整、远程委托 | 成员文件、议事规则及适用法律；C05/C07 |
| P09 | recusal_trigger、recusal_scope、recusal_denominator：关系、禁止环节、分母 | 回避制度及适用法律；C05/C07/C08 |
| P10 | emergency_trigger、temporary_authority、followup_procedure、followup_time | 紧急条件、临时权、报告/追认及期限；C03/C11/C16 |
| P11 | condition_type、execution_boundary、material_change、redecision_rule | 原决议、变更/重履和延期权限；C10/C12/C13 |
| P12 | required_record_items、signoff_rule、official_version、archive_scope、retention_rule | 会议/档案制度：记录、签认、版本、归档及保存；C09/C10/C14 |
| P13 | responsible_owner、tracking_due、acceptance_evidence、postevaluation_trigger | 决议/落实制度：责任、期限、验收和后评估；C12/C15 |
| P14 | population_scope、reconciliation_basis、sample_scope | 评价方案、台账调节：总体、完整性、选样和外推；C16/L09 |

LEAD中“关键假设”“重要变化”“接近门槛”等分析选择如果影响纳入排除，需说明本次选择依据及局限。不得默认5%、10%、30天或某金额作预警线，更不能把筛选口径升级为企业违规阈值。

## 五、来源导航与证据等级

下表保留judgment_logic.md的S01—S06编号，本轮补充核验状态以[来源说明](../references/rule_sources.md)为准。正文取得不等于客户适用性确认，也不代表穷尽全部修订、废止和特别规定。S03主题引用定位第7—14项、适用范围第23项；转正时须进一步摘取确切适用项及原文，不能猜配单项条号。

| 来源号 | 源类型、官方位置 | 限定用途 |
|---|---|---|
| S01 | 基本规范：[财政部《企业内部控制基本规范》](https://kjs.mof.gov.cn/zhengcefabu/200807/t20080704_55982.htm)，财会〔2008〕7号，第11、30、33、34条；本轮研究取得正文 | 为治理权限、授权审批、预算及经营偏离分析提供入口；适用对象和历史期间仍待核，不替代更严格特定要求 |
| S02 | 应用指引、指导示范措施：[组织架构指引PDF](https://www.mof.gov.cn/gp/xxgkml/hjs/201005/P020100518351827137241.pdf)，第1—2页第4、5条 | 权责制衡、集体决策、不得擅改设计；须结合S06及具体适用规则 |
| S03 | 国企决策制度政策文件：[2010年“三重一大”意见官方转载](https://jjjcz.mee.gov.cn/djfg/dnfgzd/gfxwj/201006/t20100605_444069.html)，第7—14、23项 | 论证、供料、程序、讨论记录、执行调整、回避后评估来源入口；先核主体期间 |
| S04 | 党内法规：[国企基层组织工作条例（试行）官方转载](https://www.cnipa.gov.cn/art/2020/1/7/art_617_40827.html)，第13、15条及主体条款；沿用已核正文导航，本轮未重新完成全部修废检索 | 核党组织类型及研究讨论关系，不预设党委→总办→董事会链 |
| S05 | 评价方法：[企业内部控制评价指引](https://www.mof.gov.cn/gp/xxgkml/hjs/201005/P020100518351827469815.pdf)，第3、11、15—19条 | 范围、证据、底稿、认定复核，不是经营行为违法的实体依据 |
| S06 | 实施解释：[规范体系实施相关问题解释第1号](https://www.mof.gov.cn/gkml/caizhengwengao/2012wg/wg201204/201207/t20120711_665500.htm)，应用指引实施说明 | 措施具有指导和示范属性，不逐字硬套所有企业 |

本版新增官方问题资料及应用指引条文的位置见[rule_sources.md](../references/rule_sources.md)。官方案例只能启发控制机制问题；不得将案例主体、事实、损失或适用招标门槛迁移为本客户事实和规则，单有案例不能转正CONTROL。

## 六、CONTROL控制规则候选卡

共用结果优先序：规则来源、含义、效力，或规则的主体/期间/触发要求本身未确认→规则待确认；规则明确，仅缺事项触发事实而不能判断是否适用，或缺其他关键事实→证据不足；有证据排除适用→不适用；适用且要求均满足→符合；证据证明具体义务未满足、反证例外已排查→存在偏差。卡片的特定充分条件不取消该顺序。未映射并在本次正式快照确认启用的候选不能直接输出符合或偏差；已确认的正式规则按快照执行。

### C01 事项归类、决定性质与权限

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C01 / C01 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 对每个入选事项辨认“做什么、由谁决定、是否触发权限边界”，包括可能低于门槛的事项，不凭标题直接判重大。 |
| 依据性质与定位 | 方法参考S02第4、5条及S06；正式来源待取得当时章程、权责清单、授权文件具体条款；涉及党组织研究时核S04第13、15条的适用部分。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.action、proposal.proposer、matter.code、matter.project、matter.counterparty、financial.amount、proposal.budget。右：原始记录/纪要决议路meeting.entity、meeting.body、decision.content、condition.content、financial.amount；实际决定再对P02、P03、P05。 |
| 关联前提与限定字段 | 同主体、同事项、对应阶段；金额核全部7项qualifiers，尤其stage/amount_basis；授权在行为时有效；研究、批准、备案分开。 |
| 比较算子与可执行程序 | semantic辨行为及决定性质；change_trace保留申请→批准变化；按确认口径算触发金额，le核实际授权占用额≤权限上限（是否含边界依原文）；逐项对照authority_map，不因会议出现就倒推有权。 |
| 业务参数及来源/确认 | P01—P03、P05：主体、类别、权限、授权期限及累计口径，由实际原件和G2确认；不默认金额最大者权限最高。 |
| 命中处理 | 明确触发特定权限要求，实际作出最终决定的主体无权或超有效授权，排除专项授权/例外后才初判偏差；仅研究建议不按无权决策判。 |
| 反证与正常解释 | 年度框架授权覆盖、预算内细化、另有有权主体批复；申请额大于批准额属于可能的正常压减。 |
| 证据不足 / 未见信号边界 | 缺实际决定、金额口径、主体归属→证据不足；权限清单未定→规则待确认；有纪要不证明已实施。 |
| 中性问题与最小补证 | “本次动作是建议、前置研究还是最终批准，适用哪项当期授权？”补对应授权条款、决定原件及必要金额组成。 |
| 输出去向 | 正式rule_id对应decisions、coverage；申请变化入comparisons；内容变化需解释时关联L07，不自动另报问题。 |

### C02 明确要求的前置程序与先后

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C02 / C02 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 事项符合已确认前置研究、审查、征求意见或报批条件时，核验规定节点及先后。 |
| 依据性质与定位 | S04第13、15条及主体条款为前置关系入口；S03第7—14、23项为程序导航。实际路径取适用原文、企业前置清单/专项流程。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路approval.action、approval.acted_at、proposal.review、history.reference、history.event_at；或获准前次原始记录/纪要决议路meeting.body、meeting.time、decision.content。右：本次原始记录/纪要决议路meeting.body、meeting.time、decision.content、condition.content。 |
| 关联前提与限定字段 | 同事项及需审批方案版本；节点不是“拟提交”或单纯历史转述；日期precision支持比较；既有决定覆盖本次范围。 |
| 比较算子与可执行程序 | semantic把P04拆为事件及必须先后对；strict_before/before_or_same逐对检验实际时点。时间区间重叠→insufficient；核已有整体授权，不机械添加第三类会议节点。 |
| 业务参数及来源/确认 | P01—P04、P11：组织类型、清单、节点、替代及变更后是否重履；G2确认每条路径关系，不仅确认“按规定流程”。 |
| 命中处理 | 可靠实际事件证明应在前的程序晚于决定，或充分核验明确未履行必需节点，且无合法替代，才初判偏差。 |
| 反证与正常解释 | 前期专题研究已覆盖、当前仅报告、合法授权、同一会议内依适用规则完成；补做本身不证明已满足事前要求。 |
| 证据不足 / 未见信号边界 | 缺前置资料不等于没履行；同日无钟点不能定严格先后；历史批准引用非原件；路径不清→规则待确认。 |
| 中性问题与最小补证 | “该版本需完成哪些前置节点，各何时完成？”补对应清单条款、前置原件及覆盖方案页；同日补可核时间戳/过程。 |
| 输出去向 | decisions、coverage及links/comparisons；仅潜在先实施叙述另按L08补证。 |

### C03 通知、议程及材料提供

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C03 / C03 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 有明确通知对象、提前告知、材料提供或临时议题处理要求的会议/议题。 |
| 依据性质与定位 | S03第7—14、23项告知供料/会议程序主题；实际对象、起算、时限、补充程序取本会议议事规则原文。 |
| 字典左端 / 右端及来源角色 | 左：清单通知路agenda.title、agenda.number、notice.issued_at、notice.received_at、schedule.distribution、schedule.change、schedule.changed_at、agenda.scheduled_at、meeting.time。右：原始记录/纪要决议路agenda.title、agenda.number、meeting.time；议案审批路document.version、proposal.submitted_at核材料版本；对象时限对P06。 |
| 关联前提与限定字段 | 同场会议、已确认议题关系；明确收件对象和材料版；precision及发出/收到/拟安排/实际召开性质分开。 |
| 比较算子与可执行程序 | set_compare核通知与实际议题集合，再查schedule.change；逐应收对象按确认日历计算间隔D，用le核要求提前量≤D，并核材料可取得。notice.issued_at不替received_at；仅签发日期不代算送达间隔。 |
| 业务参数及来源/确认 | P06、P10：对象、应供材料、起算、自然日/工作日、是否含当日、临时/紧急要求；无N天规则不自创N。 |
| 命中处理 | 可靠收发或完整过程证明规定对象未按要求获得材料、间隔不足或临时议题程序未满足，排除例外后才初判偏差。 |
| 反证与正常解释 | 更早有效通知、平台可用记录、补发回执、获准临时/紧急程序；撤回议题无须匹配实际讨论。 |
| 证据不足 / 未见信号边界 | 名单非送达，参会签字非提前收料；通知与开会日期不同属正常；新议题缺变更资料先补证。 |
| 中性问题与最小补证 | “该版议题和材料何时向哪些应收人员提供，临时变化如何处理？”补该议题发送/访问记录、变更处理及条款。 |
| 输出去向 | 会级/议题级decisions、coverage，避免同一通知问题重复计数；议题/时限写comparisons。 |

### C04 必要研究论证及专业审查

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C04 / C04 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 类别/条件触发必需论证、审查、征求意见或特定报审主体要求时，查是否针对提交方案完成。 |
| 依据性质与定位 | S03第7—14、23项研究论证主题；正式要求取本事项专项制度/审查规定，不增加所有事项均需法务/专家审查的义务。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.action、proposal.number、proposal.proposer、proposal.analysis、proposal.risk、proposal.review、approval.action、approval.acted_at、document.signature、document.version。右：同路最终方案及原始记录路decision.content、condition.content、statement.opinion；对P04、P07。 |
| 关联前提与限定字段 | 论证覆盖同主体、对象、方案版和金额范围；签署角色、时间precision明确；保留意见不删除。 |
| 比较算子与可执行程序 | semantic列“必需程序—主体—版本—意见—处理”；需事前完成再用strict_before/before_or_same；set_compare核确认的必需清单与有证据已完成清单，不以附件数量替代内容。 |
| 业务参数及来源/确认 | P01、P04、P07：触发类别、主体资格、截止节点、等效材料及豁免，逐项由原文和G2确认。 |
| 命中处理 | 完整流程/可靠原件证明必需程序未完成、主体不合要求或未覆盖实际提交版，排除替代/豁免后初判偏差。 |
| 反证与正常解释 | 合法复用同版意见、独立附件、等效审查、会上缩减范围后仍被原论证覆盖。 |
| 证据不足 / 未见信号边界 | 称已论证但未交原件、测算来源不明，不径判未论证；商业结论不同于评价人员预期不构成偏差。 |
| 中性问题与最小补证 | “审查针对哪版方案，保留意见上会前如何处理？”补指定意见书、版本页、流转节点/豁免依据。 |
| 输出去向 | decisions、coverage和comparisons；测算/方案质量疑问走L01/L03。 |

### C05 出席资格与议事人数

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C05 / C05 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 有确认的资格和会级/议题级人数要求的会议及决定。 |
| 依据性质与定位 | S03第7—14、23项会议程序导航；实际成员及人数条件取适用治理规则/议事规则，不由本卡设比例。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路attendance.person、attendance.count、recusal.content、meeting.time。右：纪要决议路同名字段作交叉核验；最终对P08/P09及当期成员文件。 |
| 关联前提与限定字段 | 同会及必要的议题时段；person核role_raw/presence/voting_right；count核count_type/basis_raw；应到、实到、有权、列席、委托、回避分开。 |
| 比较算子与可执行程序 | set_compare核名单差异并逐人确认资格；judge据可靠名单派生人数时保留去重/剔除明细。先核正式规则的分母B、比例q及边界；人数为整数且规则无另行合法口径时，“至少q”最低人数K=ceil(qB)，“超过q”则K=floor(qB)+1，再用le核K≤有效出席N。不得把严格大于改为大于等于；口径不清时停止数值测试并交规则确认。 |
| 业务参数及来源/确认 | P08、P09：成员生效日、议题资格、远程委托、回避分母、门槛包含边界，需来源/G2。 |
| 命中处理 | 分母、资格、实际出席明确，计算证明召开或决定时不达要求且无合法安排，才初判偏差。 |
| 反证与正常解释 | 生效的成员调整、允许远程、有效委托、议题前到场；缺签名不等于没参会。 |
| 证据不足 / 未见信号边界 | “有关领导参加”、身份/离席时段不明→证据不足；分母/远程规则不清→规则待确认；总人数不推议题有权人数。 |
| 中性问题与最小补证 | “本议题应到及实际有资格出席者是谁，分母如何形成？”补当期成员表、该议题签到/远程/委托和回避时段。 |
| 输出去向 | decisions、coverage、计算comparisons；C07复用核实基础但另验表决。 |

### C06 逐项讨论、意见表达与结论顺序

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C06 / C06 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 有明确逐项研究、逐人表达、负责人结论顺序或严重分歧处理要求的议题。 |
| 依据性质与定位 | S03第7—14、23项讨论、决定与记录主题；实际要求须摘正式原文并核会议议事规则。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路agenda.title、agenda.number、attendance.person、statement.opinion。右：同路decision.content、condition.content、后续statement.opinion；再对P07。纪要摘要不能代完整过程。 |
| 关联前提与限定字段 | 同议题、发言人角色已核；opinion核speaker_raw/role_raw/sequence_raw；排版顺序不当然证明发言顺序。 |
| 比较算子与可执行程序 | semantic分汇报、提问、讨论、结论，列“谁表达什么—如何处理—何时结论”；明确过程证据才用strict_before。先确认严重分歧触发再核响应，不把普通不同意见自动认作严重分歧。 |
| 业务参数及来源/确认 | P07—P09：须表达人员/环节、负责人身份、结论顺序、分歧触发及处理方式。 |
| 命中处理 | 完整可信过程证明明确表达/讨论或结论顺序要求被违反，或严重分歧后的规定动作未履行，排除例外后初判偏差。 |
| 反证与正常解释 | 开场主持非先下结论；续页/录音有补充讨论；允许列席说明后离场；多轮表达正常。 |
| 证据不足 / 未见信号边界 | 简化纪要、摘要、未记某人意见不证明未发言；记录要素不足须另按C09，不能混成讨论程序偏差。 |
| 中性问题与最小补证 | “该议题意见和主持结论的实际顺序如何，原件何处对应？”补完整记录/获准原始载体片段及分歧处理页。 |
| 输出去向 | decisions、coverage；未决意见内容需解释而无明确违规义务时关联L10。 |

### C07 表决方式、票数与决定形成

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C07 / C07 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 实际进入表决或形成需满足明确表决要求的决定。 |
| 依据性质与定位 | S02第5条/S06及S03第7—14、23项为方法/程序入口；实际方式、分母、比例取适用法律/章程/议事规则。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路voting.count、voting.expression、attendance.person、attendance.count、recusal.content。右：同路及纪要决议路decision.content、voting.count、voting.expression；对P08—P10。 |
| 关联前提与限定字段 | 同议题同次有效表决；票数count_type/basis_raw、资格、回避均明确；初次与重表决分开。 |
| 比较算子与可执行程序 | semantic核方式；先核正式规则的分母B、比例q及包含/取整口径。票数为整数且规则无另行合法口径时，“至少q”所需赞成K=ceil(qB)，“超过q”则K=floor(qB)+1，用le核K≤实有赞成F，不将严格大于改成大于等于。票种互斥完整时才eq核F+反对+弃权+无效=已投票数，不强设票种；再核宣布结果。 |
| 业务参数及来源/确认 | P08—P10：有权成员、分母、比例/取整、无效弃权、回避及替代形式。 |
| 命中处理 | 可靠表决事实证明未达要求却宣布通过，或采用明确不允许方式且无例外，才初判偏差；仅提议未表决不硬算有效性。 |
| 反证与正常解释 | 合法重表决、有效更正、允许口头/非记名方式、回避依法扣除。 |
| 证据不足 / 未见信号边界 | “一致通过”“无人反对”不生成票数和分母；原则同意不推全体已投；票数人数冲突先补证。 |
| 中性问题与最小补证 | “本次表决方式、计票基数、票数如何对应宣布决定？”补该项计票/表决原件及适用分母规则。 |
| 输出去向 | decisions、coverage、计算comparisons；表达冲突先核C10版本，不重复计同一问题。 |

### C08 利益关系触发与回避执行

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C08 / C08 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 材料载可核关系/回避事实，或本次明确纳入利益关系申报核验。 |
| 依据性质与定位 | S03第7—14、23项回避主题；实际关系范围、申报及禁止行为取适用法律、章程、回避制度。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路matter.counterparty、recusal.content、history.reference。右：原始记录路attendance.person、statement.opinion、recusal.content、voting.count、voting.expression；纪要决议路回避记载；再对P09。 |
| 关联前提与限定字段 | 人员身份、关系存续、相对方主体有据；person核role_raw/presence/voting_right，opinion核speaker_raw；同名同姓/同单位不是关系证明。 |
| 比较算子与可执行程序 | semantic先核关系触发，再逐环节核申报、说明、讨论、表决、退场；set_compare只比已核应回避人与实际行为集合，不把到会名单等同全程参与。 |
| 业务参数及来源/确认 | P09及P08：申报义务、触发、允许说明环节、禁止参与及分母；关系材料取证经G1最小必要授权。 |
| 命中处理 | 已证实关系符合明确回避条件，实际从事被禁止的行为且无合法例外，才初判偏差；申报义务须另有明确要求。 |
| 反证与正常解释 | 非同一人、关系已终止、仅依规定说明事实、议题前退场、无表决资格。 |
| 证据不足 / 未见信号边界 | 没有回避字样不等于应回避未回避；未填申报表不证明关联或利益输送；未获准材料保留限制。 |
| 中性问题与最小补证 | “该关系是否触发本议题回避，相关人在哪些环节参与？”补必要申报、回避决定、议题时段记录。 |
| 输出去向 | decisions、coverage；关系不明仅提中性补证，不自动创建违规/利益输送结论。 |

### C09 记录必要要素及签认

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C09 / C09 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 规则明确要求形成原始记录、记载要素或履行签认时。 |
| 依据性质与定位 | S03第7—14、23项记录主题；S05第15—19条仅为取证方法。正式要素及签认取企业会议制度具体条款。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路meeting.entity、meeting.body、meeting.number、meeting.time、agenda.title、attendance.person、statement.opinion、voting.count、voting.expression、decision.content、condition.content、document.signature。右：P12的required_record_items/signoff_rule；纪要决议路签认只核其自身，不替原始记录签认。 |
| 关联前提与限定字段 | 完整原件、续页附件及版本已核；人员/票数/发言均按限定；载体确属需签认正式文件，不把工作摘记当正式原件。 |
| 比较算子与可执行程序 | set_compare逐项对应“应记内容—原件位置”；semantic核内容及签署角色，按规则区分签字、会签、电子签认；专门核未记载与未提取的区别。 |
| 业务参数及来源/确认 | P12：必记要素、签认人/节点、电子替代、附件构成；无规则不自创全员签名义务。 |
| 命中处理 | 完整可信原件证明必记内容缺记或必需签认未完成，排除有效续页/附件/电子替代后初判该留痕偏差；不据此认定实际讨论/表决没发生。 |
| 反证与正常解释 | 计票表另附、连续附件记意见、有效电子签认、扫描漏页但原件齐全。 |
| 证据不足 / 未见信号边界 | 仅纪要/节选、扫描缺页、原件未取得→证据不足；未提字段退回原路复查，不直接称原件没有。 |
| 中性问题与最小补证 | “所供是否完整正式记录，规定要素及签认位于何处？”补该议题续页、签认/电子页及附件目录。 |
| 输出去向 | decisions、coverage；实存归档问题归C14，避免与记录内容缺口重复。 |

### C10 原始结论与纪要实质一致

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C10 / C10 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 同会同事项有可信最终会议结论及正式纪要，核是否保留实质授权边界。 |
| 依据性质与定位 | 方法参考S02第5条/S06及S03第7—14、23项；正式义务映射准确记录传达、不得擅改和有效更正要求。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路decision.content、condition.content、financial.amount、matter.project、matter.counterparty、follow_up.action、follow_up.owner、follow_up.due_at。右：纪要决议路同名字段及document.amendment、document.number、document.version、document.issued_at。议案审批路proposal.action仅解释申请阶段。 |
| 关联前提与限定字段 | 同一次决定和最终有效版；金额全部限定一致；期限precision/性质一致；确认是在转述还是合法新决定。 |
| 比较算子与可执行程序 | semantic逐项核动作、对象、否定、范围、条件、责任、期限；同次批准额eq，等值换算留痕；修订change_trace。“测算补齐后实施”变为无条件同意时保留差异并查更正/新决定。 |
| 业务参数及来源/确认 | P05、P11、P12：金额口径、不得擅改范围、正式版、更正/重新决策权限和准确传达要求。 |
| 命中处理 | 可比可信最终结论与正式纪要存在实质边界遗漏/改动，相关完整版本及新决定核查不能解释，按确认义务初判偏差。 |
| 反证与正常解释 | 不改实质摘要、单位换算、撤回草稿、合法更正、后续有权决定；申请120批准100非本卡失真。 |
| 证据不足 / 未见信号边界 | 未签认、缺续页、正式版不明、更正未取得→证据不足；较晚不自动替代较早。 |
| 中性问题与最小补证 | “两份材料对应同次最终决定吗，差异有无更正/重决策依据？”补关键页、正式版标识及明确替代依据。 |
| 输出去向 | links/comparisons→decisions、coverage；同事件未确认保留insufficient和补证，不直接报失真。 |

### C11 紧急临时决定与事后程序

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C11 / C11 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 材料以紧急、临时、先行决定、报告/追认解释偏离常规路径，或存在临时议题。 |
| 依据性质与定位 | S03第7—14、23项紧急/会议程序主题；实际条件、临时权限及后续程序取适用原文和企业规则，不自设“及时”的天数。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路approval.action、approval.acted_at、history.reference、history.event_at、proposal.action；清单通知路schedule.change、schedule.changed_at。右：原始记录/纪要决议路meeting.time、decision.content、history.reference、follow_up.action；对P10。 |
| 关联前提与限定字段 | 同紧急事项及决定范围；临时事件、报告、追认的实际与计划分开；precision足够；紧急原因是具体事实而非标签。 |
| 比较算子与可执行程序 | semantic分测紧急条件、临时权限、记录、报告/追认；确认时限后le核间隔，顺序strict_before/before_or_same；常规与例外分开，有追认仍查临时权限。 |
| 业务参数及来源/确认 | P03、P06、P10、P12：紧急情形、权限、后续对象内容时限及记录。 |
| 命中处理 | 事实明确不满足例外仍使用例外，或证据证明必需后续程序未及时履行且无合法替代，才初判偏差。 |
| 反证与正常解释 | 专项应急授权、已有回执、仅追加报告、同名不同事项、允许临时程序。 |
| 证据不足 / 未见信号边界 | 仅“紧急”、追认标题、起点不明→证据不足；“及时”待解释→规则待确认；追认不自动消除或证明事前偏差。 |
| 中性问题与最小补证 | “何事实触发临时权限，之后履行了哪些报告/追认？”补紧急事实证据、授权及对应程序原件。 |
| 输出去向 | decisions、coverage；先行叙述未能核实行为时关联L08。 |

### C12 附条件决议的执行边界

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C12 / C12 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 有实施前条件、暂停条件或执行边界，且G1授权核验真实执行。 |
| 依据性质与定位 | S03第7—14、23项执行/调整主题；正式要求取有效具体决议及执行制度。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路decision.content、condition.content、condition.due_at、follow_up.action、follow_up.owner、follow_up.due_at。右：获准执行及条件完成原件经另行确认的扩展提取契约进入；四路history.reference、fact.event_at仅核查入口，不作执行凭证。 |
| 关联前提与限定字段 | 条件对应具体决定/执行动作；实施前提、实施后报告、授权内细化分开；期限precision清楚；未建立扩展路线不造字段。 |
| 比较算子与可执行程序 | semantic拆“何条件满足才可何行为”；扩展事实取得后strict_before/before_or_same核条件与实施时点，并核对象金额边界。只有会议资料时先识别条件及做L06，实际执行结论保持不足。 |
| 业务参数及来源/确认 | P11、P13：条件性质、执行起点、确认主体/证据、允许准备工作及延期/调整权限。 |
| 命中处理 | 可靠执行证据证明先决条件未完成就实施或超明确边界实施，且无有效调整/例外，才初判偏差。 |
| 反证与正常解释 | 会外已有效确认条件、许可准备工作、有权调整/延期、该义务只是实施后报告。 |
| 证据不足 / 未见信号边界 | 纪要同意实施/责成落实不证明已签约付款；缺条件材料不证明未完成；未授权扩展不得私读执行目录。 |
| 中性问题与最小补证 | “条件在该实施节点前如何满足并由谁确认？”最小补条件确认页、首个相关实施凭证，主控确认扩展后取得。 |
| 输出去向 | 已获准部分decisions、coverage；扩展请求交主控，叙述线索入L06；leads不能代替已纳入控制检查。 |

### C13 重大调整与重新决策

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C13 / C13 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 批准后出现对象、方案、金额、资金来源、条件变化，并有明确重大调整/重新决策要求。 |
| 依据性质与定位 | S02第5条/S06、S03第7—14、23项调整主题；具体标准取当期授权/变更制度及原决定。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路原decision.content、condition.content、matter.project、matter.counterparty、financial.amount。右：议案审批路新proposal.action、proposal.budget、financial.amount、matter.project、matter.counterparty、history.reference；后续纪要决议路decision.content、document.amendment。 |
| 关联前提与限定字段 | 同事项原决策及后续版本链已确认；主体、范围、金额7项限定对齐；申请变化与实际变化分开；历史引用非原批复。 |
| 比较算子与可执行程序 | change_trace列前后值、阶段及批准依据；semantic对重大调整定义；金额可比算Δ=新额−原额，只有规则确认原额基数且非零才算比例；再核重履节点，不能仅见新申请就假定已经实施。 |
| 业务参数及来源/确认 | P03、P05、P11：定性/量化标准、累计、授权内调整、重履节点和例外。 |
| 命中处理 | 实际变更已发生或规则要求的变更节点已到，明确触发重履而程序未完成且不在授权内，才初判偏差；真实实施需扩展证据。 |
| 反证与正常解释 | 主体更名、已批备选方案、授权内细化、原决定允许调整、有效新决定。 |
| 证据不足 / 未见信号边界 | 新申请非实施证据；重大标准未定→规则待确认；币种税范围不明不算增幅。 |
| 中性问题与最小补证 | “变化在哪个阶段，是否在原授权内或需重决策？”补原批准边界、变更说明、新决定；执行资料另确认。 |
| 输出去向 | comparisons→decisions、coverage；性质待解释时关联L07，不以变化数计问题数。 |

### C14 正式版本与归档留存

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C14 / C14 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 明确要求正式记录、纪要、附件、更正归档保存，且范围含档案核验。 |
| 依据性质与定位 | S03第7—14、23项记录存档主题，S05第15—19条取证方法；具体范围、责任、时限取档案/会议制度。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路document.number、document.version、document.signature、document.issued_at；纪要决议路document.amendment；四路history.reference辅助定位。右：获准档案目录及实存/检索凭证（需扩展，不存在现成“归档状态”键）和P12。 |
| 关联前提与限定字段 | 文件身份、正式版、附件、保存期间清楚；印发precision支持时限；目录、实存、本次提供三种状态分开。 |
| 比较算子与可执行程序 | set_compare核应存—目录—实存；change_trace核更正/旧版留存关系；确认规则后核时限。先说明实际检索范围、权限、责任及补查，再解释缺档。 |
| 业务参数及来源/确认 | P12：正式载体、归档责任期限、保管年限、电子替代及销毁条件。 |
| 命中处理 | 明确义务适用，完整档案范围和补查足以证明应归未归/应存未存，排除替代/合法处置才初判偏差。 |
| 反证与正常解释 | 另库保管、有效电子档、并入综合卷、阅读副本、到期合法销毁。 |
| 证据不足 / 未见信号边界 | 未上传非不存在，目录没搜到非从未形成；检索权限、索引错、缺页均保留。 |
| 中性问题与最小补证 | “正式版及附件归于哪卷/系统，实存和替代关系如何核实？”补该项目录、保管定位和补查记录，扩展经G1。 |
| 输出去向 | decisions、coverage及扩展请求；内容/签认问题归C09，不重复计数。 |

### C15 决议跟踪、到期报告与后评估

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C15 / C15 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 决议/制度有责任落实、到期报告、后评估或反馈要求，本次明确核验该到期义务。 |
| 依据性质与定位 | S03第7—14、23项执行/后评估主题；正式来源为有效具体决议及落实/后评估制度。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路decision.content、follow_up.action、follow_up.owner、follow_up.due_at、condition.content。右：获准后续原始记录/纪要决议路history.reference、history.event_at、follow_up.action、decision.content；真实报告提交/验收证据另行扩展。 |
| 关联前提与限定字段 | 同任务、责任和成果对象；期限precision明确；听取汇报不自动满足完成标准；引用报告非报告原件。 |
| 比较算子与可执行程序 | semantic列“谁—做什么—何时—何证据确认”，逐项核是否到期、责任变更、延期；真实履行时点明确才before_or_same核时限；后评估按P13触发，不一律强加。 |
| 业务参数及来源/确认 | P11、P13：交付/报告/验收、期限起算、后评估触发及延期权限。 |
| 命中处理 | 到明确节点且可靠证据证明规定报告/跟踪/后评估未履行，排除延期/取消/替代后初判偏差。 |
| 反证与正常解释 | 尚未到期、任务合法取消、责任移交、批准延期、报告已在独立系统提交、后评估触发未到。 |
| 证据不足 / 未见信号边界 | 责成落实非已落实，后续纪要无汇报非没报告；效果不佳不等于未跟踪；材料未到手保持不足。 |
| 中性问题与最小补证 | “这项到期义务以何成果/提交记录确认完成，是否有效调整？”补指定报告接收、验收或延期原件，执行取证先扩展。 |
| 输出去向 | decisions、coverage；材料显示反馈未入新方案时另按L10提出内容问题。 |

### C16 会外总体反查应决策事项

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | C16 / C16 / 1.0.0 / CONTROL / candidate |
| 启停与正式规则 | confirmation_status=pending；enabled=false；formal_rule_id=待G2映射 |
| 目标与触发 | 评价包含应上会未上会/期间完整性，G1获准取得独立于已上会资料的总体。 |
| 依据性质与定位 | S05第3、11、15—19条仅支持范围/取证；实体义务来自C01/C02所确认的权限程序，不能用S05直接认定漏报。 |
| 字典左端 / 右端及来源角色 | 左：获准合同、投资、资金、担保、人事等总体明细，须专门提取路线。右：四路matter.code、matter.project、matter.counterparty、agenda.title、financial.amount、history.reference；原始记录/纪要决议路decision.content、meeting.time。 |
| 关联前提与限定字段 | 先核期间、主体、取消/重复、完整性，再核事项粒度；金额7项限定、年度/累计及行为性质一致；标题未匹配非未决策。 |
| 比较算子与可执行程序 | 依P02/P05逐笔筛触发总体，用set_compare反查决定；未匹配补查授权/框架决定/其他合法载体。总体N、已核n、排除、未完成分别登记，无完整总体不算全年漏报率。 |
| 业务参数及来源/确认 | P01—P05、P10、P14：总体调节、触发、授权例外、抽样和外推界限。 |
| 命中处理 | 具体业务实际发生且明确触发义务，可靠关联、完整相关档案与补查证明未履行，排除授权/合并决策/例外后初判偏差。 |
| 反证与正常解释 | 年度框架覆盖、业务取消、历史批准、专项授权、无需再决策的执行支付。 |
| 证据不足 / 未见信号边界 | 已上会包不得推出无漏报；搜索无结果非未履行；三类会议次数/数量不同非缺会；选样限制不得删除。 |
| 中性问题与最小补证 | “总体中该业务由哪份决定或授权覆盖，范围如何对应？”先补该笔凭证及授权定位；总体调节只在获准范围核验。 |
| 输出去向 | decisions、coverage并报告分母/样本限制；分批临界按L09仅作线索，不能先贴规避标签。 |

## 七、LEAD业务线索检查卡

lead_scan每项保留scan_id、matter_id、rule_id、rule_version、state、record_refs、item_refs、lead_ids、linked_decision_ids、reason、limits。linked_decision_ids仅引用本次有效判定成果中实际存在的decision_id；不涉及控制判定时填空数组。state仅用以下五值，不与业务结果混用。

| state | 使用条件 |
|---|---|
| lead_found | 已核具体材料触发并形成可验证控制机制疑问，关联leads；已转入控制判定时可通过linked_decision_ids关联有效decisions，保留触发状态且不重复计问题 |
| no_signal_in_scope | 已核获准且足以开展该维度检查的材料，未形成触发；仅说明该范围结果 |
| insufficient | 所需材料、字段、关联、精度或版本不足，不能可靠完成；不计问题 |
| not_applicable | 有事实证明维度不适用，如无资金安排的纯人事事项不适用资金节奏；不能因缺材料使用 |
| not_processed | 纳入范围但尚未实际检查；全局完成状态保留partial |

发现具体触发且已由CONTROL处理时，state仍为lead_found，通过linked_decision_ids登记去向；如果无独立待核问题，lead_ids可为空，不重复生成同一线索，不能改记no_signal_in_scope。已有具体材料触发而部分材料缺失时，可用lead_found，线索限于已知事实，limits列缺口；只有缺字段而无触发时记insufficient并补证，不包装实质疑点。已核范围没有触发应写no_signal_in_scope，而非造线索。

状态按实际完成情况判断：已获准、可读材料尚未提取或检查，属于not_processed，不能以insufficient掩盖未做；已完成本次可执行查阅但关键材料未提供、不可读或事实确实不足，才用insufficient。仅因上游遗漏字段，应向原路发起中性复查；该复查是本次必须完成且尚未完成时仍保留未处理范围。

leads保留lead_id、matter_id、description、record_refs、why_follow_up、neutral_question、needed_materials、suggested_domain，并补rule_ids、item_refs、trigger_facts、alternative_explanations、control_question、suggested_next_step。事实、机制疑问及可能解释分开；无grade、违规概率或动机推定。口头解释可指引取证，核到对应材料后才调整线索。

### L01 关键测算假设和数据来源

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L01 / L01 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；主控scope含线索分析、G1批准范围内；扫描含需求、产量、价格、利用率、回收等关键假设的事项。 |
| 方法来源 | 证据分析设计；参考S05第3、11、15—19条及S03第7—14项论证主题；[来源说明](../references/rule_sources.md)的资金/工程指引及A01案例仅启发假设和成本控制疑问，不构成客户既有问题。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.analysis、financial.amount。右：同路proposal.risk、proposal.review、document.version、history.reference；原始记录路statement.opinion、condition.content核会议关注是否针对同一假设。 |
| 关联前提与限定字段 | 同版本、期间、对象、假设含义；金额7项限定及历史引用性质；非金额假设保留proposal.analysis原文，不造利用率等键。 |
| 材料触发与潜在机制疑问 | 测算明确依赖某价格/需求，却仅笼统写“按市场情况”，或审查已提取数疑问但未见对应解释。关注关键输入是否可追溯、复核、更新并与决策版本一致；预测乐观本身不证明失实。 |
| 比较算子与可执行程序 | semantic逐项列实际关键假设、来源说明及限制，查同路获准附件是否对应；change_trace核各版假设变动与解释。具体模型及数据齐备才复算，不自定行业收益率。 |
| 分析参数及来源 | 关键性依据材料明示敏感因素、结论依赖或专业关注；选择理由写calculation，不预设市场价格或可接受收益阈值。 |
| 命中处理 | lead_found并形成“某测算输入的来源/版本或复核过程待核”；trigger_facts载依赖关系和原文，control_question聚焦取数、验证、更新机制。 |
| 反证与正常解释 | 来源在漏交附件、合法沿用获批可研、公开价格只是情景值、独立复核在其他获准材料。 |
| 证据不足 / 未见信号边界 | 已获准可读附件尚未提取/检查→not_processed；现有范围已查而关键附件未提供/不可读且无具体触发→insufficient；已核假设依据相互对应→no_signal_in_scope，不证明预测必将实现。 |
| 中性问题与最小补证 | “该版决定的关键假设取自何时、何项数据，经何种复核？”补该输入的测算页、来源及版本/复核页，优先关键一项。 |
| 输出去向与延伸领域 | lead_scan及有触发的leads；延伸投资可研、预算、市场需求、后评估；执行/外部数据需主控另确认范围。 |

### L02 摘要、明细与同口径数据关系

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L02 / L02 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描含摘要、明细、汇总附件或多处同一数值陈述的事项。 |
| 方法来源 | 数据勾稽/版本分析设计，S05第15—19条为方法参考；不据数字不一致直接认定失实或损失。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.analysis、financial.amount、proposal.budget、document.version的摘要/合计。右：同路同版附件proposal.analysis、financial.amount；原始记录/纪要决议路financial.amount、decision.content核不同阶段转述。 |
| 关联前提与限定字段 | 同命题、范围、版本；金额币种、单位、税口径、总额/本次/累计、bound、stage齐全；明细完整、互斥及抵减项明确。 |
| 材料触发与潜在机制疑问 | 可比明细与明示合计不符，同版同命题相反陈述，摘要省略附件明确限制。关注上会信息校核、版本控制和限定语传递。 |
| 比较算子与可执行程序 | eq核Σ完整互斥明细=摘要合计，保留每项引用、换算和抵减；semantic核结论与附件限制。申请→批准改change_trace，不入同值勾稽。 |
| 分析参数及来源 | 范围、舍入精度、抵减取材料说明；无说明不自定容忍度，展示原值及差额。 |
| 命中处理 | 形成“摘要与明细勾稽/限定语传递待核”线索，写冲突字段和可比依据，不直接称财务错报。 |
| 反证与正常解释 | 四舍五入、税口径不同、备选项重复、汇总抵销、附件漏页、不同有效版或合法批准压减。 |
| 证据不足 / 未见信号边界 | 明细不全/范围未知→insufficient；属性不同说明不宜直接比较并改正确命题；已核吻合→no_signal_in_scope。 |
| 中性问题与最小补证 | “该合计包含哪些明细/调整项，两处表述为何不同？”补对应关系表、必要明细页及有效版说明。 |
| 输出去向与延伸领域 | lead_scan、leads；同次记录与纪要失真且有正式义务时转C10；延伸财务数据质量、预算、信息报送。 |

### L03 方案选择理由与风险响应

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L03 / L03 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描有备选方案、关键风险或专业保留意见的事项。 |
| 方法来源 | 决策依据/风险响应分析；S02第4、5条/S06、S03第7—14项及来源说明所列工程/合同指引仅启发；不设“最低价必选”等商业答案。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.analysis、proposal.risk、proposal.review、proposal.action。右：原始记录路statement.opinion、decision.content、condition.content；纪要决议路decision.content、condition.content、follow_up.owner、follow_up.action。 |
| 关联前提与限定字段 | 风险、方案及意见针对最终版本；opinion按speaker_raw/role_raw/sequence_raw核；保留假设及适用限制。 |
| 材料触发与潜在机制疑问 | 列有实质备选方案而选择理由不可追踪；审查已指出关键风险但受影响方案未说明回应；措施与风险无直接对应。关注方案评价、风险接受和责任安排。 |
| 比较算子与可执行程序 | semantic建立“备选及维度→理由→已知风险→回应/承担者→决定条件”链，逐项核实质响应，不数风险标题、不自行评最佳方案。 |
| 分析参数及来源 | 关键性以材料明示重要性及决定依赖为据；风险容忍度/接受权限未定时留待核，无统一阈值。 |
| 命中处理 | 形成“选择依据或风险响应如何进入决定待核”线索；control_question问评估、接受、落实机制。 |
| 反证与正常解释 | 单一方案有约束、战略目标容许成本较高、专题报告已有比较、有权主体接受风险并设条件。 |
| 证据不足 / 未见信号边界 | 缺专业附件而无具体触发→insufficient；纯例行无该维度可有据not_applicable；链条已核清楚→no_signal_in_scope。 |
| 中性问题与最小补证 | “这项风险/备选方案如何影响推荐和最终条件？”补对应比较页、风险接受/响应说明及责任安排。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸投资、采购、合同、技术路线、合规审查；明确必需审查义务关联C04。 |

### L04 预算覆盖与累计承诺

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L04 / L04 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描预算、本次支出/投资及相关历史/分期承诺。 |
| 方法来源 | 预算占用/承诺口径分析；S05方法及来源说明预算指引第11、14条作启发，不把“已列预算”当已取得批复。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.budget、financial.amount、proposal.action。右：同路history.reference、proposal.analysis、financial.amount；获准既有原始记录/纪要决议路financial.amount、decision.content、condition.content。 |
| 关联前提与限定字段 | 同预算对象、年度、币税口径、用途；金额stage/amount_basis/scope_raw明确；同承诺跨材料去重，历史引用未核原件不作确定实际数。 |
| 材料触发与潜在机制疑问 | 声称预算内却记载原预算未覆盖的新用途/期间；本次加明示既有承诺可能共占同额；额度与承诺范围缺乏对应。关注预算占用、可用余额和跨期承诺控制。 |
| 比较算子与可执行程序 | semantic区分已批、申请、估计和来源；资料齐且P05明确才派生B−C−N，其中B已核预算、C去重既有占用、N新增。le比较占用与额度仅为分析关系，不直接判超预算。 |
| 分析参数及来源 | P05预算/累计仅确认后使用；缺B/C不能填零，不默认年度可结转。 |
| 命中处理 | 形成“预算如何覆盖本次/相关承诺及可用额度待核”线索，金额表述限定为材料记载，不称已超支。 |
| 反证与正常解释 | 已批预算调整、跨年总预算、承诺解除、其他有效额度、框架上限非必然支出。 |
| 证据不足 / 未见信号边界 | 单纯缺批复且无触发→insufficient；覆盖已核清→no_signal_in_scope；单会包不测企业总承诺。 |
| 中性问题与最小补证 | “该额度覆盖哪些期间用途，新增后如何算余额？”补预算批复/调整页及该事项承诺调节表；会外台账扩展须授权。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸预算、合同承诺、投资、财务；正式权限义务与事实充分后关联C01/C13。 |

### L05 资金到位与支出承诺节奏

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L05 / L05 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描有融资、自有资金、回款等来源及支付/开工安排的事项。 |
| 方法来源 | 资金计划与承诺衔接分析；S05方法及来源说明资金活动指引第13—15条作启发，不默认流动性安全比例。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.budget、proposal.analysis、proposal.risk、financial.amount、condition.content。右：同路proposal.action、fact.event_at及原始记录/纪要决议路follow_up.action、follow_up.due_at、condition.content、condition.due_at、financial.amount。 |
| 关联前提与限定字段 | 同资金用途币种期间；预计到位/承诺/收到与拟承诺/承诺/支付分开；日期precision、金额stage/bound完整。 |
| 材料触发与潜在机制疑问 | 资金尚待落实但材料安排更早刚性签约/付款，融资前提与执行计划不一致，已提示缺口无对应措施。关注承诺前资金可用检查和备选安排。 |
| 比较算子与可执行程序 | semantic匹配来源条件/预计日与支出节点；时点明确用before_or_same作计划关系比较并标注计划性质；不足不造现金流表，落实期限不是实际付款日。 |
| 分析参数及来源 | 支出刚性、融资条件、可用资金定义取材料或确认规则，不预设安全垫/偿债比率/周转天数。 |
| 命中处理 | 形成“资金兑现与承诺节点是否匹配”的线索，不称资金链已断裂。 |
| 反证与正常解释 | 附条件合同未生效、可支用现金池/授信、合法顺延付款、自有资金已落实但附件未展。 |
| 证据不足 / 未见信号边界 | 仅总额无来源/支付节点→insufficient；无资金安排可有据not_applicable；计划合理→no_signal_in_scope，不证明实际到账。 |
| 中性问题与最小补证 | “承诺前可用资金依据是什么，来源延后如何安排？”补该项资金计划、融资条件、首个重要付款节点；银行/支付证据另扩展。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸资金、融资、合同支付、进度，实际执行转专门核验。 |

### L06 附条件决策与执行叙述

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L06 / L06 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描有先决、暂停、限额条件且后续出现执行叙述的事项。 |
| 方法来源 | 条件传递/落实分析；S03第7—14项执行主题及来源说明合同指引仅为启发，真实义务另走C12/G2。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路decision.content、condition.content、condition.due_at、follow_up.owner。右：议案审批路proposal.action、approval.action、history.reference、history.event_at、fact.event_at；后续原始记录/纪要决议路follow_up.action、decision.content。 |
| 关联前提与限定字段 | 同条件、事项、阶段、动作；期限与执行时点分开；历史叙述/计划不提升为已核实际，日期precision匹配。 |
| 材料触发与潜在机制疑问 | 原决定要求完成某项后实施，后续明确称已实施却未说明条件完成；暂停/限额在后续叙述消失。关注条件传达、解除确认和实施前检查。 |
| 比较算子与可执行程序 | semantic逐条映射条件到后续叙述，change_trace记录保留/调整；日期比较只是声称事件时序，不借comparisons升级为实际事实。 |
| 分析参数及来源 | 以原文条件性质为主；执行起点、有效解除未确认则保留，不默认签约/付款/开工都等价。 |
| 命中处理 | 形成“条件如何转为实施前控制、解除依据待核”的线索，不写成条件未完成即实施的既定结论。 |
| 反证与正常解释 | 独立验收完成、有效变更、获准准备工作、后续简略表述、实际是其他阶段。 |
| 证据不足 / 未见信号边界 | 仅有条件且本次仅检查材料叙述，已核范围可no_signal_in_scope并注明未验证执行；已获准且可读的材料尚未提取/检查→not_processed；现有范围已查但关键材料未提供→insufficient；缺执行凭证非违规证明。 |
| 中性问题与最小补证 | “后续实施具体指何行为，原条件何时由谁确认完成或调整？”补条件确认/变更页和首个行为凭证，主控批准扩展后取得。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸合同、采购、建设、支付；规则和实际证据充分后对应C12，去重。 |

### L07 方案、相对方和标的变动

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L07 / L07 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描多版本、历史批准引用或后续调整事项。 |
| 方法来源 | 业务范围/版本追踪；S02第5条/S06、S03第7—14项及来源说明工程/合同指引为启发，变化本身并非违规。 |
| 字典左端 / 右端及来源角色 | 左：原始记录/纪要决议路原matter.project、matter.counterparty、financial.amount、decision.content、condition.content。右：议案审批路proposal.action、proposal.analysis、proposal.budget、matter.project、matter.counterparty、financial.amount、history.reference；纪要决议路document.amendment。 |
| 关联前提与限定字段 | 同事项/版本已确认或注明候选；同项目非必然同采购包；金额7项限定及主体身份相符；会前推荐、会上决定、会后声称变化分开。 |
| 材料触发与潜在机制疑问 | 后续改变关键对象/相对方/技术路线/来源/金额仍援引原批复，覆盖关系不清；调整理由不对应原风险条件。关注变更识别、授权覆盖与风险再评估。 |
| 比较算子与可执行程序 | change_trace列对象、范围、金额、条件前后值及依据；semantic核仍按原批复的解释。候选关联只提核实关系问题，不作确定性差异。 |
| 分析参数及来源 | 关键性依原批准边界、方案依赖或材料自述影响；不自设重大调整比例，正式阈值经C13/G2。 |
| 命中处理 | 形成“变化是否仍获原授权覆盖、是否更新审查依据”的线索，不称擅自变更/暗换供应商。 |
| 反证与正常解释 | 仅更名未换主体、备选已批、授权内细化、缩减范围、有效新决定。 |
| 证据不足 / 未见信号边界 | 缺历史原件→相关关系insufficient；已有具体变化叙述可形成限定线索；申请120批准100且正常调整有据→no_signal_in_scope。 |
| 中性问题与最小补证 | “变化在哪阶段，原批准哪段覆盖，有无另行确认或审查？”补前后关键页、变更说明及覆盖/新授权页。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸合同、采购、投资、科研路线和工程变更；正式义务确认后关联C13。 |

### L08 潜在先实施后决策的时间关系

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L08 / L08 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描已签约、已开工、已支付、补办、追认等具体行为叙述。 |
| 方法来源 | 时序/授权覆盖分析；S03第7—14项及来源说明工程、合同指引为启发；关键词仅引导读原文，不是判定。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路proposal.action、approval.action、history.reference、history.event_at、fact.event_at及四路获准同类历史记载。右：原始记录/纪要决议路meeting.time、decision.content；议案审批路approval.acted_at按实际节点性质使用。 |
| 关联前提与限定字段 | 同主体事项行为范围；准备/正式承诺/执行/计划分开；precision保留；当前会议未必首次授权，历史批准须核原件。 |
| 材料触发与潜在机制疑问 | 材料明示具体行为先于本次申请/决定，既有授权或紧急覆盖解释不清。关注执行起点、事前授权验证和补办处理。 |
| 比较算子与可执行程序 | semantic确认“已”修饰行为；strict_before/before_or_same比声称时点与本次决定，标注事实性质。同日无时点→insufficient；并查获准历史授权和紧急解释，不以本次会机械认首次批准。 |
| 分析参数及来源 | 执行起点及事前义务待正式规则确认；印发、提交、拟开工不等同实际批准/实施。 |
| 命中处理 | 形成“前序行为由何授权覆盖”的线索，照原文限定trigger_facts，不写先干后批已成立。 |
| 反证与正常解释 | 更早授权、框架覆盖、附条件合同未生效、准备工作、紧急权限、本次仅备案/调整。 |
| 证据不足 / 未见信号边界 | 仅追认标题无动作日期→insufficient；时间明确授权待核可成限定线索；无时序触发→no_signal_in_scope，不证明实际均事前审批。 |
| 中性问题与最小补证 | “所述行为何时实际发生，由哪份当期授权/紧急程序覆盖？”补首个行为凭证及授权关键页，执行取证须G1扩展。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸合同、采购、建设、支付、应急；规则和实际事实足够后关联C02/C11。 |

### L09 分批安排与临界金额

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L09 / L09 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准跨议题/跨会议范围；扫描可关联分批或有已确认门槛参照的事项。 |
| 方法来源 | 分组/累计分析，S05第3、11、15—19条；[来源说明](../references/rule_sources.md)A02案例只启发整体需求划分，中央预算单位招标规则不能直接套企业。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路matter.project、matter.counterparty、matter.code、proposal.action、financial.amount、proposal.submitted_at、history.reference。右：获准其他事项四路对应标识、financial.amount及原始记录/纪要决议路decision.content、meeting.time。 |
| 关联前提与限定字段 | 先核同需求/工程范围/资金用途、共同计划、独立交付边界；同组事项保留各自matter_id，在links中以same_group登记关联，并在comparison.preconditions/calculation记录入组依据、期间、范围和排除项，不为了累计而合并为同一事项；项目/相对方相同仅候选；金额scope_raw/stage/amount_basis及币税单位、日期precision相符；同事项多次上会不重复累计。 |
| 材料触发与潜在机制疑问 | 明示同一整体计划却分批申请，或已确认门槛附近反复安排且累计覆盖解释不清。关注需求划分、合并计算及权限路由；单笔近门槛不足以推主观规避。 |
| 比较算子与可执行程序 | semantic先核分组依据，change_trace去重阶段；资料和P05齐备才算ΣA_i并对门槛。门槛未确认不用临界措辞；分批事实仍可问整体计划/独立性。 |
| 分析参数及来源 | P05/P14确认累计期间、关联范围、门槛；“接近”筛选区间须任务明确并说明纯分析性质，不默认90%等比例。 |
| 命中处理 | 形成“分批范围和累计审批口径是否一致”的线索，列纳入项、依据、遗漏范围，不称拆分规避成立。 |
| 反证与正常解释 | 独立需求/标的、真实跨期分期、技术交付决定批次、框架已授权、重复报进度非新增承诺。 |
| 证据不足 / 未见信号边界 | 获准跨会单元未做→not_processed；未获准范围仅在limits说明并请求授权，不伪装已查；关联/基数不足→insufficient；独立边界已核清→no_signal_in_scope。 |
| 中性问题与最小补证 | “批次源于何整体计划，独立边界是什么，适用规则如何累计？”补需求计划、划分说明、批次调节及门槛条款。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸采购计划、投资分期、合同、权限；全年漏报须C16另核，不能外推。 |

### L10 反复暂缓、未决异议与反馈吸收

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L10 / L10 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；scope含线索分析且G1获准；扫描复议、暂缓、保留意见、后评价反馈/整改事项。 |
| 方法来源 | 问题闭环分析；S03第7—14项讨论/执行/后评估、S05第15—19条和来源说明工程后评估条文为方法参考，不把多次审议本身视为失控。 |
| 字典左端 / 右端及来源角色 | 左：原始记录路statement.opinion、decision.content、condition.content、follow_up.action、follow_up.due_at；纪要决议路对应非发言字段。右：新议案审批路proposal.analysis、proposal.risk、proposal.review、proposal.action、history.reference、history.event_at；后续记录/纪要decision.content。后评估无专用键时保留fact.other并请求扩展。 |
| 关联前提与限定字段 | 同事项同一待解问题，不同原因暂缓不合并；opinion核speaker_raw/role_raw/sequence_raw，期限核precision；只见历史反馈引用不等于读过报告。 |
| 材料触发与潜在机制疑问 | 同一明确疑问连续复议仍出现而材料无相应变化；再提交未说明原暂缓条件处理；引用后评价教训却沿用受质疑假设且无解释。关注意见分派、验证关闭和再提交检查。 |
| 比较算子与可执行程序 | semantic建“前次问题→要求/责任/期限→本次回应→决定处理”，change_trace核要求修改的内容；不按会议次数设异常。fact.other只保留原文及复查请求，不自动拆新字段计算。 |
| 分析参数及来源 | 问题和期限取原决定/意见/反馈；后评估义务、销项要求另需P13/G2，不设复议次数上限。 |
| 命中处理 | 形成“此前具体问题如何关闭并进入新方案”的线索，不直接称整改不力、决策失效、重复损失。 |
| 反证与正常解释 | 分阶段成熟决策、新事实合理改结论、独立附件已回应、原风险经授权接受、反馈针对其他范围。 |
| 证据不足 / 未见信号边界 | 仅多次上会无同一未决问题→no_signal_in_scope；缺历次/反馈原件→insufficient；缺后评估不自动生成未吸收线索。 |
| 中性问题与最小补证 | “此前这一项意见/反馈在方案何处处理，以何证据确认关闭？”补该项响应对照、对应测算/调整和确认页，后评估证据先确认扩展。 |
| 输出去向与延伸领域 | lead_scan、leads；延伸后评估、整改、计划、风险管理；明确到期义务关联C15，实质同一问题去重。 |

### L11 年度预算方案首次审批的及时性及事前指导作用

| 固定项 | 本卡内容 |
|---|---|
| id / catalog_id / version / kind / status | L11 / L11 / 1.0.0 / LEAD / analytic_method |
| 启停与适用 | method_status=designed；enabled=true；本次lead_scope纳入L11且G1批准资料范围时使用。检查年度初始预算方案的编制、首次审议批准及下达与其覆盖期间是否衔接；预算调整只用于确认事项性质、排除误认，本卡不开展调整审批测试。 |
| 方法来源 | 预算事前指导和资金约束的控制目的；S02第15号全面预算第5、8、10、11条及S06的指引性质说明，具体定位见来源说明第6节。草案编制要求、首次最终批准和下达是不同节点；不把草案编制要求改写成董事会审批截止日。方法不是客户违规或缺陷认定依据。 |
| 字典左端 / 右端及来源角色 | 左：议案审批路agenda.title、proposal.action、proposal.budget、proposal.analysis、proposal.submitted_at，原文明确编制事件可用fact.event_at；其他获准路线的agenda.title、history.reference辅助确认预算所属期间与初始性质。右：原始记录/纪要决议路meeting.time、decision.content、document.version、document.issued_at、document.amendment；议案审批路approval.action、approval.acted_at，四路获准history.reference/history.event_at辅助查更早批准或临时安排。各键仍仅由字典允许的角色提取。 |
| 关联前提与限定字段 | 同一企业及年度初始预算，覆盖年度/期间和最终批准主体分别核实；首次由原文明示或获准完整历史核查支持，单次会议包未见早期决议不能证明首次。meeting.time须结合实际会议结论使用；拟召开、提交、同意上会、印发均不自动等于最终批准。缺年不补年，期间不明不造起止日期。 |
| 材料触发与潜在机制疑问 | 材料足以确认年度初始预算的所属期间和首次批准时点，显示预算所覆盖年度已运行较长阶段才首次批准，可触发审批与事前指导的衔接疑问；例如明确覆盖当年1—12月的初始预算于当年9月首次获批。9月只是例子，不是统一门槛。即使制度未明确审批截止日，仍检查控制目的。前期支出凭证未提供不消除已经成立的时点触发，也不能据此推断发生了无预算支出。 |
| 比较算子与可执行程序 | semantic确认初始/调整性质、预算期间、审批节点和首次依据；change_trace按有据节点梳理“草案编制→提交→首次最终批准→下达”，已知期间和日期用before_or_same或strict_before作时间关系比较，精度不足不作严格先后结论。节点缺失逐项保留，不强求全部节点齐全才提出已有事实支持的线索。编制完成不替代批准；只比较已知事实，不由判定者补上游字段。 |
| 分析参数及来源 | 预算年度/覆盖范围取原文；批准权限取当期适用章程、授权及正式规则。无截止日时不自设1月底、季度末或延迟天数等违规门槛，不机械认定预算期间开始后任何一次审批均异常。“较长阶段”的选择应说明实际时点、覆盖期间、企业成立/经营起点等相关事实，不能暗设通用阈值。 |
| 命中处理 | lead_found，形成“年度初始预算首次审批时点可能影响事前统筹和约束，前期控制依据待核”的线索，列所属期间、首次批准证据和时点，明确尚未验证实际支出。以leads记录具体疑问；不能直接写预算失效、无预算支出、违规或缺陷等级。 |
| 反证与正常解释 | 本次实为调整且早期初始预算有据；9月审批对应下一年度；企业新设或预算覆盖期晚于自然年初；有更早的有效授权。临时预算、月度额度、资金计划或草案已编制的声明不自动排除线索：须核权限、期间、范围和实际执行，且不自动替代应履行的正式审批。有效替代控制可能缓解资金约束风险，年度审批程序是否充分仍另核。 |
| 证据不足 / 未见信号边界 | 已有明确时点触发但缺前期执行材料→lead_found并在limits/needed_materials列缺口；只有缺材料、无时点触发→insufficient。初始/调整、所属年度、是否批准或首次依据不明且尚无其他足够触发→insufficient，不把只有上会通知当批准；本次需读而未读的资料→not_processed。核实为调整事项→not_applicable，仅限L11，不给调整程序背书；初始预算在其覆盖期前已批准且本维度无其他触发→no_signal_in_scope，不保证未来执行有效。 |
| 中性问题与最小补证 | “初始年度预算获批前，资金安排和支出依据什么控制；由谁授权，覆盖哪些期间和业务？首次审批与下达时点怎样保障该年度预算的事前作用？”先取相关预算编报流转、早期批准/下达及临时安排的关键页；核验实际影响时再申请有针对性的前期资金计划、支出样本与执行记录，不默认索取全年全部业务。 |
| 输出去向与延伸领域 | lead_scan、leads，suggested_domain写预算管理/资金管理，needed_materials及suggested_next_step列最小补证与核验动作；通过requests交主控确认会外扩展范围和专门提取路线，不增加四路读取权限。不因无企业日期条款停止线索扫描；若扩展后证据支持控制设计或执行问题，再结合适用要求、控制目标及评价标准按权限认定，不直接把L11作为CONTROL依据。 |

## 八、跨管理领域线索的交接

三重一大资料是业务控制问题的发现入口。会议程序符合，也要检查获准范围内材料内容是否出现具体触发；一个议题可以指向多个领域，但不表示这些领域已经接受完整评价。以下是现有规则的延伸方向导航，不另增检查义务或自动扩大任务。

| 资料中的具体信号 | 可能延伸领域 | 现有入口及最小核查方向 |
|---|---|---|
| 年度初始预算较晚首次批准，或额度与承诺范围不对应 | 预算、资金管理 | L11、L04：前期控制依据、预算覆盖与额度使用 |
| 投资收益高度依赖未获支持的需求/价格假设 | 投资、战略与风险管理 | L01、L03：关键假设来源、复核及风险回应 |
| 同一整体计划分批申请，累计审批口径不清 | 采购、合同与权限管理 | L09：共同需求、分批理由、授权累计口径 |
| 决定对象、相对方或方案与后续材料不一致 | 合同、采购、投资或工程管理 | L07：变更性质、原授权覆盖及更新依据 |
| 资金来源待落实而材料安排更早刚性支付 | 资金、融资与合同管理 | L05：资金可用条件、支付安排与备选措施 |
| 实施叙述早于本次决策，或原先决条件在后续材料消失 | 合同、工程、投资与资金管理 | L08、L06：实际行为节点、更早授权及条件完成依据 |

交接使用既有leads字段：trigger_facts和引用→control_question→alternative_explanations→neutral_question→needed_materials→suggested_domain与suggested_next_step。建议延伸领域不代表已取得该领域取证权限，也不因为涉及多个领域就重复计为多个问题。

主控登记线索并确认最小扩展范围、资料白名单和专门输出契约；专项事实提取采用新任务及独立上下文，只收到中性核查问题和获准原件，不接收期待结论。四路原始成果保留，新增证据由判定者关联并交独立复核；主控不改原事实、不因发现线索自动开展全年或全领域检查。

## 九、新增和维护

1. 先写具体控制命题或可检验机制问题，确定CONTROL/LEAD再选字段；不能因字段易提取就造义务。
2. 新CONTROL保持candidate/pending/disabled，补来源参数交base_rule/G2；新LEAD说明触发、正常解释及扫描范围，由主控在任务中确认采用。编号顺延，不复用旧号。
3. 仅用既有键及允许角色；新类型用fact.other保留原文并请求扩展。字典变更须单独升版、更新提取提示词和验证，不在本库暗加字段。
4. 正式参数保留来源、有效期间和确认。if/then、计算式或“应”字不是来源，不能用测试方法间接增设义务。
5. 改触发、含义、算子、口径或输出位置须升单卡版本、登记原因和受影响单元；保留旧运行，不在正式任务中自动按发现改规则。
6. 修改后检验字段/角色白名单、反证能否阻误报、缺事实与缺规则分离、正式映射、线索覆盖和引用；合成检查不等于真实验收。
7. 必测边界：申请120批准100不判错；同日无钟点不定严格先后；一致通过不推票数；发出非送达；纪要非执行；已上会包不推全年完整；程序符合仍扫内容；无触发不凑线索；缺字段不计问题；案例不迁移客户事实。

### 可复制空卡（15行）

~~~text
### [目录号] [具体名称]
id/catalog_id/version/kind/status：
启停：CONTROL填confirmation_status=pending、enabled=false、formal_rule_id待映射；LEAD填method_status=designed、enabled=true及任务范围条件。
目标/适用触发：
来源性质/原件位置/正式适用确认或方法参考：
字典左端（角色、键、引用）：
字典右端或确认参数（角色、键、引用/参数来源）：
关联前提/限定字段：
比较算子/中文步骤/必要公式：
业务或分析参数/来源及确认：
命中处理（LEAD写材料触发→控制机制疑问）：
反证/正常解释：
证据不足/未见信号边界：
中性问题/最小补证：
输出去向/延伸领域：
~~~
