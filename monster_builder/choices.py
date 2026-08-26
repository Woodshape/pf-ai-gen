"""System-owned input requirements for catalog-driven monster selections."""

from __future__ import annotations

from typing import Any


def active_class_cr_entry(graft: dict[str, Any] | None, cr: int | float) -> dict[str, Any] | None:
    return max((entry for entry in (graft or {}).get("crEntries", []) if cr >= entry["minCR"]), key=lambda entry: entry["minCR"], default=None)


def active_graft_option_grants(class_id, class_graft, subtype_grafts, template_id, template, cr, selections):
    """Return the source grants used by both validation and input requirements."""
    grants = []
    if class_graft:
        class_grants = list(class_graft.get("optionGrants", []))
        entry = active_class_cr_entry(class_graft, cr)
        if entry:
            removed = set(entry.get("removeOptionGrantIds", []))
            class_grants = [grant for grant in class_grants if grant["optionId"] not in removed] + list(entry.get("optionGrants", []))
        grants.extend((class_id, grant) for grant in class_grants)
    for subtype_id, subtype in subtype_grafts:
        if subtype:
            grants.extend((subtype_id, grant) for grant in subtype.get("optionGrants", []))
    if template:
        grants.extend((template_id, grant) for grant in template.get("optionGrants", []))
        choice = template.get("optionChoiceGrant", {})
        values = selections.get("templateGraftChoices", {}).get("optionIds", [])
        expected = 1 + int((cr - choice["minCR"]) / choice["perCR"]) if choice and cr >= choice["minCR"] else 0
        if isinstance(values, list) and len(values) == expected and len(set(values)) == len(values) and all(value in choice.get("optionIds", []) for value in values):
            parameters = choice.get("parametersByOption", {})
            grants.extend((template_id, {"optionId": option_id, "parameters": parameters.get(option_id, {}), "sourceText": template.get("ruleText", "")}) for option_id in values)
    return grants


def skill_selection_basis(catalog, draft, *, main=None, class_graft=None, active_grafts=None, subtype_grafts=None, size=None, template=None):
    selections = draft.get("selections", {})
    cr = selections.get("cr")

    def by_id(records, value):
        return next((entry for entry in records.values() if entry.get("id") == value), {})

    class_graft = class_graft if class_graft is not None else by_id(catalog["grafts"]["classGrafts"], selections.get("classGraftId"))
    subtype_grafts = subtype_grafts if subtype_grafts is not None else [(value, by_id(catalog["grafts"]["subtypes"], value)) for value in selections.get("subtypeGraftIds", [])]
    template = template if template is not None else by_id(catalog["grafts"]["templates"], selections.get("templateGraftId"))
    size = size if size is not None else by_id(catalog["grafts"]["sizes"], selections.get("sizeId"))
    active_grafts = active_grafts if active_grafts is not None else [graft for _, graft in subtype_grafts] + ([template] if template else [])
    if main is None and cr is not None:
        array = by_id(catalog["arrays"], selections.get("arrayId"))
        main = array.get("mainStatistics", {}).get("1/2" if cr == 0.5 else str(cr))
    grants = list((class_graft or {}).get("skillGrants", []))
    for graft in active_grafts:
        grants.extend(graft.get("skillGrants", []))
    for subtype_id, graft in subtype_grafts:
        choice = graft.get("skillChoiceGrant")
        if choice:
            value = selections.get("subtypeGraftChoices", {}).get(subtype_id, {}).get(choice["name"])
            if value in choice["skillIds"]:
                grants.append({"skillId": value, "rank": choice["rank"], "additional": True})
    expected_master = main.get("masterCount", 0) if main else None
    expected_good = main.get("goodCount", 0) if main else None
    if main:
        for graft in ((class_graft,) if class_graft else ()) + tuple(active_grafts):
            for slot in graft.get("skillSlots", []):
                if slot["rank"] == "master": expected_master += slot["count"]
                else: expected_good += slot["count"]
        for grant in grants:
            if not grant.get("additional"):
                if grant["rank"] == "master": expected_master = max(0, expected_master - 1)
                else: expected_good = max(0, expected_good - 1)
        if template and template.get("skillBudgetOverride"):
            expected_master = template["skillBudgetOverride"]["master"]
            expected_good = template["skillBudgetOverride"]["good"]
    ranks = {}

    def add(skill_id, rank, source_ref=None):
        if not isinstance(skill_id, str) or rank not in {"master", "good"}: return
        canonical = skill_id if skill_id.startswith("skill.") else f"skill.{skill_id}"
        if rank == "master" or canonical not in ranks: ranks[canonical] = (rank, source_ref)

    for graft in ((class_graft,) if class_graft else ()) + tuple(active_grafts):
        for grant in graft.get("skillGrants", []): add(grant.get("skillId"), grant.get("rank"), graft.get("sourceRef"))
    for grant in grants:
        if grant.get("additional"): add(grant.get("skillId"), grant.get("rank"))
    for skill_id in size.get("additionalMasterSkills", []): add(skill_id, "master", size.get("sourceRef"))
    for skill_id in size.get("additionalGoodSkills", []): add(skill_id, "good", size.get("sourceRef"))
    if not template.get("suppressAutomaticPerception") and "skill.perception" not in ranks: add("skill.perception", "good")
    skill_records = {entry["id"]: entry for entry in catalog["skills"].values()}
    automatic = {"master": [], "good": []}
    for skill_id, (rank, source_ref) in ranks.items():
        item = {"value": skill_id, "label": skill_records.get(skill_id, {}).get("name", _label(skill_id.removeprefix("skill.")))}
        if source_ref: item["sourceRefs"] = source_ref if isinstance(source_ref, list) else [source_ref]
        automatic[rank].append(item)
    for rank in automatic: automatic[rank].sort(key=lambda item: (item["label"], item["value"]))
    return {"grants": grants, "budgets": {"master": expected_master, "good": expected_good}, "automaticSelections": {"skills": automatic}}


