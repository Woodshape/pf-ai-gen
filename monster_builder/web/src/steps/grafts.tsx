import { useEffect, useState } from "preact/hooks";
import { ChoiceGroups, ChoiceSection, setChoiceValue, setNestedChoiceValue } from "../choice-fields";
import { CatalogSelect, DefinitionPreview, Field, MultiCatalogSelect, Select, Source, StepFrame } from "../components";
import type { CatalogEntry, ChoiceRequirement, Dict, JsonObject } from "../types";
import type { EditorProps } from "./basic";

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

export function PrimaryGraftStep({ draft, catalog, choiceRequirements, onPreview, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [typeId, setTypeId] = useState(String(selections.creatureTypeGraftId || ""));
  const [classId, setClassId] = useState(String(selections.classGraftId || ""));
  const [classChoices, setClassChoices] = useState((selections.classGraftChoices as JsonObject | undefined) || {});
  const [optionChoices, setOptionChoices] = useState((selections.graftOptionChoices as JsonObject | undefined) || {});
  const selectedClass = Object.values(catalog.grafts.classGrafts).find((entry) => entry.id === classId);
  const classPrefix = "/selections/classGraftChoices";
  const optionPrefix = classId ? `/selections/graftOptionChoices/${classId}` : "/selections/graftOptionChoices/__none__";
  const classOptionValues = objectValue(optionChoices[classId]);
  useEffect(() => onPreview({ creatureTypeGraftId: typeId || undefined, classGraftId: classId || undefined, classGraftChoices: classChoices, graftOptionChoices: optionChoices }), [typeId, classId, classChoices, optionChoices]);
  const chooseClass = (id: string) => {
    setClassId(id);
    setClassChoices({});
    setOptionChoices((current) => {
      const next = { ...current };
      if (classId) delete next[classId];
      return next;
    });
  };
  return <StepFrame step={2} onBack={onBack} onApply={(next) => onSave({ creatureTypeGraftId: typeId || undefined, classGraftId: classId || undefined, classGraftChoices: classChoices, graftOptionChoices: optionChoices }, {}, next)}>
    <div class="grid">
      <CatalogSelect label="Creature type graft" records={catalog.grafts.creatureTypes} value={typeId} onChange={setTypeId} />
      <CatalogSelect label="Primary class graft" records={catalog.grafts.classGrafts} value={classId} onChange={chooseClass} blank="None" />
      <ChoiceSection title="Class graft choices" description={selectedClass ? `Catalog-defined choices for ${selectedClass.name}.` : undefined} requirements={choiceRequirements} pathPrefix={classPrefix} values={classChoices} onChange={(name, value) => setClassChoices((current) => setChoiceValue(current, name, value))} />
      <ChoiceGroups title="Automatic class option" description="Catalog-defined parameters for each granted option." requirements={choiceRequirements} pathPrefix={optionPrefix} values={classOptionValues} onChange={(optionId, name, value) => setOptionChoices((current) => setNestedChoiceValue(current, classId, optionId, name, value))} />
    </div>
    <DefinitionPreview entry={selectedClass} /><Source entry={selectedClass} />
  </StepFrame>;
}

export function SubtypeStep({ draft, catalog, choiceRequirements, onPreview, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [ids, setIds] = useState<string[]>((selections.subtypeGraftIds as string[] | undefined) || []);
  const [choices, setChoices] = useState((selections.subtypeGraftChoices as JsonObject | undefined) || {});
  const [optionChoices, setOptionChoices] = useState((selections.graftOptionChoices as JsonObject | undefined) || {});
  useEffect(() => onPreview({ subtypeGraftIds: ids, subtypeGraftChoices: choices, graftOptionChoices: optionChoices }), [ids, choices, optionChoices]);
  const changeIds = (next: string[]) => {
    setIds(next);
    setChoices((current) => Object.fromEntries(next.filter((id) => current[id] !== undefined).map((id) => [id, current[id]])));
    setOptionChoices((current) => {
      const nextChoices = { ...current };
      for (const id of Object.keys(nextChoices)) if (id.startsWith("graft.subtype.") && !next.includes(id)) delete nextChoices[id];
      return nextChoices;
    });
  };
  return <StepFrame step={3} onBack={onBack} onApply={(next) => onSave({ subtypeGraftIds: ids, subtypeGraftChoices: choices, graftOptionChoices: optionChoices }, {}, next)}>
    <div class="grid"><div class="field full"><MultiCatalogSelect label="Subtype grafts" records={catalog.grafts.subtypes} values={ids} onChange={changeIds} /></div>
      {ids.map((id) => {
        const entry = Object.values(catalog.grafts.subtypes).find((item) => item.id === id);
        if (!entry) return null;
        const values = objectValue(choices[id]);
        const optionValues = objectValue(optionChoices[id]);
        return <div key={id} class="field full"><ChoiceSection title={`${entry.name} choices`} description="Catalog-defined subtype choices." requirements={choiceRequirements} pathPrefix={`/selections/subtypeGraftChoices/${id}`} values={values} onChange={(name, value) => setChoices((current) => ({ ...current, [id]: setChoiceValue(values, name, value) }))} />
          <ChoiceGroups title={`${entry.name} option`} description="Catalog-defined parameters for each granted option." requirements={choiceRequirements} pathPrefix={`/selections/graftOptionChoices/${id}`} values={optionValues} onChange={(optionId, name, value) => setOptionChoices((current) => setNestedChoiceValue(current, id, optionId, name, value))} />
          <DefinitionPreview entry={entry} /><Source entry={entry} /></div>;
      })}
    </div>
  </StepFrame>;
}

export function TemplateStep({ draft, catalog, choiceRequirements, onPreview, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [id, setId] = useState(String(selections.templateGraftId || ""));
  const [choices, setChoices] = useState((selections.templateGraftChoices as JsonObject | undefined) || {});
  const [optionChoices, setOptionChoices] = useState((selections.graftOptionChoices as JsonObject | undefined) || {});
  const entry = Object.values(catalog.grafts.templates).find((item) => item.id === id);
  const optionValues = objectValue(optionChoices[id]);
  useEffect(() => onPreview({ templateGraftId: id || undefined, templateGraftChoices: choices, graftOptionChoices: optionChoices }), [id, choices, optionChoices]);
  const chooseTemplate = (nextId: string) => {
    setId(nextId);
    setChoices({});
    setOptionChoices((current) => {
      const next = { ...current };
      if (id) delete next[id];
      return next;
    });
  };
  return <StepFrame step={4} onBack={onBack} onApply={(next) => onSave({ templateGraftId: id || undefined, templateGraftChoices: choices, graftOptionChoices: optionChoices }, {}, next)}>
    <div class="grid"><CatalogSelect label="Template graft" records={catalog.grafts.templates} value={id} onChange={chooseTemplate} blank="None" full />
      <ChoiceSection title="Template graft choices" description={entry ? `Catalog-defined choices for ${entry.name}.` : undefined} requirements={choiceRequirements} pathPrefix="/selections/templateGraftChoices" values={choices} onChange={(name, value) => setChoices((current) => setChoiceValue(current, name, value))} />
      <ChoiceGroups title="Automatic template option" description="Catalog-defined parameters for each granted option." requirements={choiceRequirements} pathPrefix={id ? `/selections/graftOptionChoices/${id}` : "/selections/graftOptionChoices/__none__"} values={optionValues} onChange={(optionId, name, value) => setOptionChoices((current) => setNestedChoiceValue(current, id, optionId, name, value))} />
    </div>
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

export function SpellStep({ draft, catalog, choiceRequirements, evaluation, onPreview, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [listId, setListId] = useState(String(selections.spellListId || ""));
  const [ability, setAbility] = useState(String(selections.spellcastingAbility || ""));
  const [levelSource, setLevelSource] = useState(String(selections.spellLevelSource || "").toLowerCase());
  const [benefit, setBenefit] = useState((selections.spellListBenefitChoices as JsonObject | undefined) || {});
  const [spells, setSpells] = useState<SelectedSpell[]>((selections.spells as SelectedSpell[] | undefined) || []);
  const entry = Object.values(catalog.spellLists).find((item) => item.id === listId);
  const levelSources = [...new Set(Object.values(catalog.spells).flatMap((spell) => Object.keys((spell.levelsByClass as JsonObject | undefined) || {})))].sort();
  const benefitText = typeof objectValue(entry?.benefit).text === "string" ? String(objectValue(entry?.benefit).text) : undefined;
  const savedSpells = (selections.spells as SelectedSpell[] | undefined) || [];
  const appliedConfiguration = listId === selections.spellListId && JSON.stringify(spells) === JSON.stringify(savedSpells);
  const resolved = appliedConfiguration ? ((((evaluation.effective as JsonObject | null | undefined)?.spells as JsonObject[] | undefined) || [])) : [];
  const resolvedSelections = resolved.map((spell) => ({ spellId: String(spell.spellId) }));
  const customize = (removeIndex?: number) => setSpells(resolvedSelections.filter((_, index) => index !== removeIndex));
  const addSpell = (spellId: string) => setSpells([...(spells.length ? spells : resolvedSelections), { spellId }]);
  useEffect(() => onPreview({ spellListId: listId || undefined, spellListBenefitChoices: benefit, spells }), [listId, benefit, spells]);
  const chooseSpellList = (nextId: string) => {
    setListId(nextId);
    setBenefit({});
  };
  return <StepFrame step={6} onBack={onBack} onApply={(next) => onSave({ spellListId: listId || undefined, spellcastingAbility: ability || undefined, spellLevelSource: levelSource || undefined, spellListBenefitChoices: Object.keys(benefit).length ? benefit : undefined, spells }, {}, next)}>
    <div class="grid"><CatalogSelect label="Structured spell list" records={catalog.spellLists} value={listId} onChange={chooseSpellList} blank="None — select spells individually" />
      <Select label="Spellcasting ability" value={ability} onChange={setAbility}><option value="">Default</option>{["intelligence", "wisdom", "charisma"].map((item) => <option value={item}>{item}</option>)}</Select>
      <Select label="Preferred spell-level source" value={levelSource} onChange={setLevelSource}><option value="">Automatic per spell</option>{levelSources.map((source) => <option value={source}>{source}</option>)}</Select>
      <ChoiceSection title="Spell-list benefit choices" description={benefitText} requirements={choiceRequirements} pathPrefix="/selections/spellListBenefitChoices" values={benefit} onChange={(name, value) => setBenefit((current) => setChoiceValue(current, name, value))} />
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