import { useState } from "preact/hooks";
import { CatalogSelect, DefinitionPreview, Field, JsonField, MultiCatalogSelect, Select, Source, StepFrame } from "../components";
import type { JsonObject } from "../types";
import type { EditorProps } from "./basic";

export function PrimaryGraftStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [typeId, setTypeId] = useState(String(selections.creatureTypeGraftId || ""));
  const [classId, setClassId] = useState(String(selections.classGraftId || ""));
  const [classChoices, setClassChoices] = useState((selections.classGraftChoices as JsonObject | undefined) || {});
  const [optionChoices, setOptionChoices] = useState((selections.graftOptionChoices as JsonObject | undefined) || {});
  const selectedClass = Object.values(catalog.grafts.classGrafts).find((entry) => entry.id === classId);
  return <StepFrame step={2} onBack={onBack} onApply={(next) => onSave({ creatureTypeGraftId: typeId || undefined, classGraftId: classId || undefined, classGraftChoices: classChoices, graftOptionChoices: optionChoices }, {}, next)}>
    <div class="grid">
      <CatalogSelect label="Creature type graft" records={catalog.grafts.creatureTypes} value={typeId} onChange={setTypeId} />
      <CatalogSelect label="Primary class graft" records={catalog.grafts.classGrafts} value={classId} onChange={setClassId} blank="None" />
      <JsonField label="Class graft choices" value={classChoices} onChange={(value) => setClassChoices(value as JsonObject)} hint="Only source-defined dynamic class choices belong here." />
      <JsonField label="Automatic graft-option choices" value={optionChoices} onChange={(value) => setOptionChoices(value as JsonObject)} />
    </div>
    <DefinitionPreview entry={selectedClass} /><Source entry={selectedClass} />
  </StepFrame>;
}

export function SubtypeStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [ids, setIds] = useState<string[]>((selections.subtypeGraftIds as string[] | undefined) || []);
  const [choices, setChoices] = useState((selections.subtypeGraftChoices as JsonObject | undefined) || {});
  return <StepFrame step={3} onBack={onBack} onApply={(next) => onSave({ subtypeGraftIds: ids, subtypeGraftChoices: choices }, {}, next)}>
    <div class="grid"><div class="field full"><MultiCatalogSelect label="Subtype grafts" records={catalog.grafts.subtypes} values={ids} onChange={setIds} /></div><JsonField label="Subtype choices" value={choices} onChange={(value) => setChoices(value as JsonObject)} /></div>
    {ids.map((id) => { const entry = Object.values(catalog.grafts.subtypes).find((item) => item.id === id); return <div key={id}><DefinitionPreview entry={entry} /><Source entry={entry} /></div>; })}
  </StepFrame>;
}

export function TemplateStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [id, setId] = useState(String(selections.templateGraftId || ""));
  const [choices, setChoices] = useState((selections.templateGraftChoices as JsonObject | undefined) || {});
  const entry = Object.values(catalog.grafts.templates).find((item) => item.id === id);
  return <StepFrame step={4} onBack={onBack} onApply={(next) => onSave({ templateGraftId: id || undefined, templateGraftChoices: choices }, {}, next)}>
    <div class="grid"><CatalogSelect label="Template graft" records={catalog.grafts.templates} value={id} onChange={setId} blank="None" full /><JsonField label="Template choices" value={choices} onChange={(value) => setChoices(value as JsonObject)} /></div>
    <DefinitionPreview entry={entry} /><Source entry={entry} />
  </StepFrame>;
}

export function SizeStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [id, setId] = useState(String(selections.sizeId || ""));
  const [speed, setSpeed] = useState<JsonObject>({ ...((selections.speed as JsonObject | undefined) || {}) });
  const entry = Object.values(catalog.grafts.sizes).find((item) => item.id === id);
  return <StepFrame step={5} onBack={onBack} onApply={(next) => onSave({ sizeId: id || undefined, speed: Object.keys(speed).length ? speed : undefined }, {}, next)}>
    <div class="grid"><CatalogSelect label="Size graft" records={catalog.grafts.sizes} value={id} onChange={setId} full />
      {["land", "fly", "swim", "climb", "burrow"].map((mode) => <Field key={mode} label={`${mode[0].toUpperCase() + mode.slice(1)} speed (ft.)`} type="number" value={String(speed[mode] ?? "")} onInput={(value) => setSpeed((current) => { const next = { ...current }; if (value === "") delete next[mode]; else next[mode] = Number(value); return next; })} />)}
    </div><Source entry={entry} />
  </StepFrame>;
}

export function SpellStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [listId, setListId] = useState(String(selections.spellListId || ""));
  const [ability, setAbility] = useState(String(selections.spellcastingAbility || ""));
  const [levelSource, setLevelSource] = useState(String(selections.spellLevelSource || ""));
  const [benefit, setBenefit] = useState((selections.spellListBenefitChoices as JsonObject | undefined) || {});
  const [spells, setSpells] = useState((selections.spells as unknown[] | undefined) || []);
  const entry = Object.values(catalog.spellLists).find((item) => item.id === listId);
  return <StepFrame step={6} onBack={onBack} onApply={(next) => onSave({ spellListId: listId || undefined, spellcastingAbility: ability || undefined, spellLevelSource: levelSource || undefined, spellListBenefitChoices: benefit, spells }, {}, next)}>
    <div class="grid"><CatalogSelect label="Structured spell list" records={catalog.spellLists} value={listId} onChange={setListId} blank="None" />
      <Select label="Spellcasting ability" value={ability} onChange={setAbility}><option value="">Default</option>{["intelligence", "wisdom", "charisma"].map((item) => <option value={item}>{item}</option>)}</Select>
      <Field label="Spell-level source / class" value={levelSource} onInput={setLevelSource} />
      <JsonField label="Spell-list benefit choices" value={benefit} onChange={(value) => setBenefit(value as JsonObject)} />
      <JsonField label="Explicit spell selections" value={spells} onChange={(value) => setSpells(value as unknown[])} hint="Usually empty when a structured list supplies spells." />
    </div><DefinitionPreview entry={entry} /><Source entry={entry} />
  </StepFrame>;
}
