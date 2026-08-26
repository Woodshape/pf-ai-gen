import { useState } from "preact/hooks";
import { StepFrame } from "../components";
import type { CatalogEntry, Dict, JsonObject, OptionDefinition, ParameterSpec, SelectedAttack, SelectedOption } from "../types";
import type { EditorProps } from "./basic";

interface OptionRow { key: string; selection: SelectedOption }
const key = () => crypto.randomUUID();

export function OptionsStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const initial = ((draft.selections.options as SelectedOption[] | undefined) || []).map((selection) => ({ key: key(), selection: { ...selection, parameters: { ...(selection.parameters || {}) } } }));
  const [rows, setRows] = useState<OptionRow[]>(initial);
  const [addId, setAddId] = useState("");
  const definitions = Object.values(catalog.options).sort((a, b) => a.name.localeCompare(b.name));
  const setParameter = (rowKey: string, name: string, value: unknown) => setRows((current) => current.map((row) => row.key === rowKey ? { ...row, selection: { ...row.selection, parameters: { ...(row.selection.parameters || {}), [name]: value } } } : row));
  return <StepFrame step={7} onBack={onBack} onApply={(next) => onSave({ options: rows.map((row) => row.selection) }, {}, next)}>
    <div class="add-row"><div class="field"><label>Add a monster option</label><select value={addId} onChange={(event) => setAddId(event.currentTarget.value)}><option value="">Choose an option…</option>{definitions.map((option) => <option value={option.id}>{option.name} — {option.category}</option>)}</select></div>
      <button type="button" class="btn primary" onClick={() => { if (!addId) return; setRows((current) => [...current, { key: key(), selection: { optionId: addId, parameters: {} } }]); setAddId(""); }}>Add option</button></div>
    <div class="builder-list">{rows.map((row) => { const definition = catalog.options[row.selection.optionId]; return <article class="builder-card" key={row.key}><div class="builder-head"><div><strong>{definition.name}</strong><small>{definition.category} · {definition.id}</small></div><button type="button" class="btn small" onClick={() => setRows((current) => current.filter((item) => item.key !== row.key))}>Remove</button></div>
      <div class="builder-fields">{Object.entries(definition.parameters || {}).filter(([, spec]) => !spec.internal).map(([name, spec]) => <OptionParameter key={name} name={name} spec={spec} value={row.selection.parameters?.[name]} attacks={(draft.selections.attacks as SelectedAttack[] | undefined) || []} catalogs={{ spell: catalog.spells, skill: catalog.skills, spellList: catalog.spellLists }} onChange={(value) => setParameter(row.key, name, value)} />)}{!Object.values(definition.parameters || {}).some((spec) => !spec.internal) && <p class="hint">This option has no choices.</p>}</div>
      <details class="rule-details"><summary>Source rule</summary>{definition.ruleText}</details></article>; })}</div>
    {!rows.length && <div class="empty">No options selected yet.</div>}
  </StepFrame>;
}

function OptionParameter(props: { name: string; spec: ParameterSpec; value: unknown; attacks: SelectedAttack[]; catalogs: Record<string, Dict<CatalogEntry>>; onChange: (value: unknown) => void }) {
  const { name, spec, value } = props;
  const label = `${name}${spec.optional ? " (optional)" : ""}`;
  if (spec.catalogKind) {
    const records = props.catalogs[spec.catalogKind] || {};
    return <div class="field"><label>{label}</label><select value={String(value || "")} onChange={(event) => props.onChange(event.currentTarget.value)}><option value="">Choose…</option>{Object.values(records).map((entry) => <option value={entry.id}>{entry.name}</option>)}</select></div>;
  }
  if (spec.type === "enum") return <div class="field"><label>{label}</label><select value={String(value || "")} onChange={(event) => props.onChange(event.currentTarget.value)}><option value="">Choose…</option>{spec.values?.map((item) => <option value={item}>{item}</option>)}</select></div>;
  if (spec.type === "enum-array") return <MultiParameter label={label} values={spec.values || []} selected={(value as string[] | undefined) || []} onChange={props.onChange} />;
  if (spec.type === "selected-attack") return <div class="field"><label>{label}</label><select value={String(value || "")} onChange={(event) => props.onChange(event.currentTarget.value)}><option value="">Choose an attack…</option>{props.attacks.map((attack) => <option value={attack.name}>{attack.name}</option>)}</select>{!props.attacks.length && <p class="hint">Create attacks in Step 9 first, then return here.</p>}</div>;
  if (spec.type === "selected-attacks") return <MultiParameter label={label} values={props.attacks.map((attack) => attack.name)} selected={(value as string[] | undefined) || []} onChange={props.onChange} />;
  if (spec.type === "integer") return <div class="field"><label>{label}</label><input type="number" value={String(value ?? "")} onInput={(event) => props.onChange(event.currentTarget.value === "" ? undefined : Number(event.currentTarget.value))} /></div>;
  if (spec.type === "string-array") return <div class="field"><label>{label}</label><input value={((value as string[] | undefined) || []).join(", ")} onInput={(event) => props.onChange(event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))} /><p class="hint">Separate multiple values with commas.</p></div>;
  return <div class="field"><label>{label}</label><input value={String(value || "")} onInput={(event) => props.onChange(event.currentTarget.value)} /></div>;
}

function MultiParameter(props: { label: string; values: string[]; selected: string[]; onChange: (value: unknown) => void }) {
  return <div class="field"><label>{props.label}</label><select multiple size={Math.min(6, Math.max(3, props.values.length))} onChange={(event) => props.onChange([...event.currentTarget.selectedOptions].map((option) => option.value))}>{props.values.map((item) => <option value={item} selected={props.selected.includes(item)}>{item}</option>)}</select><p class="hint">Use Ctrl/Cmd-click for multiple choices.</p></div>;
}
