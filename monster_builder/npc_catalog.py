"""Loading and validation for the independently versioned NPC catalog.

The NPC catalog is deliberately separate from ``catalog/catalog.json``.  This
module validates the generated JSON with only the standard library so the
runtime and the catalog builder apply the same provenance and money rules.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .catalog import CatalogError


NPC_SCHEMA_VERSION = "1"
NPC_CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog" / "npc.json"
NPC_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "catalog" / "npc.schema.json"
NPC_SECTIONS = (
    "abilityArrays",
    "gearBudgets",
    "races",
    "classes",
    "classFeatures",
    "skills",
    "feats",
    "items",
    "spells",
    "derivedRules",
)
SECTION_KINDS = {
    "abilityArray": "abilityArrays",
    "gearBudget": "gearBudgets",
    "race": "races",
    "class": "classes",
    "classFeature": "classFeatures",
    "skill": "skills",
    "feat": "feats",
    "item": "items",
    "spell": "spells",
    "derivedRule": "derivedRules",
}
CATALOG_STATUSES = {"resolved", "gap", "policy", "partial"}
ABILITY_NAMES = {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}
MONEY_KEYS = {"priceCp", "budgetCp", "spentCp", "valueCp", "costCp"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def catalog_fingerprint(data: dict[str, Any]) -> str:
    """Return the deterministic version hash used by ``catalogVersion``."""
    value = {key: item for key, item in data.items() if key != "catalogVersion"}
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _error(message: str) -> CatalogError:
    return CatalogError(f"NPC catalog: {message}")


def _safe_path(root: Path, file_name: str, context: str) -> Path:
    if not isinstance(file_name, str) or not file_name:
        raise _error(f"{context} file must be a non-empty string")
    candidate = (root / file_name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise _error(f"{context} file escapes catalog root: {file_name}") from exc
    return candidate


def _hash_file(root: Path, file_name: str, context: str) -> str:
    path = _safe_path(root, file_name, context)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise _error(f"{context} source file cannot be read: {file_name}") from exc


def _source_refs(value: Any, context: str) -> list[dict[str, Any]]:
    refs = value if isinstance(value, list) else [value]
    if not refs or any(not isinstance(ref, dict) for ref in refs):
        raise _error(f"{context} sourceRef must be an object or non-empty array")
    return refs


def _validate_source_ref(ref: dict[str, Any], sources: dict[str, Any], root: Path, context: str) -> None:
    allowed = {"sourceId", "file", "sha256", "section", "txtLines", "printedPages", "viewerPages", "officialUrl", "entry", "table", "provenanceStatus"}
    unknown = set(ref) - allowed
    if unknown:
        raise _error(f"{context} has unknown fields: {', '.join(sorted(unknown))}")
    source_id = ref.get("sourceId")
    if not isinstance(source_id, str) or source_id not in sources:
        raise _error(f"{context} references unknown source: {source_id!r}")
    if not isinstance(ref.get("section"), str) or not ref["section"]:
        raise _error(f"{context} sourceRef section is required")
    lines = ref.get("txtLines")
    if not isinstance(lines, list) or len(lines) not in (0, 2) or any(
        not isinstance(line, int) or isinstance(line, bool) or line < 1 for line in lines
    ):
        raise _error(f"{context} sourceRef txtLines must contain zero or two positive integers")
    for field in ("printedPages", "viewerPages"):
        if field in ref and (not isinstance(ref[field], list) or not ref[field] or any(not isinstance(page, int) or isinstance(page, bool) or page < 1 for page in ref[field])):
            raise _error(f"{context} {field} must be a non-empty array of positive integers")
    for field in ("officialUrl", "entry", "table"):
        if field in ref and (not isinstance(ref[field], str) or not ref[field]):
            raise _error(f"{context} {field} must be a non-empty string")
    source = sources[source_id]
    if ref.get("file") != source["file"]:
        raise _error(f"{context} sourceRef file does not match {source_id}")
    if ref.get("sha256") != source["sha256"]:
        raise _error(f"{context} sourceRef hash does not match {source_id}")
    if "provenanceStatus" in ref and not isinstance(ref["provenanceStatus"], str):
        raise _error(f"{context} provenanceStatus must be a string")


def _validate_source_table(data: dict[str, Any], root: Path) -> None:
    sources = data.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise _error("sources must be a non-empty object")
    for key, source in sources.items():
        context = f"sources.{key}"
        if not isinstance(source, dict):
            raise _error(f"{context} must be an object")
        unknown = set(source) - {"sourceId", "file", "sha256", "description"}
        if unknown:
            raise _error(f"{context} has unknown fields: {', '.join(sorted(unknown))}")
        if source.get("sourceId") != key:
            raise _error(f"{context}.sourceId must match its key")
        if not isinstance(source.get("file"), str) or not source["file"]:
            raise _error(f"{context}.file must be a non-empty string")
        expected = source.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise _error(f"{context}.sha256 must be a lowercase SHA-256 hex digest")
        if not isinstance(source.get("description"), str) or not source["description"]:
            raise _error(f"{context}.description must be a non-empty string")
        actual = _hash_file(root, source["file"], context)
        if actual != expected:
            raise _error(f"{context} hash mismatch for {source['file']}")


def _validate_prerequisite(value: Any, context: str, *, allow_none: bool = True) -> None:
    if value is None:
        if allow_none:
            return
        raise _error(f"{context} must be a prerequisite expression")
    if not isinstance(value, dict) or len(value) != 1:
        raise _error(f"{context} must be one typed prerequisite expression")
    operator, operand = next(iter(value.items()))
    if operator in {"all", "any"}:
        if not isinstance(operand, list) or (operator == "any" and not operand):
            raise _error(f"{context}.{operator} must be a non-empty array" if operator == "any" else f"{context}.{operator} must be an array")
        for index, child in enumerate(operand):
            _validate_prerequisite(child, f"{context}.{operator}[{index}]", allow_none=False)
        return
    if operator == "not":
        _validate_prerequisite(operand, f"{context}.not", allow_none=False)
        return
    if operator == "abilityAtLeast":
        if not isinstance(operand, dict) or not operand:
            raise _error(f"{context}.abilityAtLeast must be a non-empty ability map")
        for ability, score in operand.items():
            if ability not in ABILITY_NAMES or not isinstance(score, int) or isinstance(score, bool):
                raise _error(f"{context}.abilityAtLeast contains an invalid ability or score")
        return
    if operator in {"babAtLeast", "characterLevelAtLeast", "casterLevelAtLeast"}:
        minimum = 1 if operator != "babAtLeast" else 0
        if not isinstance(operand, int) or isinstance(operand, bool) or operand < minimum:
            raise _error(f"{context}.{operator} must be an integer >= {minimum}")
        return
    if operator in {"classLevelAtLeast", "skillRanksAtLeast"}:
        if not isinstance(operand, dict) or not operand:
            raise _error(f"{context}.{operator} must be a non-empty map")
        for key, minimum in operand.items():
            if not isinstance(key, str) or not key or not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                raise _error(f"{context}.{operator} contains an invalid entry")
            if operator == "classLevelAtLeast" and minimum < 1:
                raise _error(f"{context}.classLevelAtLeast values must be positive")
        return
    if operator in {"race", "alignment", "hasFeat", "hasClassFeature"}:
        if not isinstance(operand, str) or not operand:
            raise _error(f"{context}.{operator} must be a non-empty string")
        return
    raise _error(f"{context} uses unsupported prerequisite operand: {operator}")


def _validate_money(value: Any, context: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            money_container = context.endswith(".categories") or context.rsplit(".", 1)[-1].endswith("Cp")
            if key in MONEY_KEYS or key.endswith("Cp") or money_container:
                if child is not None and (not isinstance(child, int) or isinstance(child, bool) or child < 0):
                    raise _error(f"{context}.{key} must be a non-negative integer copper-piece value or null")
            _validate_money(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_money(child, f"{context}[{index}]")


def _validate_nested_refs(value: Any, sources: dict[str, Any], root: Path, context: str) -> None:
    if isinstance(value, dict):
        if "sourceRef" in value:
            for index, ref in enumerate(_source_refs(value["sourceRef"], f"{context}.sourceRef")):
                _validate_source_ref(ref, sources, root, f"{context}.sourceRef[{index}]")
        for key, child in value.items():
            if key != "sourceRef":
                _validate_nested_refs(child, sources, root, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_nested_refs(child, sources, root, f"{context}[{index}]")


def _validate_sections(data: dict[str, Any], root: Path) -> None:
    sources = data["sources"]
    seen_ids: set[str] = set()
    alias_owners: dict[tuple[str, str], str] = {}
    for section in NPC_SECTIONS:
        records = data.get(section)
        if not isinstance(records, dict):
            raise _error(f"{section} must be an object")
        for key, record in records.items():
            context = f"{section}.{key}"
            if not isinstance(record, dict):
                raise _error(f"{context} must be an object")
            if record.get("id") != key:
                raise _error(f"{context}.id must match its key")
            if not isinstance(record.get("name"), str) or not record["name"]:
                raise _error(f"{context}.name must be a non-empty string")
            status = record.get("catalogStatus")
            if status not in CATALOG_STATUSES:
                raise _error(f"{context}.catalogStatus is invalid")
            if "gapCode" in record and (not isinstance(record["gapCode"], str) or not record["gapCode"]):
                raise _error(f"{context}.gapCode must be a non-empty string")
            if status == "gap" and (not isinstance(record.get("gapCode"), str) or not record["gapCode"]):
                raise _error(f"{context}.gapCode is required for a catalog gap")
            aliases = record.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias for alias in aliases):
                raise _error(f"{context}.aliases must be an array of non-empty strings")
            if "sourceRef" not in record:
                raise _error(f"{context}.sourceRef is required")
            for index, ref in enumerate(_source_refs(record["sourceRef"], f"{context}.sourceRef")):
                _validate_source_ref(ref, sources, root, f"{context}.sourceRef[{index}]")
            if record["id"] in seen_ids:
                raise _error(f"duplicate record ID: {record['id']}")
            seen_ids.add(record["id"])
            for alias in aliases:
                alias_key = (section, alias.rsplit(".", 1)[-1].casefold())
                if alias_key in alias_owners and alias_owners[alias_key] != record["id"]:
                    raise _error(f"{context}.aliases conflicts with {alias_owners[alias_key]}: {alias}")
                alias_owners[alias_key] = record["id"]
            _validate_nested_refs(record, sources, root, context)
            _validate_money(record, context)
            if section == "feats" and "prerequisites" in record:
                _validate_prerequisite(record["prerequisites"], f"{context}.prerequisites")
            if section == "abilityArrays":
                if not isinstance(record.get("method"), str) or not record["method"]:
                    raise _error(f"{context}.method must be a non-empty string")
                if "scores" not in record:
                    raise _error(f"{context}.scores is required")
                scores = record.get("scores")
                if scores is not None and (not isinstance(scores, list) or len(scores) != 6 or any(not isinstance(value, int) or isinstance(value, bool) for value in scores)):
                    raise _error(f"{context}.scores must be null or an array of six integers")
                if "abilityOrder" in record and (not isinstance(record["abilityOrder"], list) or any(not isinstance(value, str) for value in record["abilityOrder"])):
                    raise _error(f"{context}.abilityOrder must be an array of strings")
            if section == "classes":
                for field in ("category", "hitDie", "classSkills", "skillSelections", "levels"):
                    if field not in record:
                        raise _error(f"{context}.{field} is required")
                if record.get("category") not in {"npc", "pc"}:
                    raise _error(f"{context}.category is invalid")
                if record.get("hitDie") is not None and not isinstance(record.get("hitDie"), str):
                    raise _error(f"{context}.hitDie must be a string or null")
                if record.get("classSkills") is not None and (not isinstance(record.get("classSkills"), list) or any(not isinstance(value, str) for value in record["classSkills"])):
                    raise _error(f"{context}.classSkills must be an array of strings or null")
                if record.get("skillSelections") is not None and (not isinstance(record.get("skillSelections"), int) or isinstance(record.get("skillSelections"), bool)):
                    raise _error(f"{context}.skillSelections must be an integer or null")
                levels = record.get("levels")
                if not isinstance(levels, dict):
                    raise _error(f"{context}.levels must be an object")
                for level_key, level in levels.items():
                    if not str(level_key).isdigit():
                        raise _error(f"{context}.levels.{level_key} has an invalid level key")
                    numeric_level = int(level_key)
                    if not isinstance(level, dict) or not isinstance(level.get("level"), int) or isinstance(level.get("level"), bool) or level.get("level") != numeric_level or numeric_level < 1:
                        raise _error(f"{context}.levels.{level_key} has an inconsistent level")
                    if level.get("catalogStatus") not in CATALOG_STATUSES:
                        raise _error(f"{context}.levels.{level_key}.catalogStatus is invalid")
                    if "sourceRef" not in level:
                        raise _error(f"{context}.levels.{level_key}.sourceRef is required")
                    self_level_context = f"{context}.levels.{level_key}"
                    for field in ("bab", "fortitude", "reflex", "will", "skillSelections"):
                        if field in level and level[field] is not None and (not isinstance(level[field], int) or isinstance(level[field], bool)):
                            raise _error(f"{self_level_context}.{field} must be an integer or null")
                    for field in ("hitDie",):
                        if field in level and level[field] is not None and not isinstance(level[field], str):
                            raise _error(f"{self_level_context}.{field} must be a string or null")
                    for field in ("featureGrants",):
                        if field in level and level[field] is not None and (not isinstance(level[field], list) or any(not isinstance(value, str) for value in level[field])):
                            raise _error(f"{self_level_context}.{field} must be an array of strings or null")
                    if "choiceSlots" in level and level["choiceSlots"] is not None and (not isinstance(level["choiceSlots"], list) or any(not isinstance(value, dict) for value in level["choiceSlots"])):
                        raise _error(f"{self_level_context}.choiceSlots must be an array of objects or null")
            if section == "gearBudgets":
                if record.get("progression") not in {"slow", "medium", "fast"}:
                    raise _error(f"{context}.progression is invalid")
                if record.get("fantasyLevel") not in {"low", "normal", "high"}:
                    raise _error(f"{context}.fantasyLevel is invalid")
                if "budgetCp" not in record or "categories" not in record:
                    raise _error(f"{context}.budgetCp and categories are required")
                if record.get("effectiveLevel") is not None and (not isinstance(record.get("effectiveLevel"), int) or isinstance(record.get("effectiveLevel"), bool)):
                    raise _error(f"{context}.effectiveLevel must be an integer or null")
                if record.get("budgetCp") is not None and (not isinstance(record.get("budgetCp"), int) or isinstance(record.get("budgetCp"), bool) or record["budgetCp"] < 0):
                    raise _error(f"{context}.budgetCp must be a non-negative integer or null")
                categories = record.get("categories")
                if categories is not None and (not isinstance(categories, dict) or any(value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in categories.values())):
                    raise _error(f"{context}.categories must contain non-negative integers or null")
            if section == "races":
                for field in ("abilityAdjustments", "speed"):
                    value = record.get(field)
                    if value is not None and (not isinstance(value, dict) or any(not isinstance(child, int) or isinstance(child, bool) for child in value.values())):
                        raise _error(f"{context}.{field} must be an integer map or null")
                for field in ("sizeId",):
                    if record.get(field) is not None and not isinstance(record.get(field), str):
                        raise _error(f"{context}.{field} must be a string or null")
                for field in ("senses", "traits", "languages"):
                    if record.get(field) is not None and (not isinstance(record.get(field), list) or any(not isinstance(child, str) for child in record[field])):
                        raise _error(f"{context}.{field} must be an array of strings or null")
            if section == "skills":
                for field in ("keyAbility",):
                    if record.get(field) is not None and not isinstance(record.get(field), str):
                        raise _error(f"{context}.{field} must be a string or null")
                for field in ("trainedOnly", "armorCheckPenalty"):
                    if record.get(field) is not None and not isinstance(record.get(field), bool):
                        raise _error(f"{context}.{field} must be a boolean or null")
            if section == "feats":
                if not isinstance(record.get("category"), str) or not record["category"]:
                    raise _error(f"{context}.category must be a non-empty string")
                if "prerequisites" not in record:
                    raise _error(f"{context}.prerequisites is required")
                if record.get("effects") is not None and not isinstance(record.get("effects"), dict):
                    raise _error(f"{context}.effects must be an object or null")
            if section == "items":
                if record.get("category") not in {"weapon", "armor", "shield", "gear", "goods", "magic"}:
                    raise _error(f"{context}.category is invalid")
                if "priceCp" not in record or "effects" not in record:
                    raise _error(f"{context}.priceCp and effects are required")
                if record.get("priceCp") is not None and (not isinstance(record.get("priceCp"), int) or isinstance(record.get("priceCp"), bool) or record["priceCp"] < 0):
                    raise _error(f"{context}.priceCp must be a non-negative integer or null")
                if record.get("effects") is not None and not isinstance(record.get("effects"), dict):
                    raise _error(f"{context}.effects must be an object or null")
    typed = data["derivedRules"].get("npc-rule.typed-prerequisites")
    if typed is not None:
        examples = typed.get("examples")
        if not isinstance(examples, list) or not examples:
            raise _error("derivedRules.npc-rule.typed-prerequisites.examples must be a non-empty array")
        for index, example in enumerate(examples):
            _validate_prerequisite(example, f"derivedRules.npc-rule.typed-prerequisites.examples[{index}]", allow_none=False)


def validate_npc_data(data: dict[str, Any], root: Path, *, check_version: bool = True) -> None:
    """Validate catalog structure, hashes, references, money, and expressions."""
    if not isinstance(data, dict):
        raise _error("root must be an object")
    allowed_root = {"schemaVersion", "catalogVersion", "catalogStatus", "sources", *NPC_SECTIONS}
    unknown_root = set(data) - allowed_root
    if unknown_root:
        raise _error(f"root has unknown fields: {', '.join(sorted(unknown_root))}")
    if data.get("schemaVersion") != NPC_SCHEMA_VERSION:
        raise _error(f"unsupported schemaVersion: {data.get('schemaVersion')!r}")
    version = data.get("catalogVersion")
    if not isinstance(version, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", version):
        raise _error("catalogVersion must be a SHA-256 catalog fingerprint")
    if check_version and version != catalog_fingerprint(data):
        raise _error("catalogVersion does not match catalog contents")
    _validate_source_table(data, root)
    missing = [section for section in NPC_SECTIONS if section not in data]
    if missing:
        raise _error(f"missing sections: {', '.join(missing)}")
    status = data.get("catalogStatus")
    if not isinstance(status, dict) or any(not isinstance(value, str) for value in status.values()):
        raise _error("catalogStatus must be an object of strings")
    _validate_sections(data, root)
    _validate_money(data, "catalog")


class NpcCatalog:
    """A validated, independently versioned NPC catalog."""

    def __init__(self, data: dict[str, Any], root: Path):
        self.data = data
        self.root = root
        self.version = data["catalogVersion"]
        self.schema_version = data["schemaVersion"]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "NpcCatalog":
        catalog_path = Path(path or NPC_CATALOG_PATH).resolve()
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"cannot load NPC catalog: {catalog_path}") from exc
        root = catalog_path.parent.parent
        catalog = cls(data, root)
        catalog.validate()
        return catalog

    def validate(self) -> None:
        schema_path = self.root / "catalog" / "npc.schema.json"
        if schema_path.is_file():
            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise _error("cannot load npc.schema.json") from exc
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise _error("unsupported schema dialect")
            if schema.get("$id") != "https://pf-ai-gen.local/npc.schema.json":
                raise _error("unexpected NPC schema identity")
        validate_npc_data(self.data, self.root)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def entries(self, kind: str) -> dict[str, Any]:
        try:
            section = SECTION_KINDS[kind]
        except KeyError as exc:
            raise CatalogError(f"unknown NPC catalog kind: {kind}") from exc
        return self.data[section]

    def resolve_id(self, kind: str, value: str) -> tuple[str, dict[str, Any]]:
        if not isinstance(value, str) or not value:
            raise CatalogError(f"{kind} id must be a non-empty string")
        records = self.entries(kind)
        if value in records:
            return value, records[value]
        alias_matches = [
            record for record in records.values()
            if isinstance(record, dict) and (record.get("id") == value or value in record.get("aliases", []))
        ]
        if len(alias_matches) == 1:
            record = alias_matches[0]
            return record["id"], record
        if len(alias_matches) > 1:
            raise CatalogError(f"ambiguous NPC {kind} id: {value}")
        prefixes = {
            "abilityArray": "npc-ability-array.",
            "gearBudget": "npc-gear.",
            "race": "npc-race.",
            "class": "npc-class.",
            "classFeature": "npc-class-feature.",
            "skill": "skill.",
            "feat": "feat.",
            "item": "item.",
            "spell": "spell.",
            "derivedRule": "npc-rule.",
        }
        candidate = prefixes.get(kind, "") + value
        if candidate in records:
            return candidate, records[candidate]
        raise CatalogError(f"unknown NPC {kind} id: {value}")


__all__ = [
    "NPC_CATALOG_PATH",
    "NPC_SCHEMA_PATH",
    "NpcCatalog",
    "catalog_fingerprint",
    "validate_npc_data",
]
