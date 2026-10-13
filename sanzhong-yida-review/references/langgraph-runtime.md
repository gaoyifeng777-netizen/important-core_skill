# LangGraph本机运行与Codex桥接

本参考供主控执行，用户只提供业务信息和确认回复。包1.2.0，运行传输协议1.0与工作流1.1.0、角色业务schema分别编号。默认专业执行使用[逐任务沙箱](sandbox-execution.md)。

## 启动和环境

在Skill根目录运行下列命令；其他位置使用实际脚本路径：

```text
python scripts/launch_runtime.py doctor
python scripts/launch_runtime.py init --project "项目运行目录" --config "项目配置.json"
python scripts/launch_runtime.py status --project "项目运行目录"
```

launch_runtime优先读取SANZHONG_REVIEW_PYTHON环境变量，其次读取当前Codex配置目录下skill-runtimes/sanzhong-yida-review.json的python_path，最后尝试当前解释器。包内不写本机固定路径。缺依赖时，在专用虚拟环境安装scripts/requirements-langgraph.txt并配置入口；不要修改无关全局Python。doctor须实际通过。

项目配置最低需要project_id，主控另保存entity、period、stop_at、授权输入输出范围及资源限制。示例仅为结构：

```json
{
  "project_id": "PROJECT-001",
  "entity": "评价对象",
  "period": "2025年度",
  "stop_at": "完整判定与复核"
}
```

运行目录保存checkpoints.sqlite、config.json、events、tasks、submissions、gates和confirmations。完整状态用status --full查看。项目同一时刻只有一个写命令，专业角色可以并行阅读各自输入并输出；主控依次提交。不要手改SQLite、任务输入或归档结果来纠错。

