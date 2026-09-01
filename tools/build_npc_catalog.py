#!/usr/bin/env python3
"""Build the independent NPC catalog from deterministic JSON fragments.

Usage from the repository root::

    python3 tools/build_npc_catalog.py
    python3 tools/build_npc_catalog.py --check

The builder never reads or writes ``catalog/catalog.json``.  It verifies the
hash-anchored source manifest, hydrates source references with the current
source hashes, computes the catalog version, and validates the final result.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monster_builder.catalog import CatalogError
from monster_builder.npc_catalog import NPC_SECTIONS, catalog_fingerprint, validate_npc_data


DEFAULT_FRAGMENT_DIR = ROOT / "catalog" / "npc"
DEFAULT_OUTPUT = ROOT / "catalog" / "npc.json"
SOURCE_MANIFEST = ROOT / "sources" / "npc" / "MANIFEST.json"

# Local policy and hash-anchored source files consumed by the NPC catalog.
# Record fragments cite the gap matrix for unavailable game data, the ADR for
# product representation decisions, the mode plan for structural references,
# and the anchored Core Rulebook spell-list extract for resolved spell-list
# membership (the only locally anchored numeric NPC domain).
SOURCE_FILES = (
    ("source.npc-manifest", "sources/npc/MANIFEST.json", "Hash manifest for the local NPC source foundation"),
    ("source.npc-gap-matrix", "docs/npc-source-gap-matrix.md", "Explicit source-gap classifications binding NPC catalog data"),
    ("source.npc-adr", "docs/adr/creation-system.md", "Accepted creation-system and NPC catalog decisions"),
    ("source.npc-mode-plan", "NPC_MODE_PLAN.md", "NPC creation plan and terminology"),
    ("source.npc-crb-spell-lists", "sources/npc/core-rulebook-extract.spell-lists.txt", "Hash-anchored Core Rulebook class spell lists (16-page local excerpt)"),
    ("source.npc-crb-extract", "sources/npc/core-rulebook-extract.txt", "Full pdftotext extraction of the local 16-page Core Rulebook excerpt"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read {description}: {path}") from exc


def _safe_relative(root: Path, file_name: str, description: str) -> Path:
    path = (root / file_name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CatalogError(f"{description} escapes repository root: {file_name}") from exc
    return path


def validate_source_manifest(root: Path = ROOT) -> None:
    """Verify every file/hash pair declared by the Phase 0 manifest."""
    manifest_path = _safe_relative(root, "sources/npc/MANIFEST.json", "source manifest")
    manifest = _read_json(manifest_path, "source manifest")
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != "1":
        raise CatalogError("NPC source manifest has an unsupported schema")
    for group_name in ("parentSources", "extracts", "fragments"):
        group = manifest.get(group_name, {})
        if not isinstance(group, dict):
            raise CatalogError(f"NPC source manifest section is invalid: {group_name}")
        for entry_id, entry in group.items():
            if not isinstance(entry, dict):
                raise CatalogError(f"NPC source manifest entry is invalid: {entry_id}")
            file_name = entry.get("file")
            expected = entry.get("sha256")
            if file_name is None:
                if expected is not None:
                    raise CatalogError(f"NPC source manifest external entry has a hash: {entry_id}")
                continue
            if not isinstance(file_name, str) or not isinstance(expected, str):
                raise CatalogError(f"NPC source manifest entry lacks file/hash: {entry_id}")
            path = _safe_relative(root, file_name, f"NPC source {entry_id}")
            if not path.is_file():
                raise CatalogError(f"NPC source file is missing: {file_name}")
            if _sha256(path) != expected:
                raise CatalogError(f"NPC source hash mismatch: {file_name}")


def source_table(root: Path = ROOT) -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = {}
    for source_id, file_name, description in SOURCE_FILES:
        path = _safe_relative(root, file_name, f"catalog source {source_id}")
        if not path.is_file():
            raise CatalogError(f"catalog source file is missing: {file_name}")
        table[source_id] = {
            "sourceId": source_id,
            "file": file_name,
            "sha256": _sha256(path),
            "description": description,
        }
    return table


def _hydrate_refs(value: Any, sources: dict[str, dict[str, str]]) -> Any:
    if isinstance(value, dict):
        result = {key: _hydrate_refs(child, sources) for key, child in value.items()}
        if "sourceRef" in result:
            refs = result["sourceRef"] if isinstance(result["sourceRef"], list) else [result["sourceRef"]]
            hydrated = []
            for ref in refs:
                if not isinstance(ref, dict):
                    raise CatalogError("fragment sourceRef must be an object or array of objects")
                source_id = ref.get("sourceId")
                if source_id not in sources:
                    raise CatalogError(f"fragment references unknown source: {source_id!r}")
                source = sources[source_id]
                item = copy.deepcopy(ref)
                item.setdefault("file", source["file"])
                item.setdefault("sha256", source["sha256"])
                item.setdefault("txtLines", [])
                if item["file"] != source["file"] or item["sha256"] != source["sha256"]:
                    raise CatalogError(f"fragment sourceRef metadata disagrees with source table: {source_id}")
                hydrated.append(item)
            result["sourceRef"] = hydrated if isinstance(result["sourceRef"], list) else hydrated[0]
        return result
    if isinstance(value, list):
        return [_hydrate_refs(child, sources) for child in value]
    return value


def load_fragments(fragment_dir: Path = DEFAULT_FRAGMENT_DIR) -> list[dict[str, Any]]:
    if not fragment_dir.is_dir():
        raise CatalogError(f"NPC fragment directory is missing: {fragment_dir}")
    fragments = []
    for path in sorted(fragment_dir.glob("*.fragment.json")):
        fragment = _read_json(path, "NPC catalog fragment")
        if not isinstance(fragment, dict):
            raise CatalogError(f"NPC catalog fragment must be an object: {path.name}")
        section = fragment.get("section")
        records = fragment.get("records")
        if section not in NPC_SECTIONS:
            raise CatalogError(f"NPC catalog fragment has an unknown section: {path.name}")
        if not isinstance(records, list):
            raise CatalogError(f"NPC catalog fragment records must be an array: {path.name}")
        fragments.append({"path": path, "section": section, "records": records})
    if not fragments:
        raise CatalogError("NPC catalog has no *.fragment.json inputs")
    return fragments


def build_catalog(root: Path = ROOT, fragment_dir: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    validate_source_manifest(root)
    sources = source_table(root)
    fragments = load_fragments(fragment_dir or root / "catalog" / "npc")
    data: dict[str, Any] = {
        "schemaVersion": "1",
        # A temporary non-empty value lets structural validation run before
        # the final content hash is calculated.
        "catalogVersion": "sha256:" + "0" * 64,
        "catalogStatus": {
            "sourcePolicy": "bounded-by-local-source-gaps",
            "npcWorkflow": "gap",
            "abilityArrays": "gap",
            "races": "gap",
            "classes": "gap",
            "classFeatures": "gap",
            "skills": "gap",
            "feats": "gap",
            "equipment": "gap",
            "gearBudgets": "gap",
            "spellListMembership": "resolved",
            "spellRules": "gap",
            "typedPrerequisites": "policy-schema-ready",
            "money": "integer-copper-pieces",
        },
        "sources": sources,
    }
    data.update({section: {} for section in NPC_SECTIONS})
    seen: dict[str, Path] = {}
    for fragment in fragments:
        for raw_record in fragment["records"]:
            if not isinstance(raw_record, dict):
                raise CatalogError(f"NPC catalog record must be an object: {fragment['path'].name}")
            record = _hydrate_refs(raw_record, sources)
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise CatalogError(f"NPC catalog record has no ID: {fragment['path'].name}")
            if record_id in seen:
                raise CatalogError(f"duplicate NPC catalog record {record_id}: {seen[record_id].name} and {fragment['path'].name}")
            seen[record_id] = fragment["path"]
            data[fragment["section"]][record_id] = record
    validate_npc_data(data, root, check_version=False)
    data["catalogVersion"] = catalog_fingerprint(data)
    validate_npc_data(data, root)
    return data


def serialized_catalog(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_catalog(data: dict[str, Any], output: Path = DEFAULT_OUTPUT) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = serialized_catalog(data)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise CatalogError(f"cannot write NPC catalog: {output}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the independent source-backed NPC catalog")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--fragment-dir", type=Path, default=None, help="NPC fragment directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="generated catalog path")
    parser.add_argument("--check", action="store_true", help="verify generated output without writing")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = (args.output if args.output.is_absolute() else root / args.output).resolve()
    fragment_dir = None if args.fragment_dir is None else (args.fragment_dir if args.fragment_dir.is_absolute() else root / args.fragment_dir).resolve()
    try:
        data = build_catalog(root, fragment_dir)
        content = serialized_catalog(data)
        if args.check:
            if not output.is_file() or output.read_bytes() != content:
                print(f"NPC catalog is stale: {output}", file=sys.stderr)
                return 1
            print(f"NPC catalog is up to date: {output}")
            return 0
        write_catalog(data, output)
        print(f"Wrote {output} ({data['catalogVersion']})")
        return 0
    except (CatalogError, OSError, ValueError) as exc:
        print(f"NPC catalog build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
