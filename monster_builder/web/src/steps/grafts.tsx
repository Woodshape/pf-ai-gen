import { useState } from "preact/hooks";
import { CatalogSelect, DefinitionPreview, Field, JsonField, MultiCatalogSelect, Select, Source, StepFrame } from "../components";
import type { CatalogEntry, Dict, JsonObject } from "../types";
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

interface SelectedSpell { spellId: string; spellLevelSource?: string; metamagic?: string[] }

export function SpellStep({ draft, catalog, evaluation, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [listId, setListId] = useState(String(selections.spellListId || ""));
  const [ability, setAbility] = useState(String(selections.spellcastingAbility || ""));
  const [levelSource, setLevelSource] = useState(String(selections.spellLevelSource || "").toLowerCase());
  const [benefit, setBenefit] = useState((selections.spellListBenefitChoices as JsonObject | undefined) || {});
  const [spells, setSpells] = useState<SelectedSpell[]>((selections.spells as SelectedSpell[] | undefined) || []);
  const entry = Object.values(catalog.spellLists).find((item) => item.id === listId);
  const levelSources = [...new Set(Object.values(catalog.spells).flatMap((spell) => Object.keys((spell.levelsByClass as JsonObject | undefined) || {})))].sort();
  const benefitParameters = ((entry?.benefit as JsonObject | undefined)?.parameters as JsonObject | undefined) || {};
  const savedSpells = (selections.spells as SelectedSpell[] | undefined) || [];
  const appliedConfiguration = listId === selections.spellListId && JSON.stringify(spells) === JSON.stringify(savedSpells);
  const resolved = appliedConfiguration ? ((((evaluation.effective as JsonObject | null | undefined)?.spells as JsonObject[] | undefined) || [])) : [];
  const resolvedSelections = resolved.map((spell) => ({ spellId: String(spell.spellId) }));
  const customize = (removeIndex?: number) => setSpells(resolvedSelections.filter((_, index) => index !== removeIndex));
  const addSpell = (spellId: string) => setSpells([...(spells.length ? spells : resolvedSelections), { spellId }]);
  return <StepFrame step={6} onBack={onBack} onApply={(next) => onSave({ spellListId: listId || undefined, spellcastingAbility: ability || undefined, spellLevelSource: levelSource || undefined, spellListBenefitChoices: benefit, spells }, {}, next)}>
    <div class="grid"><CatalogSelect label="Structured spell list" records={catalog.spellLists} value={listId} onChange={setListId} blank="None — select spells individually" />
      <Select label="Spellcasting ability" value={ability} onChange={setAbility}><option value="">Default</option>{["intelligence", "wisdom", "charisma"].map((item) => <option value={item}>{item}</option>)}</Select>
      <Select label="Preferred spell-level source" value={levelSource} onChange={setLevelSource}><option value="">Automatic per spell</option>{levelSources.map((source) => <option value={source}>{source}</option>)}</Select>
      {Object.keys(benefitParameters).length > 0 && <JsonField label="Spell-list benefit choices" value={benefit} onChange={(value) => setBenefit(value as JsonObject)} />}
      <div class="field full"><SpellPicker records={catalog.spells} values={spells} baseValues={listId && !spells.length ? resolvedSelections : []} showValues={!resolved.length} onAdd={addSpell} onChange={setSpells} /></div>
      <section class="field full"><div class="builder-head"><div><span class="label">Resolved spell loadout</span><small>{resolved.length} {spells.length ? "custom" : "generated"} spell entries using the {entry?.name || "structured"} list at CR {String(selections.cr ?? "—")}</small></div>{resolved.length > 0 && !spells.length && <button type="button" class="btn" onClick={() => customize()}>Customize loadout</button>}</div>
        {resolved.length ? <div class="builder-list spell-loadout">{resolved.map((spell, index) => <article class="builder-card" key={`${String(spell.spellId)}-${index}`}><div class="builder-head"><div><strong>{String(spell.name || spell.spellId)}</strong><small>{String(spell.frequency || "frequency not specified")} · DC {String(spell.spellDC ?? "—")}</small></div><div class="builder-actions"><span class="pill">{String(spell.role || "spell")}</span><button type="button" class="btn small" onClick={() => customize(index)}>Remove</button></div></div></article>)}</div> : <div class="empty">{listId === selections.spellListId ? "Apply a valid spell selection to see the engine-resolved loadout." : "Apply this spell-list change to preview its loadout."}</div>}
      </section>
    </div><DefinitionPreview entry={entry} /><Source entry={entry} />
  </StepFrame>;
}

function SpellPicker(props: { records: Dict<CatalogEntry>; values: SelectedSpell[]; baseValues: SelectedSpell[]; showValues: boolean; onAdd: (spellId: string) => void; onChange: (values: SelectedSpell[]) => void }) {
  const [addId, setAddId] = useState("");
  const records = Object.values(props.records).sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id));
  const selectedIds = [...props.baseValues, ...props.values].map((spell) => spell.spellId);
  const available = records.filter((spell) => !selectedIds.includes(spell.id));
  return <section class="skill-picker"><div class="builder-head"><div><span class="label">Explicit spell selections</span><small>{props.values.length} selected</small></div></div>
    <div class="add-row"><div class="field"><label>Add spell</label><select value={addId} onChange={(event) => setAddId(event.currentTarget.value)}><option value="">Choose a spell…</option>{available.map((spell) => <option value={spell.id}>{spell.name || spell.id}</option>)}</select></div><button type="button" class="btn primary" disabled={!addId} onClick={() => { if (!addId) return; props.onAdd(addId); setAddId(""); }}>Add</button></div>
    {props.baseValues.length > 0 && <p class="hint">Adding a spell converts the structured loadout to a custom one and keeps its generated spells.</p>}
    {props.showValues && <div class="builder-list">{props.values.map((selection) => { const spell = records.find((entry) => entry.id === selection.spellId); return <article class="builder-card" key={selection.spellId}><div class="builder-head"><div><strong>{spell?.name || selection.spellId}</strong><small>{selection.spellId}</small></div><button type="button" class="btn small" onClick={() => props.onChange(props.values.filter((item) => item.spellId !== selection.spellId))}>Remove</button></div></article>; })}</div>}
    {props.showValues && !props.values.length && <div class="empty">No explicit spells selected.</div>}
  </section>;
}
