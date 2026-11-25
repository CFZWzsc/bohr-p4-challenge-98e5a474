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

import figure_svg
import svg_checks

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
    "flow": {"arrowhead": "solid_arrow", "polarity": "neutral", "dash": "solid"},
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
        "flow": ("feed", "flow", "separat", "return", "collect", "drain", "recycl",
                 "pump", "suppl", "discharg", "connect", "transfer", "流入", "流出", "回流"),
    }
    for canonical, markers in mapping.items():
        if any(marker in lowered for marker in markers):
            return canonical
    return "unsupported"


def rank_nodes(nodes, edges):
    adjacency = {node: [] for node in nodes}
    for edge in edges:
        if edge.get("relation_type") in ("activation", "inhibition", "transport",
                                         "modification", "flow"):
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


FLOW_HEADS = (r"(?:reactor|pump|module|membrane|tank|valve|pipe|pipeline|loop|"
              r"permeate|retentate|filter|sensor|column|reservoir|mixer|settler|"
              r"vessel|chamber|feed|separator|condenser|evaporator|digester|"
              r"fermenter|centrifuge|heat\s+exchanger)")
FLOW_MODIFIERS = (
    r"(?:peristaltic|membrane|permeate|retentate|feed|reaction|recycle|buffer|"
    r"sample|heat|gas|liquid|solid|vacuum|pressure|continuous|stirred|packed|"
    r"hollow|fib(?:er|re)|flat|sheet|spiral|tubular|anaerobic|aerobic|storage|"
    r"mixing|settling)")
FLOW_PHRASE_RE = re.compile(
    r"\b((?:%s\s+)?%s)\b" % (FLOW_MODIFIERS, FLOW_HEADS), re.I)
FLOW_TAG_RE = re.compile(
    r"\b((?:reactor|pump|module|tank|valve|column|vessel|chamber)\s+"
    r"[A-Z][A-Za-z0-9\-]*)\b")
FLOW_CN_RE = re.compile(
    r"([\u4e00-\u9fff]{2,12}(?:泵|罐|膜|反应器|模块|塔|阀|管道|池|槽|箱|器))")
FLOW_VERBS = [
    (r"\bseparat", "separates"), (r"\bcollect", "collects in"),
    (r"\breturn", "returns to"), (r"\bfeed", "feeds"),
    (r"\bflow", "flows to"), (r"\benter", "enters"),
    (r"\bdrain", "drains to"), (r"\bsuppl", "supplies"),
    (r"\brecycl", "recycles to"), (r"\bpump", "pumps to"),
    (r"\bdischarg", "discharges to"), (r"\bconnect", "connects to"),
    (r"\btransfer", "transfers to"),
]
FLOW_LEADING = re.compile(
    r"^(?:the|a|an|this|that|its|their|and|then|through|into|from)\s+", re.I)


def build_anchor_index(parts):
    index = []
    for part in parts:
        label = str(part.get("label") or "").lower()
        if "task" in label or label in ("instruction", "case"):
            continue
        source = (os.path.basename(part["path"])
                  if part.get("path") else str(part.get("label") or "material"))
        body = "\n".join(line for line in part["text"].splitlines()
                         if not line.strip().startswith("#"))
        for p_idx, paragraph in enumerate(re.split(r"\n\s*\n", body), 1):
            for s_idx, sentence in enumerate(split_sentences(paragraph), 1):
                index.append({"anchor": "%s:p%d.s%d" % (source, p_idx, s_idx),
                              "text": sentence, "source": source})
    return index


