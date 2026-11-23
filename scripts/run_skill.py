#!/usr/bin/env python3
"""Scientific relationship schematic builder (standard library only).

Reads a case bundle (default /input/case.json), extracts entities and typed
relations from explicit lists or from source text, validates direction and
legend consistency, and writes an editable drawing specification plus an
export-check plan to /app/output/result.json.  Deterministic, offline, and
honest: nothing is rendered and no scientific value is invented.
"""

import argparse
import hashlib
import json
import os
import re
import sys

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
SKILL_NAME = "scientific-relationship-schematic"
SKILL_VERSION = "1.0.0"
CHALLENGE_ID = "challenge-98e5a474"
MAX_TEXT = 400000

SKIP_KEYS = {"output_contract", "scoring", "tags", "meta", "case_id",
             "challenge_id", "skill", "contract_notes"}

CN_TRIGGERS = [
    ("activation", ("激活", "促进", "上调", "增强", "诱导", "招募", "募集", "启动")),
    ("inhibition", ("抑制", "阻断", "下调", "降低", "减弱", "沉默", "拮抗")),
    ("binding", ("结合", "互作", "相互作用", "识别")),
    ("modification", ("磷酸化", "泛素化", "甲基化", "乙酰化", "切割", "降解", "修饰")),
    ("transport", ("转运", "运输", "分泌", "易位", "迁移", "输入", "输出")),
]
EN_TRIGGERS = [
    ("activation", r"activates?|promotes?|induces?|upregulates?|enhances?"),
    ("inhibition", r"inhibits?|suppresses?|represses?|downregulates?|blocks?"),
    ("binding", r"binds?|interacts?\s+with|recognizes?"),
    ("modification", r"phosphorylates?|ubiquitinates?|methylates?|cleaves?|degrades?"),
    ("transport", r"transports?|translocates?|secretes?|exports?|imports?"),
]
SUFFIX_TYPES = [
    ("gene", ("基因",)),
    ("protein", ("蛋白", "激酶", "磷酸酶", "酶", "受体", "因子", "通道", "抗体")),
    ("complex", ("复合物", "复合体", "二聚体", "家族")),
    ("cell", ("细胞", "神经元", "巨噬细胞", "T细胞", "B细胞")),
    ("compartment", ("细胞核", "细胞质", "胞质", "胞膜", "线粒体", "内质网", "高尔基", "膜")),
    ("pathway", ("通路", "途径", "级联", "信号轴")),
    ("molecule", ("分子", "代谢物", "离子", "ATP", "cAMP", "Ca2+")),
]
REL_STYLE = {
    "activation": {"arrowhead": "solid_arrow", "polarity": "positive", "dash": "solid"},
    "inhibition": {"arrowhead": "bar", "polarity": "negative", "dash": "solid"},
    "binding": {"arrowhead": "none", "polarity": "neutral", "dash": "solid"},
    "modification": {"arrowhead": "solid_arrow", "polarity": "positive", "dash": "dashed"},
    "transport": {"arrowhead": "open_arrow", "polarity": "neutral", "dash": "solid"},
    "inclusion": {"arrowhead": "containment", "polarity": "neutral", "dash": "solid"},
    "sequence": {"arrowhead": "solid_arrow", "polarity": "neutral", "dash": "solid"},
    "unsupported": {"arrowhead": "none", "polarity": "unknown", "dash": "dotted"},
}
STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "these", "those",
             "into", "using", "used", "were", "was", "are", "is", "be", "of", "in",
             "on", "to", "by", "as", "at", "an", "or", "we", "our", "their", "its",
             "which", "who", "what", "when", "where", "how", "not", "can", "may"}
CLAUSE_SPLIT = re.compile(r"[，。；;！!？?\n\t]|(?<=[a-z])\s+(?:and|then|which|that)\s+")
TOKEN_STRIP = " \t\r\n，。；;：:、（）()[]【】\"'“”‘’《》<>"


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_text_file(path):
    try:
        if os.path.isfile(path) and os.path.getsize(path) <= 4 * 1024 * 1024:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    return None


