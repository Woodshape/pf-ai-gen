import { useEffect, useState } from "preact/hooks";
import { ChoiceFields } from "../choice-fields";
import { StepFrame } from "../components";
import type { JsonObject, SelectedOption } from "../types";
import type { EditorProps } from "./basic";

interface OptionRow { key: string; selection: SelectedOption }
const key = () => crypto.randomUUID();

export function OptionsStep({ draft, catalog, choiceRequirements, onPreview, onSave, onBack }: EditorProps) {
  const initial = ((draft.selections.options as SelectedOption[] | undefined) || []).map((selection) => ({ key: key(), selection: { ...selection, parameters: { ...(selection.parameters || {}) } } }));
  const [rows, setRows] = useState<OptionRow[]>(initial);
  const [addId, setAddId] = useState("");
  const definitions = Object.values(catalog.options).sort((a, b) => a.name.localeCompare(b.name));
  const setParameter = (rowKey: string, name: string, value: unknown) => setRows((current) => current.map((row) => row.key === rowKey ? { ...row, selection: { ...row.selection, parameters: { ...(row.selection.parameters || {}), [name]: value } } } : row));
  useEffect(() => onPreview({ options: rows.map((row) => row.selection) }), [rows]);
  return <StepFrame step={7} onBack={onBack} onApply={(next) => onSave({ options: rows.map((row) => row.selection) }, {}, next)}>
    <div class="add-row"><div class="field"><label>Add a monster option</label><select value={addId} onChange={(event) => setAddId(event.currentTarget.value)}><option value="">Choose an option…</option>{definitions.map((option) => <option value={option.id}>{option.name} — {option.category}</option>)}</select></div>
      <button type="button" class="btn primary" onClick={() => { if (!addId) return; setRows((current) => [...current, { key: key(), selection: { optionId: addId, parameters: {} } }]); setAddId(""); }}>Add option</button></div>
    <div class="builder-list">{rows.map((row, index) => { const definition = catalog.options[row.selection.optionId]; const pathPrefix = `/selections/options/${index}/parameters`; return <article class="builder-card" key={row.key}><div class="builder-head"><div><strong>{definition.name}</strong><small>{definition.category} · {definition.id}</small></div><button type="button" class="btn small" onClick={() => setRows((current) => current.filter((item) => item.key !== row.key))}>Remove</button></div>
      <ChoiceFields requirements={choiceRequirements} pathPrefix={pathPrefix} values={row.selection.parameters} onChange={(name, value) => setParameter(row.key, name, value)} />
      {!choiceRequirements.some((requirement) => requirement.path.startsWith(`${pathPrefix}/`)) && <p class="hint">No catalog choices are required for this option.</p>}
      <details class="rule-details"><summary>Source rule</summary>{definition.ruleText}</details></article>; })}</div>
    {!rows.length && <div class="empty">No options selected yet.</div>}
  </StepFrame>;
}