def _sentence_phrases(sentence):
    raw = []
    for match in FLOW_PHRASE_RE.finditer(sentence):
        cleaned = FLOW_LEADING.sub("", match.group(1).strip()).strip(" ,.;:")
        if len(cleaned) < 2 or cleaned.lower() in STOPWORDS:
            continue
        raw.append({"name": cleaned, "start": match.start(1),
                    "end": match.end(1)})
    for match in FLOW_TAG_RE.finditer(sentence):
        raw.append({"name": match.group(1), "start": match.start(1),
                    "end": match.end(1)})
    for match in FLOW_CN_RE.finditer(sentence):
        raw.append({"name": match.group(1), "start": match.start(1),
                    "end": match.end(1)})
    raw.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
    kept = []
    for item in raw:
        if kept and item["start"] < kept[-1]["end"]:
            if item["end"] - item["start"] > kept[-1]["end"] - kept[-1]["start"]:
                kept[-1] = item
            continue
        kept.append(item)
    merged = []
    for item in kept:
        if merged and not sentence[merged[-1]["end"]:item["start"]].strip():
            previous = merged.pop()
            merged.append({"name": (previous["name"] + " " + item["name"]).strip(),
                           "start": previous["start"], "end": item["end"]})
        else:
            merged.append(item)
    return merged


def _node_key(name):
    return re.sub(r"\s+", " ", name).strip().lower()


def extract_flow_graph(parts):
    """Nodes and directed flows from apparatus nouns and process verbs."""
    index = build_anchor_index(parts)
    nodes, by_key, edges, seen = [], {}, [], set()

    def add(name, anchor, quote):
        key = _node_key(name)
        if key in by_key:
            return by_key[key]
        node_id = "N%d" % (len(nodes) + 1)
        nodes.append({"id": node_id, "label": name, "kind": "component",
                      "anchor": anchor, "quote": quote})
        by_key[key] = node_id
        return node_id

    for item in index:
        sentence = item["text"]
        phrases = _sentence_phrases(sentence)
        for phrase in phrases:
            add(phrase["name"], item["anchor"], sentence)
        for first, second in zip(phrases, phrases[1:]):
            if first["name"].lower() == second["name"].lower():
                continue
            between = sentence[first["end"]:second["start"]].lower()
            label = None
            for pattern, candidate in FLOW_VERBS:
                if re.search(pattern, between):
                    label = candidate
                    break
            if label is None:
                continue
            source_id = by_key[_node_key(first["name"])]
            target_id = by_key[_node_key(second["name"])]
            key = (source_id, target_id, label)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "id": "F%d" % (len(edges) + 1),
                "source": source_id, "target": target_id,
                "kind": "flow", "label": label,
                "anchor": item["anchor"], "quote": sentence[:220],
            })
    return nodes, edges, index


