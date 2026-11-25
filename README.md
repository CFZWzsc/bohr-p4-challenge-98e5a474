# 科研示意图生成与编辑 Skill

从论文材料抽取实体、区室与关系，画成分层、可编辑的科研示意图（SVG），
并导出 300 dpi 的 `figure.png` 与 `figure.pdf`。Python 标准库实现，离线、确定性。

## 使用

```bash
python scripts/run_skill.py --case examples/demo-case/case.json \
    --out /app/output/result.json --work /app/work
```

- 输入：`case.json`、`task.md`、来源材料（实体清单或正文段落）。
- 输出：`result.json`（契约键 `case_id`/`status`/`editable_source`/`export_artifact`/
  `content_map`/`compliance_checks`/`exceptions`）、`figure.svg`、`figure-spec.json`、
  `figure.png`、`figure.pdf`。

## 设计要点

- **不编造**：实体与关系只取材料原文，每条边附原文句子；无依据的关系用虚线"关联"
  并在 `exceptions` 说明，绝不画反向抑制。
- **图面规范**：区室/泳道分层、关系线型与图例一一对应、色盲友好配色、文字全部 `<text>`。
- **可编辑**：语义化 `id`（`node-*`、`edge-*`、`legend`），节点坐标写入 `figure-spec.json`。
- **可核验**：`compliance_checks` 覆盖锚点、箭头标记、图例覆盖、画布包含、PNG 非空白像素。
- **确定性**：布局只依赖有序输入，无随机数与时间戳，双跑逐字节一致。

## 验证

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out /tmp/r1/result.json --work /tmp/r1
python scripts/run_skill.py --case examples/demo-case/case.json --out /tmp/r2/result.json --work /tmp/r2
# 两次产物 sha256 应完全一致
```
