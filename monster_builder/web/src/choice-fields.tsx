import { useState } from "preact/hooks";
import type { ChoiceRequirement, ChoiceValue, JsonObject } from "./types";

export interface ChoiceFieldProps {
  requirement: ChoiceRequirement;
  value: unknown;
  onChange: (value: unknown) => void;
}

export interface ChoiceFieldsProps {
  requirements: ChoiceRequirement[];
  pathPrefix: string;
  values?: JsonObject;
  onChange: (name: string, value: unknown) => void;
}

export interface ChoiceSectionProps extends ChoiceFieldsProps {
  title: string;
  description?: string;
}

export interface ChoiceGroupsProps {
  requirements: ChoiceRequirement[];
  pathPrefix: string;
  values?: JsonObject;
  title: string;
  description?: string;
  onChange: (group: string, name: string, value: unknown) => void;
}

function prefix(value: string): string {
  return value.replace(/\/$/, "");
}

function directRequirements(requirements: ChoiceRequirement[], pathPrefix: string): ChoiceRequirement[] {
  const root = prefix(pathPrefix);
  return requirements.filter((requirement) => {
    if (!requirement.path.startsWith(`${root}/`)) return false;
    return !requirement.path.slice(root.length + 1).includes("/");
  });
}

function fieldName(path: string, pathPrefix: string): string {
  return path.slice(prefix(pathPrefix).length + 1);
}

/** The only renderer for engine-provided choice requirements. */
export function ChoiceFields(props: ChoiceFieldsProps) {
  const requirements = directRequirements(props.requirements, props.pathPrefix);
  const values = props.values || {};
  return requirements.length ? <div class="builder-fields">
    {requirements.map((requirement) => {
      const name = fieldName(requirement.path, props.pathPrefix);
      return <ChoiceField key={requirement.path} requirement={requirement} value={values[name]} onChange={(value) => props.onChange(name, value)} />;
    })}
  </div> : null;
}

export function ChoiceSection(props: ChoiceSectionProps) {
  if (!directRequirements(props.requirements, props.pathPrefix).length) return null;
  return <section class="field full choice-section">
    <div class="builder-head"><div><span class="label">{props.title}</span>{props.description && <small>{props.description}</small>}</div></div>
    <ChoiceFields requirements={props.requirements} pathPrefix={props.pathPrefix} values={props.values} onChange={props.onChange} />
  </section>;
}

/** Group nested `/.../<group>/<parameter>` requirements without knowing graft IDs. */
export function ChoiceGroups(props: ChoiceGroupsProps) {
  const root = prefix(props.pathPrefix);
  const groups = new Map<string, ChoiceRequirement[]>();
  for (const requirement of props.requirements) {
    if (!requirement.path.startsWith(`${root}/`)) continue;
    const rest = requirement.path.slice(root.length + 1).split("/");
    if (rest.length !== 2) continue;
    const existing = groups.get(rest[0]) || [];
    existing.push(requirement);
    groups.set(rest[0], existing);
  }
  return <>{[...groups.entries()].map(([group, requirements]) => <ChoiceSection
    key={group}
    title={`${props.title} · ${humanize(group)}`}
    description={props.description}
    requirements={requirements}
    pathPrefix={`${root}/${group}`}
    values={objectValue(props.values?.[group])}
    onChange={(name, value) => props.onChange(group, name, value)}
  />)}</>;
}

export function ChoiceField(props: ChoiceFieldProps) {
  const requirement = props.requirement;
  const label = `${requirement.label}${requirement.required ? "" : " (optional)"}`;
  const hint = requirement.required ? undefined : "Optional source choice.";
  if (requirement.type === "enum") return <SelectChoice label={label} value={props.value} values={requirement.values || []} onChange={props.onChange} blank="Choose…" hint={hint} />;
  if (requirement.type === "enum-array") return <MultiChoice label={label} values={requirement.values || []} selected={asStrings(props.value)} minCount={requirement.minCount} maxCount={requirement.maxCount} onChange={props.onChange} hint={hint} />;
  if (requirement.type === "string-array") return <StringArrayChoice label={label} selected={asStrings(props.value)} minCount={requirement.minCount} maxCount={requirement.maxCount} onChange={props.onChange} hint={hint} />;
  if (requirement.type === "integer") return <div class="field"><label>{label}</label><input type="number" value={String(props.value ?? "")} onInput={(event) => props.onChange(event.currentTarget.value === "" ? undefined : Number(event.currentTarget.value))} />{hint && <p class="hint">{hint}</p>}</div>;
  return <div class="field"><label>{label}</label><input value={String(props.value ?? "")} onInput={(event) => props.onChange(event.currentTarget.value || undefined)} />{hint && <p class="hint">{hint}</p>}</div>;
}