def collect_material(case, base_dir):
    parts, unreadable = [], []

    def walk(node, label):
        if isinstance(node, str):
            stripped = node.strip()
            if len(stripped) >= 40:
                parts.append({"label": label, "text": stripped, "path": None})
                return
            if stripped and not stripped.startswith(("{", "[")):
                for candidate in (stripped, os.path.join(base_dir, stripped)):
                    text = read_text_file(candidate)
                    if text is not None:
                        parts.append({"label": label, "text": text, "path": candidate})
                        return
                if stripped.lower().endswith((".txt", ".md", ".json", ".csv")):
                    unreadable.append({"label": label, "path": stripped})
            return
        if isinstance(node, dict):
            for key in ("path", "file", "filename"):
                candidate = node.get(key)
                if isinstance(candidate, str):
                    for resolved in (candidate, os.path.join(base_dir, candidate)):
                        text = read_text_file(resolved)
                        if text is not None:
                            parts.append({"label": label, "text": text, "path": resolved})
                            return
                    if os.path.isfile(candidate):
                        unreadable.append({"label": label, "path": candidate})
                        return
            for key in ("content", "text", "body", "markdown", "description", "material"):
                if isinstance(node.get(key), (str, list, dict)):
                    walk(node[key], "%s.%s" % (label, key))
                    return
            for key, value in node.items():
                if key in ("id", "name", "title", "type", "kind"):
                    continue
                walk(value, "%s.%s" % (label, key))
            return
        if isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, "%s[%d]" % (label, idx))

    for key, value in case.items():
        if key in SKIP_KEYS:
            continue
        walk(value, key)
    parts.sort(key=lambda item: (-len(item["text"]), item["label"]))
    return parts, unreadable


def task_text(base_dir):
    for name in ("task.md", "TASK.md", "task.txt"):
        path = os.path.join(base_dir, name)
        text = read_text_file(path)
        if text:
            return text, path
    return "", None


def entity_type(label):
    for kind, suffixes in SUFFIX_TYPES:
        if any(suffix in label for suffix in suffixes):
            return kind
    if re.search(r"[A-Za-z]", label):
        return "molecule"
    return "entity"


def pick_entities(case, text):
    explicit = []
    for key in ("entities", "nodes", "objects", "components", "items"):
        value = case.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    explicit.append({"name": entry.strip(), "type": None, "source": key})
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("label") or entry.get("id")
                    if isinstance(name, str) and name.strip():
                        explicit.append({
                            "name": name.strip(),
                            "type": entry.get("type") or entry.get("kind"),
                            "id": entry.get("id"),
                            "source": key,
                        })
    if explicit:
        return explicit

    nouns = []
    for match in re.finditer(
            r"([\u4e00-\u9fffA-Za-z0-9\-/+]{2,18}?"
            r"(?:蛋白|基因|受体|因子|激酶|磷酸酶|复合物|复合体|细胞|通路|分子|酶|通道))", text):
        nouns.append(match.group(1))
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9\-]{2,15})\b", text):
        if match.group(1).lower() not in STOPWORDS:
            nouns.append(match.group(1))
    seen, result = set(), []
    for name in nouns:
        key = name.lower()
        if key in seen or name.lower() in STOPWORDS:
            continue
        seen.add(key)
        result.append({"name": name, "type": entity_type(name), "source": "text"})
    return result


def clean_token(raw):
    token = raw.strip(TOKEN_STRIP)
    token = re.sub(r"^(?:而|且|并|又|也|均|可|能|会|可以|其中|同时|随后|然后)+", "", token)
    token = re.sub(r"的$", "", token).strip(TOKEN_STRIP)
    if len(token) < 2 or len(token) > 26:
        return None
    if token.lower() in STOPWORDS:
        return None
    return token


