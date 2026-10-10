# 合成行为验证

本目录原件为合成文本，不包含客户事实。生产任务不加载本目录或既有测试答案。

重跑时复制 fixtures 和 tasks 到独立运行目录，设置新的 run_id 和输出位置；任务内相对路径均相对于 Skill 根目录解析。每个提取角色只接收自身 prompts 文件、tasks 文件和对应 fixtures 原件，在新的独立上下文执行，不读取其他角色、results 或验证预期。随后由主控汇集结果交给新的判定上下文，再独立复核。

`check_artifacts.py` 只检查保存的结果，不调用模型；四路结果曾在 Codex 独立子任务中实际提取。宿主执行记录、能力边界与实际结果见[发布验证记录](../../references/release-validation.md)。不同运行环境需重新登记资料权限、模型及输出；现存结果仅作为本次回归证据。

在 Skill 根目录执行 `python -B -X utf8 validation/behavior/check_artifacts.py --stage extraction`，核查已完成的四路结果。不带参数时要求同时存在判定结果；本版本尚未完成该次判定运行，因此完整检查会明确失败，不代表四路提取检查失败。
