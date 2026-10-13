# Windows逐任务沙箱执行

本参考是包1.2.0的平台适配层，业务提示词、G1/G2、判定规则和成果schema不因执行方式改变。原生`spawn_agent`与本适配器是两种执行入口；当前默认使用本适配器，不能把外部任务夹当作原生子智能体的权限设置。

## 主控运行入口

项目配置默认`execution_mode: windows_appcontainer`。先运行`launch_runtime.py doctor`检查控制依赖，再按既有流程enqueue。doctor不会创建沙箱或证明隔离成功；execute会真实检查。

```text
python scripts/launch_runtime.py execute --project "项目运行目录" --task "实际task_id"
python scripts/launch_runtime.py execute-batch --project "项目运行目录" --task "通知task_id" "议案task_id" "过程task_id" "决议task_id" --max-workers 4
```

专业执行可以并行；读取图快照时有限等待控制锁，提交和采用仍串行。每次执行是新AppContainer profile、新安全身份、新进程和全新模型上下文。返回实际执行、结构交接及业务状态；`ok`不能由主控猜写。失败只保留本项待办，不重做已通过的其他项。

项目配置可明确提供model，否则采用本机Codex配置中的model。主控真实文件登录仅在主控内存参与模型鉴权，不传入角色配置、环境或资料包。不启动网络监听，不添加回环豁免，不索要另一份API密钥。只有固定OpenAI Responses推理请求经过host网关，网关不执行任何文件、命令、浏览器或委派操作；角色没有网络能力。

## 实际边界与角色输入

| 位置/角色 | 可读 | 可写 |
|---|---|---|
| 资料准备 | 获准目录的独立副本、中性分类要求 | 本任务索引、确认页和获准派生件 |
| 依据准备 | 交给本角色的制度副本 | 本任务规则候选及确认页 |
| 四路事实角色 | 自己的完整、物理分离阅读件及本角色提示词 | 自己的完整JSON、必要侧页 |
| 判定 | 四路完整采用成果、对应证据、当前G2有效规则快照 | 本批判定及具体待核问题侧页 |
| 独立复核 | 被复核成果、完整事实、同版规则和获准证据 | 逐项复核及扫描覆盖侧页 |
| 主控私有区 | 主控可读；专业角色不可读 | 主控回执、映射、审计和采用结果 |
| 运行依赖 | 只读Python及固定Office/PDF依赖 | 不可修改；Windows为本任务创建的私有临时区可写 |

每个role/input只授予当前AppContainer SID读取，role/output仅授予其写入；host目录不授予该SID。Windows中通常公开的系统文件/依赖不代表客户材料授权。每次执行同时实测自己副本、项目登记的其他角色原件/副本、主控回执及输入写入；材料带更宽的继承权限导致越界可读时停止，不修改客户原件ACL来掩盖失败。

执行器在系统临时目录创建短路径、唯一角色工作区，避免Office/PDF依赖遇到Win32长路径限制。项目sandbox_runs仍保留唯一attempt的host审计区；stage_map登记原件与实际工作区位置，长文件名可用短实体名并保留原件定位。目录来源的文件始终留在该角色的指定枚举根内。运行依赖清单持久化到host；临时工作区保留供审计，profile删除后后续角色不能复用其身份。仅改变新建目录的ACL，不修改临时目录祖先或全局长路径设置。

四个工具`read_file/list_directory/write_file/run_command`都由沙箱内专业进程执行。命令子进程先以暂停状态创建、核对相同AppContainer SID后才恢复；父级Job负责超时终止整棵进程树。没有原生Codex文件/终端/浏览器/MCP/connector工具的旁路。资料本身的快捷方式、junction、symlink和嵌套挂载不授予访问；导入输出拒绝重解析点及硬链接。

## 冻结、范围与回传

enqueue冻结input、prompt、资料hash及sandbox合同。执行器只复制角色契约明确登记的文件：四路不能用多余的extraction_results键读取其他路；quality_review只接受正式judge_results/extract_results引用。source.origin_map及origin_source只是原件定位，投影时原样保留，不增加读取权限。

强模式只能把**实际完整阅读件**交给角色。`assigned_scope=all/whole_file/full/全文/全部/整份`表示该阅读件全部可读。只写“原件第1页”不能阻止第2页被读；须先物理切分并保存原件位置映射，再按既有G1授权/准备机制登记。无法可靠物理隔离时保留待准备，不把整份混合文件给多个角色。

staged_input将实际读取/输出路径投影到本任务目录，stage_map保留原件hash和路径。原始模型JSON保留；主控仅按冻结映射恢复已登记路径，不增删事实字段。四路schema不添加input_snapshot；有该字段的角色回填实际收到的完整输入。最终消息与已写业务JSON不同则阻断并保留双方证据，不能择一覆盖。

专业模型最终只需输出一次完整JSON；worker原样保存业务路径和final_message。派生阅读件、扫描和规则疑问侧页可用write_file独立保存。结果经host私有回执绑定task/run、真实SID/PID、独立上下文、输入/结果hash及执行审计，再由图校验、采用和安排复核。脚本模拟推理只作软件测试，不能生成可采用的真实模型执行回执。

执行失败保留failed_attempt，成功后删除唯一临时profile；不清理原始资料，不改全局Codex权限，不改变其他角色的文件ACL。结果文件保留只给已删除的SID旧权限和主控权限，后续角色取得新副本而不是复用旧SID。

## 发言归属

message_provenance由宿主登记真实说话者、任务实例、收件人、内容种类和出处。原文与哈希保留，角色不能在payload自称用户或主控。定向任务注明“主控指派给你”；第三方报告注明生产角色；来源引文始终`trusted_user_authorization:false`。read_file实际返回也附此信息，未知依赖数据不猜作者。

只有同一真实实例/上下文的assistant历史保留assistant身份；其他实例的“我已确认”是它的报告。用户真实批准、主控指派、规则快照、专业报告和原文引文分别处理。不要为了第二人称改写原件、专业事实或报告；包装说明与原话分开。这些控制防止来源和授权被程序升级，仍须业务复核检验模型有没有误解内容。

## 本机兼容性和失败

Windows AppContainer由系统提供，当前使用Python3.12运行时。现有stock Codex CLI在本机AppContainer内的DOS路径规范化失败，因此本模式不用CLI当专业executor，也不放宽全局Windows对象权限绕行。Codex主控仍管理任务，专业模型由沙箱内独立agent loop执行。

Office/PDF依赖使用固定白名单副本，禁止整个宿主site-packages、用户配置或.pth文件被装入角色。现代DOCX/XLSX/PPTX和PDF文本能力须实际验证；扫描PDF还须渲染/OCR或视觉方法实际可用，空文本不是已读。老Office、加密或损坏文件能力不足时记录unreadable/partial，不能改成业务缺陷。

模型服务超载、登录失效、权限/格式错误或网络故障均保留具体安全诊断和待办。有限重试仅针对失败项，使用新身份/上下文；不改变材料范围、不制造结果，不静默切模型或降级权限。旧1.1.0项目不会因包升级自动变硬隔离；需新建按本模式冻结的任务或保留明确的旧模式限制。
