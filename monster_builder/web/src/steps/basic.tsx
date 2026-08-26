import { useState } from "preact/hooks";
import { CatalogSelect, Field, Select, StepFrame } from "../components";
import type { Catalog, Draft, JsonObject } from "../types";

export interface EditorProps {
  draft: Draft;
  catalog: Catalog;
  onSave: (selections: JsonObject, concept: JsonObject, andContinue: boolean) => void;
  onBack: () => void;
}

export function ConceptStep({ draft, onSave, onBack }: EditorProps) {
  const [concept, setConcept] = useState<JsonObject>({ ...draft.concept });
  const set = (field: string, value: unknown) => setConcept((current) => ({ ...current, [field]: value }));
  return <StepFrame step={0} onBack={onBack} onApply={(next) => onSave({}, concept, next)}>
    <div class="grid">
      <Field label="Monster name (required)" value={String(concept.name || "")} onInput={(value) => set("name", value)} />
      <Field label="Target CR (required)" type="number" value={String(concept.targetCR ?? "")} onInput={(value) => set("targetCR", value === "" ? undefined : Number(value))} />
      <Field label="Encounter role (required)" value={String(concept.role || "")} onInput={(value) => set("role", value)} />
      <Field label="Creature identity" value={String(concept.creatureType || "")} onInput={(value) => set("creatureType", value)} />
      <Field label="Concept description" value={String(concept.description || "")} onInput={(value) => set("description", value)} full />
    </div>
    <p class="source">Pathfinder Unchained, Before You Begin and Reality Check, printed pp. 194–195.</p>
  </StepFrame>;
}

export function ArrayStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const selections = draft.selections;
  const [cr, setCR] = useState<string>(String(selections.cr ?? ""));
  const [arrayId, setArrayId] = useState<string>(String(selections.arrayId || ""));
  const [abilities, setAbilities] = useState<JsonObject>({ ...((selections.abilityModifiers as JsonObject | undefined) || {}) });
  const existingSwap = (selections.saveSwap as JsonObject | undefined) || {};
  const [saveFrom, setSaveFrom] = useState(String(existingSwap.from || ""));
  const [saveTo, setSaveTo] = useState(String(existingSwap.to || ""));
  const saves = ["fortitude", "reflex", "will"];
  const array = Object.values(catalog.arrays).find((entry) => entry.id === arrayId);
  const row = array && (array.mainStatistics as Record<string, unknown> | undefined)?.[cr];
  const submit = (next: boolean) => onSave({
    cr: cr === "" ? undefined : Number(cr),
    arrayId: arrayId || undefined,
    abilityModifiers: Object.keys(abilities).length ? abilities : undefined,
    saveSwap: saveFrom && saveTo ? { from: saveFrom, to: saveTo } : undefined,
  }, {}, next);
  return <StepFrame step={1} onBack={onBack} onApply={submit}>
    <div class="grid">
      <Field label="Challenge Rating" type="number" value={cr} onInput={setCR} />
      <CatalogSelect label="Array" records={catalog.arrays} value={arrayId} onChange={setArrayId} />
      <div class="field full"><span class="label">Ability modifiers</span><div class="grid three">
        {["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"].map((ability) => <Field key={ability} label={ability[0].toUpperCase() + ability.slice(1)} type="number" value={String(abilities[ability] ?? "")} onInput={(value) => setAbilities((current) => { const next = { ...current }; if (value === "") delete next[ability]; else next[ability] = Number(value); return next; })} />)}
      </div><p class="hint">Assign exactly three positive values from the selected CR row; unlisted abilities default to +0.</p></div>
      <Select label="Swap save from" value={saveFrom} onChange={setSaveFrom}><option value="" />{saves.map((save) => <option value={save}>{save}</option>)}</Select>
      <Select label="Swap save to" value={saveTo} onChange={setSaveTo}><option value="" />{saves.map((save) => <option value={save}>{save}</option>)}</Select>
    </div>
    <div class="baseline"><strong>Source baseline preview — not recalculated by the UI</strong>{row ? <pre>{JSON.stringify(row, null, 2)}</pre> : <p class="hint">Choose a CR and array to inspect its catalog row.</p>}</div>
  </StepFrame>;
}