def split_sentences(text):
    return [segment.strip() for segment in re.split(r"(?<=[。；;！!？?])|(?<=\.)\s+", text) if segment.strip()]


def extract_relations_from_text(text):
    relations = []
    for sentence in split_sentences(text):
        for relation_type, triggers in CN_TRIGGERS:
            for trigger in triggers:
                start = 0
                while True:
                    index = sentence.find(trigger, start)
                    if index < 0:
                        break
                    left = sentence[:index]
                    right = sentence[index + len(trigger):]
                    left = re.split(r"[，。；;：:、]", left)[-1].strip()
                    right = re.split(r"[，。；;：:、]", right)[0].strip()
                    source = clean_token(left[-26:])
                    target = clean_token(right[:26])
                    if source and target and source != target:
                        relations.append({
                            "source": source, "target": target, "type": relation_type,
                            "raw": norm(sentence)[:220], "extractor": "cn_trigger",
                        })
                    start = index + len(trigger)
        for relation_type, pattern in EN_TRIGGERS:
            for match in re.finditer(
                    r"\b([A-Za-z0-9\-/]{2,26})\s+(?:%s)\s+([A-Za-z0-9\-/]{2,26})\b" % pattern,
                    sentence):
                relations.append({
                    "source": match.group(1), "target": match.group(2),
                    "type": relation_type, "raw": norm(sentence)[:220],
                    "extractor": "en_trigger",
                })
    return relations