class ChoiceRequirements:
    """Normalize active catalog rules into one agent/UI input interface."""

    def __init__(self, catalog: dict[str, Any]):
        self.catalog = catalog

    def selection_basis(self, draft: dict[str, Any]) -> dict[str, Any]:
        return skill_selection_basis(self.catalog, draft)

    def for_draft(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        selections = draft.get("selections", {})
        cr = selections.get("cr", draft.get("concept", {}).get("targetCR", 0))
        cr = cr if isinstance(cr, (int, float)) and not isinstance(cr, bool) else 0
        requirements: list[dict[str, Any]] = []
        class_id = selections.get("classGraftId")
        class_graft = self.catalog["grafts"]["classGrafts"].get(class_id) if class_id else None
        if class_graft:
            self._class_choices(requirements, class_id, class_graft, cr, selections)
        subtype_grafts = [
            (subtype_id, self.catalog["grafts"]["subtypes"].get(subtype_id))
            for subtype_id in selections.get("subtypeGraftIds", [])
        ]
        for subtype_id, subtype in subtype_grafts:
            if subtype:
                self._subtype_choices(requirements, subtype_id, subtype, cr)
        template_id = selections.get("templateGraftId")
        template = self.catalog["grafts"]["templates"].get(template_id) if template_id else None
        if template:
            self._template_choices(requirements, template_id, template, cr)
        controlled = self._controlled_option_parameters(class_graft, template)
        grants = active_graft_option_grants(class_id, class_graft, subtype_grafts, template_id, template, cr, selections)
        for graft_id, grant in grants:
            self._option_parameters(
                requirements,
                grant["optionId"],
                grant.get("parameters", {}),
                f"/selections/graftOptionChoices/{graft_id}/{grant['optionId']}",
                selections,
                controlled,
            )
        for index, selected in enumerate(selections.get("options", [])):
            if isinstance(selected, dict) and selected.get("optionId") in self.catalog["options"]:
                self._option_parameters(
                    requirements,
                    selected["optionId"],
                    {},
                    f"/selections/options/{index}/parameters",
                    selections,
                    set(),
                )
        spell_list_id = selections.get("spellListId")
        spell_list = self._catalog_records("spellList").get(spell_list_id) if spell_list_id else None
        if spell_list:
            for name, spec in spell_list.get("benefit", {}).get("parameters", {}).items():
                requirements.append(self._requirement(
                    f"/selections/spellListBenefitChoices/{name}", name, spec, selections,
                    spell_list.get("sourceRef"),
                ))
        unique = {requirement["path"]: requirement for requirement in requirements}
        return [unique[path] for path in sorted(unique)]

    def _class_choices(self, output, class_id, graft, cr, selections):
        base = f"/selections/classGraftChoices"
        if graft.get("choiceSpec"):
            spec = graft["choiceSpec"]
            output.append(self._enum(f"{base}/{spec['name']}", spec["name"], spec["values"], graft))
        for spec in graft.get("abilityChoiceSpecs", []):
            output.append(self._enum(f"{base}/{spec['name']}", spec["name"], spec["values"], graft))
        for spec in graft.get("optionChoiceSpecs", []):
            count = 1 + sum(cr >= threshold for threshold in spec.get("countThresholds", [])) if spec.get("type") == "enum-array" else None
            output.append(self._enum(f"{base}/{spec['name']}", spec["name"], spec["values"], graft, array=count is not None, count=count))
        companion = graft.get("companionSpec")
        if companion:
            output.append(self._requirement(f"{base}/{companion['choiceName']}", companion["choiceName"], {"type": "string"}, selections, graft.get("sourceRef")))
        main = graft.get("choiceSpec")
        choice = selections.get("classGraftChoices", {}).get(main["name"]) if main else None
        languages = graft.get("choiceEffects", {}).get(choice, {}).get("languageValues")
        if languages:
            output.append(self._enum(f"{base}/languages", "languages", languages, graft, array=True, count=1 + int(cr >= 4)))

    def _subtype_choices(self, output, subtype_id, graft, cr):
        choice = graft.get("skillChoiceGrant")
        if choice:
            output.append(self._enum(
                f"/selections/subtypeGraftChoices/{subtype_id}/{choice['name']}", choice["name"], choice["skillIds"], graft,
            ))
        choice = graft.get("spellChoiceGrant")
        if choice:
            spell_list = self._catalog_records("spellList")[choice["spellListId"]]
            band = next(band for band in self.catalog["spellBands"] if band["minCR"] <= cr and (band["maxCR"] is None or cr <= band["maxCR"]))["id"]
            values = [entry["spellId"] for entry in spell_list["bands"][band][choice["role"]]]
            output.append(self._enum(
                f"/selections/subtypeGraftChoices/{subtype_id}/{choice['name']}", choice["name"], values, graft,
            ))

    def _template_choices(self, output, template_id, graft, cr):
        linked = graft.get("linkedOptionChoiceSpec")
        if linked:
            output.append(self._enum(
                f"/selections/templateGraftChoices/{linked['energyName']}", linked["energyName"], linked["energyValues"], graft,
            ))
            if linked.get("shapeName"):
                output.append(self._enum(
                    f"/selections/templateGraftChoices/{linked['shapeName']}", linked["shapeName"], linked["shapeValues"], graft,
                ))
        grant = graft.get("optionChoiceGrant")
        if grant and cr >= grant["minCR"]:
            count = 1 + int((cr - grant["minCR"]) / grant["perCR"])
            output.append(self._enum(
                "/selections/templateGraftChoices/optionIds", "optionIds", grant["optionIds"], graft, array=True, count=count,
            ))

    @staticmethod
    def _controlled_option_parameters(class_graft, template):
        controlled = set()
        for spec in (class_graft or {}).get("optionChoiceSpecs", []):
            controlled.add((spec["optionId"], spec["parameter"]))
        if (template or {}).get("linkedOptionChoiceSpec"):
            controlled.update({
                ("option.breath-weapon", "damageType"), ("option.breath-weapon", "shape"),
                ("option.channel-destruction", "energyType"), ("option.immunity", "immunities"),
            })
        return controlled

    def _option_parameters(self, output, option_id, fixed, base, selections, controlled):
        option = self.catalog["options"][option_id]
        for name, spec in option.get("parameters", {}).items():
            if spec.get("internal") or name in fixed or (option_id, name) in controlled:
                continue
            output.append(self._requirement(f"{base}/{name}", name, spec, selections, option.get("sourceRef")))

    def _enum(self, path, name, values, source, *, array=False, count=None):
        spec = {"type": "enum-array" if array else "enum", "values": values}
        if count is not None:
            spec.update({"minCount": count, "maxCount": count})
        return self._requirement(path, name, spec, {}, source.get("sourceRef"))

    def _requirement(self, path, name, spec, selections, source_ref):
        value_type = spec["type"]
        values = spec.get("values")
        if spec.get("catalogKind"):
            records = self._catalog_records(spec["catalogKind"])
            values = list(records)
        elif value_type == "selected-speed":
            values = list(dict.fromkeys(name for name, value in selections.get("speed", {}).items() if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0))
            value_type = "enum"
        elif value_type in {"selected-attack", "selected-attacks"}:
            values = list(dict.fromkeys(attack.get("name") for attack in selections.get("attacks", []) if isinstance(attack, dict) and isinstance(attack.get("name"), str) and attack["name"]))
            value_type = "enum" if value_type == "selected-attack" else "enum-array"
        result = {
            "path": path,
            "label": _label(name),
            "type": "enum" if spec.get("catalogKind") else value_type,
            "required": not spec.get("optional", False),
        }
        if values is not None:
            result["values"] = [{"value": value, "label": self._value_label(value, spec.get("catalogKind"))} for value in values]
        exact_count = spec.get("count", spec.get("sourceDefaultCount"))
        minimum = exact_count if exact_count is not None else spec.get("minCount")
        if minimum is None and result["required"] and result["type"] in {"enum-array", "string-array"}:
            minimum = 1
        maximum = exact_count if exact_count is not None else spec.get("maxCount")
        if minimum is not None:
            result["minCount"] = minimum
        if maximum is not None:
            result["maxCount"] = maximum
        if source_ref:
            result["sourceRefs"] = source_ref if isinstance(source_ref, list) else [source_ref]
        return result

    def _catalog_records(self, kind):
        records = {
            "spell": self.catalog["spells"], "skill": self.catalog["skills"], "spellList": self.catalog["spellLists"],
        }[kind]
        return {entry["id"]: entry for entry in records.values()}

    def _value_label(self, value, catalog_kind=None):
        if catalog_kind:
            return str(self._catalog_records(catalog_kind)[value].get("name", value))
        for records in (
            self.catalog.get("skills", {}), self.catalog.get("spells", {}), self.catalog.get("spellLists", {}),
            self.catalog.get("options", {}), *self.catalog.get("grafts", {}).values(),
        ):
            entry = next((entry for entry in records.values() if entry.get("id") == value), None)
            if entry:
                return str(entry.get("name", value))
        return _label(str(value).replace(":", " "))


def _label(value: str) -> str:
    import re
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", value).replace("-", " ").replace("_", " ")
    return words[:1].upper() + words[1:]
