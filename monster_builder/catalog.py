"""Versioned, source-provenanced catalog loading for the monster builder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class CatalogError(ValueError):
    """The checked-in catalog cannot be used safely."""


class Catalog:
    def __init__(self, data: dict[str, Any], root: Path):
        self.data = data
        self.root = root
        self.version = data["catalogVersion"]
        self.schema_version = data["schemaVersion"]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Catalog":
        if path is None:
            path = Path(__file__).resolve().parents[1] / "catalog" / "catalog-v1.json"
        catalog_path = Path(path).resolve()
        try:
            data = json.loads(catalog_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"cannot load catalog: {catalog_path}") from exc
        root = catalog_path.parent.parent
        catalog = cls(data, root)
        catalog.validate()
        return catalog

    def validate(self) -> None:
        schema_path = self.root / "catalog" / "catalog.schema.json"
        if schema_path.is_file():
            try:
                schema = json.loads(schema_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CatalogError(f"cannot load catalog schema: {schema_path}") from exc
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise CatalogError("unsupported catalog schema dialect")
            schema_required = set(schema.get("required", []))
        else:
            schema_required = set()
        required = (
            "schemaVersion", "catalogVersion", "sources", "arrays", "grafts",
            "options", "skills", "damage", "naturalAttacksBySize", "spellLists",
            "spells", "metamagic", "metamagicRules",
        )
        missing = [key for key in required if key not in self.data]
        missing.extend(key for key in schema_required if key not in self.data and key not in missing)
        if missing:
            raise CatalogError(f"catalog missing required sections: {', '.join(missing)}")
        if self.schema_version != "1":
            raise CatalogError(f"unsupported catalog schema: {self.schema_version!r}")
        if not isinstance(self.version, str) or not self.version:
            raise CatalogError("catalogVersion must be a non-empty string")

        for source_id, source in self.data["sources"].items():
            if source.get("sourceId") != source_id:
                raise CatalogError(f"sourceId mismatch for {source_id}")
            file_name = source.get("file")
            expected_hash = source.get("sha256")
            if not file_name:
                if expected_hash is not None:
                    raise CatalogError(f"external source {source_id} cannot have a hash")
                continue
            source_path = self.root / file_name
            if not source_path.is_file():
                raise CatalogError(f"source file missing: {file_name}")
            if not expected_hash:
                raise CatalogError(f"source hash missing: {source_id}")
            actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise CatalogError(f"source hash mismatch: {file_name}")

        arrays = self.data["arrays"]
        for array_name in ("combatant", "expert", "spellcaster"):
            array = arrays.get(array_name)
            if not isinstance(array, dict):
                raise CatalogError(f"missing array: {array_name}")
            if set(array["mainStatistics"]) != set(array["attackStatistics"]):
                raise CatalogError(f"array CR keys differ: {array_name}")
            if len(array["mainStatistics"]) != 31:
                raise CatalogError(f"array must contain CR 1/2 through 30: {array_name}")

        if "99-101" not in self.data["damage"]:
            raise CatalogError("damage table must include the 99-101 boundary")

        for entry in self._all_entries_with_refs():
            refs = entry.get("sourceRef", [])
            if isinstance(refs, dict):
                refs = [refs]
            if not refs:
                raise CatalogError(f"catalog entry has no provenance: {entry.get('id')}")
            for source_ref in refs:
                source_id = source_ref.get("sourceId")
                if source_id not in self.data["sources"]:
                    raise CatalogError(f"unknown provenance source: {source_id}")
                lines = source_ref.get("txtLines", [])
                if len(lines) not in (0, 2) or any(not isinstance(line, int) or line < 1 for line in lines):
                    raise CatalogError(f"invalid provenance line range: {source_id}")
                if source_ref.get("file") and source_ref.get("sha256"):
                    actual = hashlib.sha256((self.root / source_ref["file"]).read_bytes()).hexdigest()
                    if actual != source_ref["sha256"]:
                        raise CatalogError(f"entry provenance hash mismatch: {source_ref['file']}")

        if "metamagicRules" in self.data:
            for rule_id, increase in self.data.get("metamagic", {}).items():
                rule = self.data["metamagicRules"].get(rule_id) or self.data["metamagicRules"].get(f"metamagic.{rule_id}")
                if rule is None or rule.get("levelIncrease") != increase:
                    raise CatalogError(f"metamagic rule mismatch: {rule_id}")

        for spell_id, spell in self.data["spells"].items():
            if spell.get("id") != spell_id:
                raise CatalogError(f"spell id mismatch: {spell_id}")
            levels = spell.get("levelsByClass")
            if not isinstance(levels, dict) or not levels:
                raise CatalogError(f"spell has no class levels: {spell_id}")
            if spell.get("highest") != max(levels.values()):
                raise CatalogError(f"spell highest is not derived from levels: {spell_id}")

        non_core = [
            spell for spell in self.data["spells"].values()
            if spell.get("sourceBook") in {"APG", "UM", "UC"}
        ]
        if len(non_core) != 39:
            raise CatalogError(f"expected 39 APG/UM/UC spells, found {len(non_core)}")
        acg = [spell for spell in self.data["spells"].values() if spell.get("sourceBook") == "ACG"]
        if len(acg) != 5:
            raise CatalogError(f"expected five ACG follow-up spells, found {len(acg)}")

    def _all_entries_with_refs(self):
        for array in self.data["arrays"].values():
            yield from array["mainStatistics"].values()
            yield from array["attackStatistics"].values()
        grafts = self.data["grafts"]
        for group in grafts.values():
            yield from group.values()
        for group_name in ("options", "skills", "naturalAttacksBySize", "spellLists", "spells", "metamagicRules"):
            if group_name in self.data:
                yield from self.data[group_name].values()
        yield from self.data["damage"].values()

    def entries(self, kind: str) -> dict[str, Any]:
        groups = {
            "array": self.data["arrays"],
            "creatureType": self.data["grafts"]["creatureTypes"],
            "classGraft": self.data["grafts"]["classGrafts"],
            "subtype": self.data["grafts"]["subtypes"],
            "template": self.data["grafts"]["templates"],
            "size": self.data["grafts"]["sizes"],
            "option": self.data["options"],
            "skill": self.data["skills"],
            "naturalAttack": self.data["naturalAttacksBySize"],
            "spellList": self.data["spellLists"],
            "spell": self.data["spells"],
        }
        try:
            return groups[kind]
        except KeyError as exc:
            raise CatalogError(f"unknown catalog kind: {kind}") from exc

    def resolve_id(self, kind: str, value: str) -> tuple[str, dict[str, Any]]:
        if not isinstance(value, str) or not value:
            raise CatalogError(f"{kind} id must be a non-empty string")
        entries = self.entries(kind)
        if value in entries:
            return entries[value].get("id", value), entries[value]
        for entry_key, entry in entries.items():
            if entry.get("id") == value:
                return entry.get("id", entry_key), entry
        prefixes = {
            "array": "array.", "creatureType": "graft.creature-type.", "size": "graft.size.",
            "option": "option.", "skill": "skill.", "naturalAttack": "natural-attack.",
            "spellList": "spell-list.",
        }
        candidate = prefixes.get(kind, "") + value
        if candidate in entries:
            return entries[candidate].get("id", candidate), entries[candidate]
        aliases = self.data.get("aliases", {}).get({
            "array": "arrays", "creatureType": "grafts", "size": "grafts", "option": "options",
        }.get(kind, kind), {})
        alias = aliases.get(value)
        if kind in {"creatureType", "size"}:
            alias = self.data.get("aliases", {}).get("grafts", {}).get(value)
        if alias in entries:
            return entries[alias].get("id", alias), entries[alias]
        raise CatalogError(f"unknown {kind} id: {value}")