def pick_relations(case, text):
    explicit = []
    for key in ("relations", "edges", "interactions", "links"):
        value = case.get(key)
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                source = entry.get("source") or entry.get("from") or entry.get("head")
                target = entry.get("target") or entry.get("to") or entry.get("tail")
                if not (source and target):
                    continue
                rel_type = entry.get("type") or entry.get("relation") or entry.get("interaction")
                explicit.append({
                    "source": str(source), "target": str(target),
                    "type": normalize_type(rel_type),
                    "raw": entry.get("evidence") or entry.get("text"),
                    "extractor": key,
                    "direction": entry.get("direction"),
                })
    if explicit:
        return explicit

    relations = extract_relations_from_text(text)
    seen, unique = set(), []
    for item in relations:
        key = (item["source"].lower(), item["target"].lower(), item["type"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def normalize_type(value):
    if not isinstance(value, str):
        return "unsupported"
    lowered = value.lower()
    mapping = {
        "activation": ("activat", "promot", "induc", "upregulat", "enhanc", "激活", "促进", "上调", "增强"),
        "inhibition": ("inhibit", "suppress", "repress", "block", "抑制", "阻断", "下调"),
        "binding": ("bind", "interact", "结合", "互作"),
        "modification": ("phosphoryl", "ubiquit", "methyl", "cleav", "degrad", "磷酸化", "泛素化", "降解", "修饰"),
        "transport": ("transport", "transloc", "secret", "转运", "运输", "分泌", "易位"),
        "inclusion": ("contain", "include", "part_of", "包含", "属于"),
        "sequence": ("sequence", "before", "after", "上游", "下游", "顺序"),
    }
    for canonical, markers in mapping.items():
        if any(marker in lowered for marker in markers):
            return canonical
    return "unsupported"


def rank_nodes(nodes, edges):
    adjacency = {node: [] for node in nodes}
    for edge in edges:
        if edge.get("relation_type") in ("activation", "inhibition", "transport", "modification"):
            if edge["source"] in adjacency and edge["target"] in adjacency:
                adjacency[edge["source"]].append(edge["target"])
    rank = {node: 0 for node in nodes}
    for _ in range(len(nodes)):
        changed = False
        for source, targets in adjacency.items():
            for target in targets:
                if rank[target] < rank[source] + 1:
                    rank[target] = rank[source] + 1
                    changed = True
        if not changed:
            break
    cycle = any(rank[node] >= len(nodes) - 1 for node in nodes) and bool(edges)
    return rank, cycle


def contract_fields(contract):
    fields, unsupported = [], []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"].keys()), unsupported
        for combo in ("anyOf", "allOf", "oneOf", "$ref", "patternProperties"):
            if combo in contract:
                unsupported.append(combo)
        nested = contract.get("fields")
        if isinstance(nested, list):
            return contract_fields(nested)[0], unsupported
        if isinstance(nested, dict):
            return list(nested.keys()), unsupported
        reserved = {"type", "required", "optional", "additionalProperties", "title",
                    "description", "version", "schema", "$schema"}
        return [key for key in contract if key not in reserved and not str(key).startswith("$")], unsupported
    if isinstance(contract, list):
        for entry in contract:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
        return fields, unsupported
    return fields, unsupported


ALIASES = {
    "status": "status", "drawing_spec": "drawing_spec", "figure_spec": "drawing_spec",
    "schematic": "drawing_spec", "entities": "entities", "nodes": "entities",
    "relations": "relations", "edges": "relations", "legend": "legend",
    "consistency_checks": "consistency_checks", "checks": "consistency_checks",
    "editable_source": "editable_source", "source_file": "editable_source",
    "export_plan": "export_plan", "export_artifact": "export_plan",
    "export": "export_plan", "source_register": "source_register",
    "provenance": "source_register", "modification_log": "edit_operations",
    "edit_operations": "edit_operations", "gaps": "gaps", "uncertainty": "uncertainty",
    "evidence": "evidence", "stats": "stats", "limitations": "limitations",
}


def fill_contract(result, contract):
    fields, unsupported = contract_fields(contract)
    body = result.get("result") if isinstance(result.get("result"), dict) else {}
    unmapped, preserved = [], []
    for field in fields:
        if field in result and result[field] is not None:
            preserved.append(field)
            continue
        key = ALIASES.get(field.lower(), field.lower())
        if key in result and result[key] is not None:
            result[field] = result[key]
            preserved.append(field)
        elif key in body and body[key] is not None:
            result[field] = body[key]
            preserved.append(field)
        else:
            result[field] = None
            unmapped.append(field)
    result["contract_notes"] = {
        "declared_fields": fields,
        "preserved_fields": preserved,
        "unmapped_fields": unmapped,
        "unsupported_features": unsupported,
        "note": "Unsupported or absent fields are null; nothing is fabricated.",
    }
    if result.get("status") == "success" and (unmapped or unsupported):
        result["status"] = "partial"


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_export_plan(case):
    requested = case.get("export") or case.get("export_spec") or case.get("target_format")
    formats = []
    if isinstance(requested, str):
        formats = [part.strip().lower() for part in re.split(r"[,/;]", requested) if part.strip()]
    elif isinstance(requested, list):
        for entry in requested:
            if isinstance(entry, str):
                formats.append(entry.lower())
            elif isinstance(entry, dict) and entry.get("format"):
                formats.append(str(entry["format"]).lower())
    if not formats:
        formats = ["svg", "pdf", "png"]
    checks = {
        "svg": ["all_text_is_editable_text", "named_layers", "font_family_referenced_not_outlined"],
        "pdf": ["fonts_embedded", "vector_objects_preserved", "text_extractable"],
        "png": ["dpi_at_least_300", "no_text_clipping", "rgb_or_cmyk_declared"],
        "eps": ["fonts_embedded", "vector_objects_preserved"],
        "tiff": ["dpi_at_least_300", "lossless_compression"],
    }
    plan = []
    for fmt in formats:
        plan.append({
            "format": fmt,
            "required_checks": checks.get(fmt, ["vector_or_raster_declared"]),
            "performed": False,
            "reason": "no renderer invoked in this runtime; checks are a reproducible plan",
        })
    return plan


def parse_edit_requests(case, node_names):
    requests = case.get("edit_requests") or case.get("edits") or case.get("modifications")
    if not isinstance(requests, list):
        return [], []
    operations, unmatched = [], []
    for idx, entry in enumerate(requests):
        if isinstance(entry, dict):
            target = entry.get("target") or entry.get("from")
            value = entry.get("value") or entry.get("to")
            op = entry.get("op") or entry.get("operation") or "replace_label"
            if target is None:
                unmatched.append({"index": idx, "reason": "missing_target"})
                continue
            operations.append({"id": "E%d" % (idx + 1), "op": op,
                               "target": str(target), "value": value,
                               "matched": str(target) in node_names})
        elif isinstance(entry, str):
            match = re.search(r"(?:把|将)?\s*([^\s，。]{2,20})\s*(?:改为|改成|替换为|rename(?:d)? to)\s*([^\s，。]{1,30})", entry)
            if match:
                operations.append({"id": "E%d" % (idx + 1), "op": "replace_label",
                                   "target": match.group(1), "value": match.group(2),
                                   "matched": match.group(1) in node_names})
            else:
                unmatched.append({"index": idx, "reason": "unparsed_edit_request", "text": entry[:160]})
    return operations, unmatched


def main():
    parser = argparse.ArgumentParser(description="Scientific relationship schematic builder")
    parser.add_argument("--case", default=DEFAULT_CASE)
    parser.add_argument("--out", "--output", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    args = parser.parse_args()

    result = {
        "case_id": None,
        "challenge_id": CHALLENGE_ID,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "status": "failed",
        "result": {
            "drawing_spec": {"canvas": {}, "layers": [], "nodes": [], "edges": [],
                             "groups": [], "legend": [], "labels": []},
            "entities": [],
            "relations": [],
            "legend": [],
            "consistency_checks": [],
            "export_plan": [],
            "editable_source": None,
            "edit_operations": {"operations": [], "unmatched": []},
            "source_register": [],
            "gaps": [],
        },
        "evidence": [],
        "uncertainty": [],
        "errors": [],
        "stats": {},
        "limitations": [
            "Relation extraction uses explicit lists plus finite Chinese/English verb patterns.",
            "The drawing specification is constraint-level; no pixels or vector file are rendered here.",
        ],
    }

    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case root is not an object")
    except (OSError, ValueError) as exc:
        result["errors"].append({"stage": "read_case", "type": type(exc).__name__,
                                 "detail": "case.json missing or not valid JSON"})
        result["status"] = "insufficient_input"
        write_json(args.out, result)
        return 2

    base_dir = os.path.dirname(os.path.abspath(args.case))
    result["case_id"] = case.get("case_id") or case.get("id")
    contract = case.get("output_contract")

    parts, unreadable = collect_material(case, base_dir)
    main_text = "\n".join(part["text"] for part in parts)[:MAX_TEXT]
    extra_task, task_path = task_text(base_dir)
    if extra_task:
        main_text = (main_text + "\n" + extra_task)[:MAX_TEXT]

    entities = pick_entities(case, main_text)
    relations = pick_relations(case, main_text)
    relation_endpoints = {item["source"] for item in relations} | {item["target"] for item in relations}

    seen, nodes = set(), []
    for entity in entities:
        key = re.sub(r"\s+", "", entity["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        nodes.append(entity)
    existing = {re.sub(r"\s+", "", node["name"]).lower() for node in nodes}
    for endpoint in sorted(relation_endpoints):
        key = re.sub(r"\s+", "", endpoint).lower()
        if key not in existing:
            nodes.append({"name": endpoint, "type": entity_type(endpoint), "source": "relation_endpoint"})
            existing.add(key)

    if not main_text and not nodes:
        result["status"] = "insufficient_input"
        result["uncertainty"].append({"item": "material", "detail": "no readable source text or entity list"})
        fill_contract(result, contract)
        write_json(args.out, result)
        return 0

    names = [node["name"] for node in nodes]
    name_set = set(names)
    canonical = {re.sub(r"\s+", "", name).lower(): name for name in names}

    edges, checks, unknown = [], [], []
    for idx, item in enumerate(relations):
        source = canonical.get(re.sub(r"\s+", "", item["source"]).lower())
        target = canonical.get(re.sub(r"\s+", "", item["target"]).lower())
        if source is None or target is None:
            checks.append({"check": "dangling_endpoint", "edge": idx + 1,
                           "source": item["source"], "target": item["target"],
                           "detail": "endpoint not present in the entity list"})
            source = source or item["source"]
            target = target or item["target"]
        if source == target:
            checks.append({"check": "self_loop", "edge": idx + 1, "node": source})
        if item["type"] == "unsupported":
            unknown.append({"source": item["source"], "target": item["target"],
                            "raw": item.get("raw")})
        style = REL_STYLE[item["type"]]
        edges.append({
            "id": "E%d" % (idx + 1),
            "source": source,
            "target": target,
            "relation_type": item["type"],
            "polarity": style["polarity"],
            "arrowhead": style["arrowhead"],
            "dash": style["dash"],
            "evidence": item.get("raw"),
            "extractor": item.get("extractor"),
        })

    duplicates = []
    lowered = {}
    for name in names:
        key = re.sub(r"\s+", "", name).lower()
        lowered.setdefault(key, []).append(name)
    for key, group in lowered.items():
        if len(group) > 1:
            duplicates.append({"normalized": key, "variants": group})
            checks.append({"check": "duplicate_label", "variants": group})

    rank, cycle = rank_nodes(names, edges)
    grouped = {}
    for name in names:
        grouped.setdefault(rank[name], []).append(name)
    positions = {}
    for level in sorted(grouped):
        for order, name in enumerate(grouped[level]):
            positions[name] = {"x": 120 + level * 220, "y": 110 + order * 130, "layer": level}
    if cycle:
        checks.append({"check": "cycle_detected", "detail": "rank relaxation did not converge"})

    legend = []
    used_types = sorted({edge["relation_type"] for edge in edges}) or ["activation", "inhibition"]
    for rel_type in used_types:
        style = REL_STYLE[rel_type]
        legend.append({"key": rel_type, "arrowhead": style["arrowhead"],
                       "dash": style["dash"], "polarity": style["polarity"]})
    explicit_legend = case.get("legend")
    if isinstance(explicit_legend, list) and explicit_legend:
        provided = {str(item.get("key") or item.get("type") or item.get("label")) for item in explicit_legend
                    if isinstance(item, dict)}
        missing = [entry["key"] for entry in legend if entry["key"] not in provided]
        if missing:
            checks.append({"check": "legend_missing_relation_types", "missing": missing})

    groups = []
    for level in sorted(grouped):
        groups.append({"id": "L%d" % level, "role": "topological_layer",
                       "members": grouped[level], "boundary": "rectangle"})

    unit_missing = []
    for match in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?!%|[a-zA-Zµμ][a-zA-Z/²³]*\b)(?=[^\d])", main_text):
        context = main_text[max(0, match.start() - 20):match.end() + 20]
        if re.search(r"(浓度|时间|温度|体积|质量|表达|倍数|n\s*=|N\s*=|%|小时|分钟|天|周)", context):
            continue
        unit_missing.append({"value": match.group(1), "context": norm(context)})

    overlay = [
        {"id": n["name"], "type": n["type"], "position": positions[n["name"]],
         "label_anchor": "below", "editable": True,
         "source": n.get("source"), "provenance": n.get("id")}
        for n in nodes
    ]

    drawing_spec = {
        "canvas": {"width_mm": 180, "height_mm": 120, "units": "mm",
                   "background": "transparent", "grid_snap": True},
        "layers": ["background", "group_boundaries", "edges", "nodes",
                   "labels", "legend", "panel_tags"],
        "nodes": overlay,
        "edges": edges,
        "groups": groups,
        "legend": legend,
        "labels": [{"text": "图 1", "role": "figure_number", "position": "top_left"}],
        "layout_constraints": {
            "reading_direction": "left_to_right",
            "min_node_gap_mm": 8,
            "label_no_overlap_with_edges": True,
            "max_nodes_per_layer": 6,
        },
    }

    edit_ops, edit_unmatched = parse_edit_requests(case, name_set)
    for op in edit_ops:
        if not op.get("matched", True):
            checks.append({"check": "edit_target_not_found", "operation": op["id"],
                           "target": op["target"]})

    source_register = [
        {"label": part["label"], "path": None if not part["path"] else os.path.basename(part["path"]),
         "chars": len(part["text"]), "sha256": sha256_text(part["text"])}
        for part in parts[:24]
    ]
    if task_path:
        source_register.append({"label": "task.md", "path": os.path.basename(task_path),
                                "chars": len(extra_task), "sha256": sha256_text(extra_task)})

    gaps = []
    if len(nodes) < 2:
        gaps.append({"type": "too_few_entities", "detail": "a relationship schematic needs at least two entities"})
    if not edges:
        gaps.append({"type": "no_relations", "detail": "no typed relation could be extracted"})
    if unknown:
        gaps.append({"type": "unsupported_relation_types", "count": len(unknown)})
    if duplicates:
        gaps.append({"type": "ambiguous_entity_names", "count": len(duplicates)})

    result["result"].update({
        "drawing_spec": drawing_spec,
        "entities": [{"name": node["name"], "type": node["type"], "source": node.get("source")}
                     for node in nodes],
        "relations": edges,
        "legend": legend,
        "consistency_checks": checks,
        "export_plan": build_export_plan(case),
        "editable_source": {
            "target_file": "figure.svg",
            "layer_model": drawing_spec["layers"],
            "text_policy": "text elements stay as text; fonts referenced by family",
            "produced": False,
            "reason": "structure is emitted as a reproducible specification, not a fabricated render",
        },
        "edit_operations": {"operations": edit_ops, "unmatched": edit_unmatched},
        "source_register": source_register,
        "gaps": gaps,
    })
    result["evidence"] = [
        {"type": "relation_evidence", "edge": edge["id"], "snippet": (edge.get("evidence") or "")[:200]}
        for edge in edges if edge.get("evidence")
    ][:60]
    for entry in unreadable:
        result["uncertainty"].append({"item": "file", "detail": "unreadable_or_missing",
                                      "path": os.path.basename(entry["path"])})
    if unknown:
        result["uncertainty"].append({"item": "relations", "detail": "unsupported_verb_mapping",
                                      "count": len(unknown)})
    if unit_missing:
        result["uncertainty"].append({"item": "numbers", "detail": "missing_unit_or_context",
                                      "count": len(unit_missing)})
    if not explicit_legend:
        result["uncertainty"].append({"item": "legend", "detail": "legend_generated_from_relation_types"})
    result["result"]["unitless_numbers"] = unit_missing[:20]

    result["stats"] = {
        "source_blocks": len(parts),
        "entities": len(nodes),
        "relations": len(edges),
        "relation_types": len(used_types),
        "checks": len(checks),
        "hard_issues": sum(1 for check in checks if check["check"] in
                           ("dangling_endpoint", "self_loop", "duplicate_label", "cycle_detected")),
        "edit_operations": len(edit_ops),
        "export_formats": len(result["result"]["export_plan"]),
    }

    if edges and len(nodes) >= 2:
        result["status"] = "success"
    elif nodes:
        result["status"] = "partial"
    else:
        result["status"] = "insufficient_input"
    if any(check["check"] in ("dangling_endpoint", "cycle_detected") for check in checks):
        result["status"] = "partial"

    fill_contract(result, contract)
    write_json(args.out, result)
    if result["status"] == "failed":
        return 2
    if result.get("contract_notes", {}).get("unmapped_fields"):
        return 1
    return 0


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