图使用真实StateGraph和SQLite检查点，以interrupt等待角色成果或人工决定，收到事件后校验并恢复。图待办不是已执行的子智能体；独立沙箱适配器通过execute/execute-batch真实完成角色并回传。图不直接调用原生collaboration工具。[LangGraph interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts)及[持久化说明](https://docs.langchain.com/oss/python/langgraph/persistence)说明这种外部恢复模式。

## 分派与真实回传

```text
python scripts/launch_runtime.py enqueue --project "项目运行目录" --spec "分派侧页.json"
python scripts/launch_runtime.py submit --project "项目运行目录" --task "实际task_id" --result "原始成果.json" --receipt "实际执行回执.json"
```

分派spec包含agent_name、batch_id、input和gate_refs。input原样使用对应角色提示词的业务输入，程序分配实际task_id、run_id、output_path。gate_refs及运行回执放侧页，不加入传统业务成果JSON。

```json
{
  "agent_name": "proposal_extract",
  "batch_id": "B001",
  "input": {},
  "gate_refs": [
    {"gate_id": "G1", "version": "v1", "item_ids": ["资料条目编号"]}
  ]
}
```

上例input空对象不可执行，须由主控填真实任务。资料/规则准备角色无前置gate；四路识别须绑定已批准且实际准备就绪的G1资料。判定须有四路可用原始成果及适用G1/G2条目；程序注入完整成果位置、有效采用清单和G2规则快照，不转交主控压缩摘要。

status.pending_tasks中的input_ref、prompt_ref、envelope_ref指向固定输入、角色指令和传输侧页。默认调用execute或execute-batch，由适配器复制本角色输入、实际验证权限、启动独立专业进程并生成host回执。不要给识别者整个SKILL、整段主控历史、其他路结果或判定规则；摘要不替代原始材料。

任务侧页中confirmation_conditions须实际传达给执行者，不能丢失用户限制。自然语言限制由专业角色遵循，程序不声称已自动理解全部条件；改变可读范围的条件须形成精确获准来源范围后分派。

默认沙箱回执由适配器生成并保存在host私有区，不能手工填executed或sandbox_verified。以下回执例仅用于显式旧模式codex_external_bridge，由主控据原生工具记录生成；不用于硬隔离任务：

```json
{
  "task_id": "实际任务编号",
  "run_id": "实际运行编号",
  "agent_name": "proposal_extract",
  "input_sha256": "实际计算值",
  "result_sha256": "实际计算值",
  "context_id": "宿主实际返回的独立上下文标识",
  "history_inheritance": false,
  "executed": true,
  "executor": "codex-collaboration"
}
```

这份回执证明宿主记录的执行经过，不能自动证明事实正确或强文件隔离。重复上下文、身份或哈希错误不得放行。submit返回后必须检查任务状态和returns；结构退回可能已归档原始响应，命令收到事件不等于交接通过。格式修复按退回范围处理，实质重新识别则新上下文、新运行。

quality_review任务侧页指定scan_reviews_path时，复核者还须实际保存{"scan_reviews":[...]}扫描侧页。每条扫描为{run_id,scan_id,review_result,note}，状态accepted/revise/limited/not_reviewed，与本次分派lead_scan一一对应。主控读取完整侧页，将其中数组原样放入receipt.scan_reviews；不增改专业判断。业务JSON的scope_coverage仍保留范围检查，这份侧页只是逐扫描采用与重审控制，不改变schema1.0。未生成侧页时应退回该复核任务，不能由主控从一句总体说明猜分每项状态。

## G1/G2的可读确认和有效快照

```text
python scripts/launch_runtime.py propose-gate --project "项目运行目录" --manifest "确认清单.json"
python scripts/launch_runtime.py confirm --project "项目运行目录" --record "真实回复回执.json"
```

manifest为{gate_id,version,title,items,producer_task_ids}；items每项为{item_id,label,payload}。G1由真实read_adjust成果，G2由真实base_rule成果产生；已有外部依据可用basis_refs指向实际文件及哈希。basis仅提供确认内容来源，不等于用户批准。

G1条目payload包括获准batch_ids、source_refs及准备信息。source_refs保留file_id、path、sha256、assigned_scope，必须与实际分派精确对应。批准范围、准备状态和实际读取分别登记；“确认处理方案”不能写成已读取。派生件必须有原件映射，新增或改变授权范围不能靠改状态绕过确认。

确认资料未提供且授权继续时，可显式登记availability:not_provided，path及sha256为null，保留缺项清单编号和确切范围；这不是一个已经存在的原件。对应角色如实返回partial及not_provided覆盖，不能生成已读事实或verified来源。判定保留材料限制，不把缺资料认定为未履行。

G2条目payload保存实际rule_id、version、完整规则要求、来源和主体期间，不只保存编号。中文页面须呈现采用条款、参数和例外，未决问题分列并说明影响。使用[中文G1模板](../templates/g1-confirmation.md)和[中文G2模板](../templates/g2-confirmation.md)，先给实际链接、打开可读文件，再请求真实用户回复；用户无需看技术JSON。

base_rule的source_refs仍为source_key/file_id/version/locator/quote原文引用，不能改造成文件对象。确认清单另提供source_files来源映射（或从生产任务实际source_refs解析），其中每项保留source_key、file_id、version、path、sha256及assigned_scope。运行器按引用身份解析文件；源引用与文件映射分开，无法唯一对应时只修复相关映射。

确认回执至少包括confirmation_id、gate_id、version、manifest_sha256、decision、approved_item_ids、conditions、confirmed_by、authority_ref。decision为all/partial/conditional。全部确认明列全部实际条目；部分仅采用已批准项；条件中restriction保留限制，prerequisite未满足时相关条目不能使用。主控不得伪造批准人、回复来源或条件满足。

确认后展示中文回执，说明已批准范围、未采用项和条件。G2有效快照依据本次具体回复生成，旧候选pending只留历史。尚有具体规则解释问题时，必须说明specific_issue_ref及受影响事项，不能用内部映射或笼统版本问题恢复为“所有规则待确认”。资料日期/主体缺证与规则批准状态分开。

判定仍输出“规则待确认”时，由判定角色交付具体问题侧页，主控原样记录receipt.specific_rule_issues，按decision_id映射到{specific_issue_ref,reason,affected_scope}；不得仅填写一个布尔值或由主控猜写解释。无论rule_id是正式编号、目录编号还是null，每项都需具体依据，防止以技术映射缺口重新堵住全部已确认规则。确定性判定的rule_basis须对应当前实际规则编号、版本及确认记录。

G1批准后纯准备状态更新使用mark-ready --project "项目运行目录" --request "准备记录.json"，绑定gate_id、version、item_id、ready:true及真实evidence_refs（每项path、sha256）。它不改变已批准来源内容与授权范围，不重新要求人工确认相同范围；真正新增来源或扩大范围另走确认。

## 局部返工与立即复核

```text
python scripts/launch_runtime.py revise --project "项目运行目录" --request "局部退回单.json"
```

request包括reason、professional_basis_ref和spec。professional_basis_ref指向实际专业退回意见及哈希；spec.replaces明确把新collection:id映射到旧unit_id。spec.item_dependencies可记录某结果具体依赖的上游有效单元；未证明独立时采用保守批级依赖。不要为了保留旧pass捏造“不受影响”依据。

唯一有效采用以unit_id登记selected result_ref、被替换历史、dependencies及review_status。局部新旧单元可并存，不以“最新run”删除整批。原件、规则或事实变更后沿实际依赖使相关结果失效，只有明确不受影响的单元保留。

具体规则换版按条目依赖传播：有明确rule_id的判定只绑定对应G2条目，纯事实关联不自动绑定整份规则包；依赖不清的比较保守等待专业核对。旧复核待办因局部失效取消时，图为仍有效且尚待复核的条目生成续接待办，并在review_partition侧页记录原总体、保留单元、失效单元及另行重做原因。原full任务续接仍为full，不作为抽样；已批准sample任务保持原授权边界。主控必须把续接范围实际传给复核者，不能只保留单元而丢掉待办。

判定交接通过后图立即生成quality_review待办，主控优先分派。新上下文取得完整成果、相同依据版本、获准来源和采用边界；不传判定内部分析。默认full，逐项记录accepted/revise/limited/not_reviewed并核验扫描覆盖；结构检查和计数相等不替代实质复核。

改抽样或缩小范围：propose-gate建立REVIEW:对应任务编号的具体方案，说明总体、样本unit_ids、selection_basis和limitations；取得真实确认后用scope-review --request变更。未获确认不能直接更改review_mode或省略条目。修订后独立核验变化和采用边界，不能直接复用旧接受状态。

## 停止、恢复和交付

```text
python scripts/launch_runtime.py close-partial --project "项目运行目录" --reason "用户要求停止或实际限制"
python scripts/launch_runtime.py resume --project "项目运行目录"
```

阶段关闭保留待做范围和全部历史，不视为业务全部完成。交付按effective_results取数，将reviewed_results与initial_or_limited_results分开；抽取单元的not_applicable是复核状态，不是业务“不适用”结论。返回复核意见须完成局部闭环或明确限制；正式问题认定与定级还须评价人员最终确认。

最终签认使用FINAL确认单，payload列明具体unit_ids；先展示实际交付范围，再保存真实人工回复。复核接受不会自动生成最终签认。后续对应依赖变更时最终签认也须标记失效或明确保留范围。

局部修订不改包内规则，不覆盖原件。状态图不承担OCR或模型推理；本包沙箱适配器负责真实专业执行和权限检查，模型网关只做推理。langchain-openai为可选SDK，安装/导入不构成能力验收。扫描、老Office及视觉/OCR能力以本角色实际工具结果为准。