function SelectChoice(props: { label: string; value: unknown; values: ChoiceValue[]; onChange: (value: unknown) => void; blank: string; hint?: string }) {
  return <div class="field"><label>{props.label}</label><select value={String(props.value ?? "")} onChange={(event) => props.onChange(event.currentTarget.value || undefined)}>
    <option value="">{props.blank}</option>
    {props.values.map((choice) => <option value={choice.value} key={choice.value}>{choice.label}</option>)}
  </select>{props.hint && <p class="hint">{props.hint}</p>}</div>;
}

function MultiChoice(props: { label: string; values: ChoiceValue[]; selected: string[]; minCount?: number; maxCount?: number; onChange: (value: unknown) => void; hint?: string }) {
  const [addValue, setAddValue] = useState("");
  const available = props.values.filter((choice) => !props.selected.includes(choice.value));
  const full = props.maxCount !== undefined && props.selected.length >= props.maxCount;
  const countHint = `${props.selected.length} selected${props.minCount !== undefined ? ` · ${props.minCount} required` : ""}${props.maxCount !== undefined ? ` · maximum ${props.maxCount}` : ""}`;
  return <div class="field full"><div class="builder-head"><div><span class="label">{props.label}</span><small>{countHint}</small></div></div>
    <div class="add-row"><select value={addValue} disabled={full || !available.length} onChange={(event) => setAddValue(event.currentTarget.value)}><option value="">Choose…</option>{available.map((choice) => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select><button type="button" class="btn primary" disabled={!addValue || full} onClick={() => { if (!addValue || full) return; props.onChange([...props.selected, addValue]); setAddValue(""); }}>Add</button></div>
    <div class="builder-list">{props.selected.map((value) => <article class="builder-card" key={value}><div class="builder-head"><div><strong>{props.values.find((choice) => choice.value === value)?.label || value}</strong><small>{value}</small></div><button type="button" class="btn small" onClick={() => props.onChange(props.selected.filter((item) => item !== value))}>Remove</button></div></article>)}</div>
    {props.hint && <p class="hint">{props.hint}</p>}
  </div>;
}

function StringArrayChoice(props: { label: string; selected: string[]; minCount?: number; maxCount?: number; onChange: (value: unknown) => void; hint?: string }) {
  const [addValue, setAddValue] = useState("");
  const full = props.maxCount !== undefined && props.selected.length >= props.maxCount;
  return <div class="field full"><div class="builder-head"><div><span class="label">{props.label}</span><small>{props.selected.length} selected{props.minCount !== undefined ? ` · ${props.minCount} required` : ""}{props.maxCount !== undefined ? ` · maximum ${props.maxCount}` : ""}</small></div></div>
    <div class="add-row"><input value={addValue} disabled={full} placeholder="Enter a value" onInput={(event) => setAddValue(event.currentTarget.value)} /><button type="button" class="btn primary" disabled={!addValue.trim() || full} onClick={() => { const value = addValue.trim(); if (!value || full || props.selected.includes(value)) return; props.onChange([...props.selected, value]); setAddValue(""); }}>Add</button></div>
    <div class="builder-list">{props.selected.map((value) => <article class="builder-card" key={value}><div class="builder-head"><strong>{value}</strong><button type="button" class="btn small" onClick={() => props.onChange(props.selected.filter((item) => item !== value))}>Remove</button></div></article>)}</div>
    {props.hint && <p class="hint">{props.hint}</p>}
  </div>;
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function humanize(value: string): string {
  return value.split(/[.:]/).filter(Boolean).map((part) => part.replaceAll("-", " ").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())).join(" — ");
}

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

/** Remove a field when it is cleared while preserving empty arrays for validation. */
export function setChoiceValue(current: JsonObject, name: string, value: unknown): JsonObject {
  const next = { ...current };
  if (value === undefined || value === "") delete next[name];
  else next[name] = value;
  return next;
}

export function setNestedChoiceValue(current: JsonObject, parent: string, child: string, name: string, value: unknown): JsonObject {
  const parentValue = objectValue(current[parent]);
  const childValue = objectValue(parentValue[child]);
  return { ...current, [parent]: { ...parentValue, [child]: setChoiceValue(childValue, name, value) } };
}