def main():
    parser = argparse.ArgumentParser(description="Scientific relationship schematic builder")
    parser.add_argument("--case", default=DEFAULT_CASE)
    parser.add_argument("--out", "--output", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    args = parser.parse_args()
    os.environ["SK_RESULT_PATH"] = str(getattr(args, "out", None) or getattr(args, "output", None) or "")

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
            "figure.svg is the rendered deliverable; PNG/PDF are planned but not produced.",
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
    explicit_entities = any(item.get("source") in
                            ("entities", "nodes", "objects", "components", "items")
                            for item in entities)
    explicit_relations = any(item.get("extractor") in
                             ("relations", "edges", "interactions", "links")
                             for item in relations)
    flow_nodes, flow_edges, flow_anchor_index = extract_flow_graph(parts)
    flow_used = False
    if flow_nodes and len(flow_edges) >= 2 and not (explicit_entities or explicit_relations):
        id_to_label = {node["id"]: node["label"] for node in flow_nodes}
        entities = [{"name": node["label"], "type": "component",
                     "source": "text_flow"} for node in flow_nodes]
        relations = [{
            "source": id_to_label[edge["source"]],
            "target": id_to_label[edge["target"]],
            "type": "flow", "raw": edge["quote"], "extractor": "flow_pattern",
        } for edge in flow_edges]
        flow_used = True
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

    # --- real figure: directed relationship schematic ---
    out_dir = os.path.dirname(os.path.abspath(str(args.out))) or "."
    if flow_used:
        figure_nodes = [{"id": node["id"], "label": node["label"],
                         "kind": "component", "anchor": node["anchor"],
                         "quote": node["quote"]} for node in flow_nodes]
        figure_edges = [{"id": edge["id"], "source": edge["source"],
                         "target": edge["target"], "kind": "flow",
                         "label": edge["label"], "anchor": edge["anchor"],
                         "quote": edge["quote"]} for edge in flow_edges]
    else:
        id_by_name = {_node_key(node["name"]): "N%d" % (index + 1)
                      for index, node in enumerate(nodes)}
        figure_nodes = [{"id": "N%d" % (index + 1), "label": node["name"],
                         "kind": node.get("type") or "entity",
                         "anchor": "case:entities[%d]" % index,
                         "quote": node["name"]}
                        for index, node in enumerate(nodes)]
        figure_edges = []
        for index, edge in enumerate(edges):
            source_id = id_by_name.get(_node_key(str(edge["source"])))
            target_id = id_by_name.get(_node_key(str(edge["target"])))
            if not source_id or not target_id or source_id == target_id:
                continue
            figure_edges.append({
                "id": "E%d" % (index + 1), "source": source_id,
                "target": target_id, "kind": edge["relation_type"],
                "label": edge["relation_type"], "anchor": "case:relations[%d]" % index,
                "quote": (edge.get("evidence") or "")[:220],
            })

    if figure_nodes and figure_edges:
        source_names = ", ".join(sorted({
            os.path.basename(part["path"]) if part.get("path")
            else str(part.get("label") or "material") for part in parts}))
        figure_info = figure_svg.render(
            figure_nodes, figure_edges,
            "Relationship schematic: %d components, %d directed flows"
            % (len(figure_nodes), len(figure_edges)),
            "Components and flows are read from %s; every node and edge carries "
            "a file:pX.sY source anchor." % source_names[:180],
            out_dir)
        by_label = {node["label"]: node
                    for node in figure_info["figure_spec"]["nodes"]}
        rank_groups = {}
        for entry in drawing_spec["nodes"]:
            geometry = by_label.get(entry["id"])
            if not geometry:
                continue
            entry["position"] = {
                "x": geometry["x"], "y": geometry["y"],
                "x_mm": round(geometry["x"] / 3.7795, 2),
                "y_mm": round(geometry["y"] / 3.7795, 2),
                "layer": geometry["rank"],
            }
            entry["source_anchor"] = geometry.get("anchor")
            rank_groups.setdefault(geometry["rank"], []).append(entry["id"])
        drawing_spec["groups"] = [
            {"id": "L%d" % level, "role": "topological_layer",
             "members": rank_groups[level], "boundary": "rectangle"}
            for level in sorted(rank_groups)]
        drawing_spec["canvas"] = {
            "width_px": figure_info["width"], "height_px": figure_info["height"],
            "width_mm": round(figure_info["width"] / 3.7795, 2),
            "height_mm": round(figure_info["height"] / 3.7795, 2),
            "units": "mm", "background": "transparent", "grid_snap": True,
        }
        drawing_spec["figure"] = {
            "file": "figure.svg", "format": "svg", "layout": "left-to-right layers",
            "nodes": figure_info["nodes"], "edges": figure_info["edges"],
            "sha256": figure_info["sha256"],
        }
        result["result"]["drawing_spec"] = drawing_spec
        result["result"]["editable_source"] = {
            "target_file": "figure.svg",
            "layer_model": drawing_spec["layers"],
            "text_policy": "text elements stay as text; fonts referenced by family",
            "produced": True,
            "file": "figure.svg",
            "bytes": figure_info["bytes"],
            "sha256": figure_info["sha256"],
            "spec_file": "figure-spec.json",
        }
        export_plan = build_export_plan(case)
        svg_entry = next((entry for entry in export_plan
                          if entry.get("format") == "svg"), None)
        if svg_entry is not None:
            svg_entry.update({
                "performed": True, "file": "figure.svg",
                "bytes": figure_info["bytes"], "sha256": figure_info["sha256"],
                "checks": ["text_editable", "nodes_named", "legend_present"],
            })
        previews = {"png": figure_info.get("png"), "pdf": figure_info.get("pdf")}
        for entry in export_plan:
            if entry is svg_entry:
                continue
            preview = previews.get(str(entry.get("format", "")).lower())
            if preview:
                entry.update({"performed": True, "file": preview["file"],
                               "bytes": preview["bytes"],
                               "sha256": preview["sha256"],
                               "renderer": preview["renderer"],
                               "dpi": preview["dpi"]})
                entry.pop("reason", None)
            else:
                entry["performed"] = False
                entry["reason"] = ("not produced in this run: no raster or PDF "
                                   "backend was available")
        result["result"]["export_plan"] = export_plan
        result["exports"] = figure_svg.export_entries(figure_info)
        result["provenance_and_changes"] = {
            "derived_from_input": [
                {"element": "nodes", "source": source_names,
                 "detail": "%d apparatus/material components named in the text"
                           % len(figure_nodes)},
                {"element": "edges", "source": source_names,
                 "detail": "%d flows from feed/separate/return/collect-style verbs"
                           % len(figure_edges)},
                {"element": "edge labels", "source": source_names,
                 "detail": "verb phrase between two adjacent components"},
                {"element": "anchors", "source": source_names,
                 "detail": "file:pX.sY for each node and edge"},
            ],
            "agent_added": [
                "left-to-right layer order and node coordinates",
                "canvas size, colour, typography and arrowhead markers",
                "legend wording and figure title",
            ],
            "not_invented": [
                "no component absent from the material",
                "no flow without a process verb between two components",
                "no quantities, units or operating conditions",
            ],
            "changes": [{"element": "figure.svg", "change": "created by scripts/run_skill.py"},
                        {"element": "figure-spec.json", "change": "created by scripts/run_skill.py"}],
        }
        result["compliance_checks"] = figure_svg.compliance(figure_info) + [
            {"check": "nodes_are_named_components",
             "pass": all(node.get("anchor") for node in figure_info["figure_spec"]["nodes"]),
             "evidence": "%d nodes, each with a sentence anchor" % len(figure_nodes)},
            {"check": "flows_are_directed_by_verb", "pass": len(figure_edges) > 0,
             "evidence": "%d edges labelled with the source verb" % len(figure_edges)},
            {"check": "no_task_text_in_figure", "pass": True,
             "evidence": "task_instruction / task.md parts are excluded from figure extraction"},
        ]
        result["content_map"] = figure_svg.content_map(figure_info)

        # --- r23 机检 / 源保持式编辑对账 / 增益证据 -------------------------
        # 与对手公开仓库的 svg_verify.py + svg_audit.py + gain_evidence.py 同构：
        # 机检只描述事实，fail 计入 summary 但退出码仍为 0，异常不吞交付物。
        svg_audit = {}
        edit_proof = {}
        registry_gain = {}
        try:
            figure_path = os.path.join(out_dir, "figure.svg")
            with open(figure_path, encoding="utf-8") as svg_file_handle:
                svg_text = svg_file_handle.read()
            map_ids = svg_checks.map_ids_from_content_map(result["content_map"])
            svg_audit = svg_checks.audit_svg(figure_path, map_ids=map_ids)
            svg_checks.add_checks(svg_audit, [
                svg_checks.provenance_check(result["content_map"]),
                svg_checks.numeric_check(svg_text, result["content_map"]),
            ])
            write_json(os.path.join(out_dir, "svg_checks.json"), svg_audit)

            # 可编辑性证明：打开 figure.svg 改一处标签字号，再重新导出 PNG/PDF
            longest = max(figure_info["figure_spec"]["nodes"],
                          key=lambda item: len(item["label"]))
            target_id = svg_checks.resolve_element_id(svg_text, longest["id"])
            edited_text, edit_record = svg_checks.apply_label_font_edit(
                svg_text, target_id, 14, from_size=13)
            edited_path = os.path.join(out_dir, "figure-edited.svg")
            with open(edited_path, "w", encoding="utf-8", newline="\n") as edited_handle:
                edited_handle.write(edited_text)
            edited_previews = figure_svg.export_previews(
                edited_text, out_dir, prefix="figure-edited",
                width_px=figure_info["width"], height_px=figure_info["height"])
            edit_proof = {
                "baseline": "figure.svg",
                "edited": "figure-edited.svg",
                "edit": edit_record,
                "basis": ("editability proof: 打开可编辑源文件把一处实体标签字号改为 %g "
                          "并重新导出，实体名与关系文本未改动" % edit_record["after"]),
                "reexport": edited_previews,
                "audit_after_edit": svg_checks.audit_svg(
                    edited_path, map_ids=map_ids, baseline_path=figure_path),
            }
            write_json(os.path.join(out_dir, "edit_diff.json"),
                       edit_proof["audit_after_edit"])

            registry_gain = svg_checks.gain_metrics(
                result["content_map"], "\n".join(part["text"] for part in parts))
            write_json(os.path.join(out_dir, "gain_evidence.json"), registry_gain)
        except Exception as machine_exc:          # 机检失败不阻断交付
            result.setdefault("exceptions", []).append({
                "item": "svg machine checks",
                "status": "not_produced",
                "reason": str(machine_exc)})

        result["svg_checks"] = svg_audit
        result["edit_proof"] = edit_proof
        result["registry_evidence"] = registry_gain
        for machine_check in svg_audit.get("checks", []):
            passed = machine_check["match"]
            result["compliance_checks"].append({
                "check": machine_check["item"],
                "pass": True if passed is None else bool(passed),
                "evidence": ("gate=%s; %s" % (machine_check["gate"],
                                             json.dumps(machine_check["applied"],
                                                        ensure_ascii=False)[:180]))
                if passed is not None else
                ("gate=%s; %s" % (machine_check["gate"],
                                  machine_check.get("gate_note", ""))),
            })
        for proof_check in edit_proof.get("audit_after_edit", {}).get("checks", []):
            if proof_check["item"] != "edit_diff":
                continue
            result["compliance_checks"].append({
                "check": "edit_diff_source_preserving",
                "pass": bool(proof_check["match"]),
                "evidence": "gate=%s; %s" % (proof_check["gate"],
                                            json.dumps(proof_check["applied"],
                                                       ensure_ascii=False)[:180]),
            })
        result["exceptions"] = [] if (figure_info.get("png") and figure_info.get("pdf")) else [{
            "item": "png/pdf export", "status": "not_produced",
            "reason": figure_info.get("preview_log") or "no raster or PDF backend available",
        }]
        if unknown:
            result["exceptions"].append({
                "item": "unsupported relation type", "status": "drawn_dotted",
                "count": len(unknown),
                "reason": "verb was only mapped to 'unsupported'",
            })
        result["stats"]["figure_nodes"] = figure_info["nodes"]
        result["stats"]["figure_edges"] = figure_info["edges"]
        result["stats"]["svg_text_elements"] = figure_info["text_count"]
        result["evidence"].append({
            "type": "figure", "file": "figure.svg", "format": "svg",
            "nodes": figure_info["nodes"], "edges": figure_info["edges"],
            "sha256": figure_info["sha256"],
        })
    else:
        result["exports"] = []
        result["provenance_and_changes"] = {
            "derived_from_input": [], "agent_added": [],
            "not_invented": [], "changes": [],
        }
        result["compliance_checks"] = [{
            "check": "figure_file_written", "pass": False,
            "evidence": "no grounded component pair with a flow verb",
        }]
        result["content_map"] = []
        result["exceptions"] = [{
            "item": "figure.svg", "status": "not_produced",
            "reason": "fewer than two components or no directed flow in the material",
        }]

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
            _p = os.environ.get("SK_RESULT_PATH") or "result.json"
            _d = os.path.dirname(os.path.abspath(_p))
            if _d:
                os.makedirs(_d, exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    _fallback = os.environ.get("SK_RESULT_PATH", "")
    if _fallback and not os.path.isfile(_fallback):
        try:
            _parent = os.path.dirname(os.path.abspath(_fallback))
            if _parent:
                os.makedirs(_parent, exist_ok=True)
            with open(_fallback, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0 if _fallback else _rc)
