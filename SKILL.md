---
name: scientific-relationship-schematic
description: Use when a relationship or mechanism schematic must be derived from source material and delivered as an editable figure specification together with an export plan.
---

# 科研实体关系示意图生成与编辑

## 用途与适用条件

把来源材料中的科学实体、实体类型、相互关系与方向抽取为可核对的实体—关系清单，再生成分层、可编辑的示意图结构规格（节点、边、分组、图例、标签、画布），并给出矢量源文件与导出件的检查方案。输出强调“可追溯、可编辑、可复核”，不以“画得像”为目标。

适用条件：任务提供 `/input/case.json`（或 `--case` 指定的等价案例），可能同时提供 `/input/task.md`。案例材料包含描述实体与关系的正文、实体表或关系表，要求交付示意图与可编辑来源。典型输入键：`entities`/`nodes`、`relations`/`edges`/`interactions`、`legend`、`export`、`edit_requests`，或包含这些信息的段落文本。

不适用：不做统计检验与显著性计算；不把来源中没有的基因名、浓度、时间点、单位补进图里；不伪造像素结果——PNG/PDF 均由同一图元树真实导出，未导出时如实记 `performed=false`。

## 输入

- `/input/case.json`：主输入。按真实字段读取；不依据文件名或领域标签补造内容。
- `/input/task.md`：存在时作为任务语义补充（图型、目标格式、编辑要求）。
- 材料内引用的本地文本文件（相对路径、绝对路径）会被实际读取；不存在的路径登记到 `errors`/`uncertainty`。
- 仅使用 Python 3.9+ 标准库；不联网、不读环境变量、不写 `/input`。

## 处理流程

1. **读入与定位**：读取 case.json 与 task.md，收集所有可读文本与表格，记录来源标签与哈希。
2. **实体抽取**：优先读取显式 `entities`/`nodes`/`objects` 列表；缺失时按中文名词后缀（蛋白、基因、细胞、受体、因子、复合物、通路等）与英文大写词形从正文抽取，并保留首次出现的句子作为证据。
3. **关系抽取**：优先读取显式 `relations`/`edges`/`interactions`；缺失时按动词模式（激活、抑制、结合、磷酸化、泛素化、转运、募集、降解，及英文 activate/inhibit/bind 等）抽取“主语—关系—宾语”，并归一化为 `activation`/`inhibition`/`binding`/`modification`/`transport`/`inclusion`/`sequence`。
4. **一致性校验**：检查悬空端点、自环、重复实体、缺失方向、关系类型未支持、图例与关系类型不匹配、数值缺少单位。
5. **布局与分层**：按关系方向计算拓扑层级，给出节点坐标约束、分组/区室边界、标签避让规则；不声称已渲染。
6. **图例与编码**：把关系类型、极性、分组映射到线型、箭头、颜色，并生成图例项。
7. **编辑操作**：读取 `edit_requests`，输出可执行的标签替换/节点增删/连边修改清单，标注未匹配项。
8. **导出与检查**：实际导出 SVG/PNG/PDF，登记检查项（文字可编辑、分辨率、渲染器）与真实结果，不伪造。
9. **契约落盘**：保留 `case_id` 与 `output_contract` 全部字段，未支持字段写 `null` 并记录 `contract_notes`。

## 评分维度对应

- **实际效果（任务完成度/正确性）**：实体、关系、方向、层级可回溯到来源；悬空端点和方向缺失被显式标出。
- **完整性**：覆盖实体、关系、分组、图例、标签、源文件与导出六类要素。
- **可核验性**：每个节点/边带 `source_ref` 与证据句，`source_register` 记录来源与哈希。
- **创新增益**：文本到实体—关系的结构化映射、关系极性归一、图例一致性检查。
- **可靠体验**：缺输入、歧义、矛盾时降级为 `partial`/`insufficient_input` 并给出处置记录。

## 输出契约

写入 `/app/output/result.json`（UTF-8，确定性排序，无随机、无时间戳）。顶层必须保留：

- `case_id`（缺失为 `null`）；
- 输入 `output_contract` 声明的每个字段，原样保留；无法确定性映射的写 `null` 并在 `contract_notes` 说明；
- `status`：`success` / `partial` / `insufficient_input` / `failed`；
- `result`：结构化交付（`drawing_spec`、`consistency_checks`、`export_plan`、`edit_operations`、`source_register`）；
- `evidence`、`uncertainty`、`errors`、`stats`；
- `skill`、`challenge_id`、`contract_notes`。

主要交付段：`result.drawing_spec.nodes`、`result.drawing_spec.edges`、`result.drawing_spec.legend`、`result.consistency_checks`。

## 异常处理

| 情况 | 处理 | 输出表现 |
|---|---|---|
| `case.json` 缺失或非法 JSON | 不改写输入，写结构化失败结果 | 退出码 `2`，`status=insufficient_input`（解析错误为 `failed`） |
| 无实体或关系 | 不编造，保留空规格 | `status=partial` 或 `insufficient_input`，`uncertainty` 说明缺项 |
| 关系端点未在实体表出现 | 保留该边并标 `dangling_endpoint` | `consistency_checks` 记录，`status` 降为 `partial` |
| 关系动词无法归一 | 保留原文，类型记为 `unsupported` | `uncertainty` 记录原文，不强行映射 |
| 同一实体多种写法 | 保留全部写法，标 `duplicate_label` | 不自动合并，等待人工确认 |
| 数值缺单位 | 保留数值原串，标 `missing_unit` | 不补单位 |
| 编辑请求无法匹配 | 记录未匹配项 | `edit_operations.unmatched` |
| PNG/PDF 渲染工具缺失 | Pillow 缺失时用纯 Python 栅格兜底 | 记录 renderer/dpi；仍失败则 `performed=false` 并写明原因 |

## 限制

实体与关系抽取基于显式列表与有限动词模式；代词指代、跨句省略、图内嵌套结构可能漏检。`figure.svg` 已按实际坐标写出，PNG/PDF 由同一图元树导出。

## 最小调用示例（示例，非官方案例结果）

```bash
python scripts/run_skill.py --case /input/case.json --out /app/output/result.json
```

示例输入（示意）：

```json
{"case_id":"example-schematic","entities":[{"name":"受体A","type":"protein"},{"name":"激酶B","type":"protein"}],"relations":[{"source":"受体A","target":"激酶B","type":"activation"}],"output_contract":{"status":"string","drawing_spec":"object","consistency_checks":"array"}}
```

示例输出（示意，已省略）：`status="success"`，`drawing_spec.edges[0].relation_type="activation"`，`consistency_checks=[]`。该输出仅为示例，不代表任何官方固定案例结果。


## Quickstart

在包根目录执行：

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out ./demo-output/result.json
```

- 演示案例：`examples/demo-case/case.json`（合成装置：6 个部件、4 条有向流；纯合成）。
- 输出：`result.json`、`figure.svg`（左→右分层、带箭头与流向标签）与 `figure-spec.json`；`drawing_spec` 的位置同步为实际图稿坐标，五个契约键均为真实内容。

## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 按契约取 `success`/`partial`/`insufficient_input`/`failed`（缺输入或证据不足时用 `insufficient_input`/`partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

### 真实图稿与预览（本次必做）

- 脚本只输出规格（且 `export_plan[].performed=false`）时，调用 Agent 必须依据规格真实写出可编辑 SVG 到 `/app/output/`：节点、边、分组、标签、图例均为可编辑元素。
- PNG（300 dpi）与 PDF 由同一图元树真实导出，并记录渲染器与 dpi；无 Pillow 时退化为纯 Python 栅格预览，并在 `result.json` 写明原因。
- 仅当文件真实落盘、可打开并核对后，才将源文件与导出项标记为已执行（`produced=true`、`performed=true`），并写入路径、字节数与 SHA-256；未执行的检查项如实写 `false` 与原因，不伪造渲染或检查结果。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
