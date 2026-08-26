import type { ComponentChildren } from "preact";
import type { CatalogEntry, Dict, SourceRef } from "./types";

export function Field(props: { label: string; value: string | number; type?: string; onInput: (value: string) => void; full?: boolean }) {
  return <div class={`field ${props.full ? "full" : ""}`}>
    <label>{props.label}</label>
    <input type={props.type || "text"} value={props.value} onInput={(event) => props.onInput(event.currentTarget.value)} />
  </div>;
}

export function Select(props: { label: string; value?: string; onChange: (value: string) => void; children: ComponentChildren; full?: boolean; multiple?: boolean; size?: number }) {
  return <div class={`field ${props.full ? "full" : ""}`}>
    <label>{props.label}</label>
    <select value={props.value} multiple={props.multiple} size={props.size} onChange={(event) => props.onChange(event.currentTarget.value)}>{props.children}</select>
  </div>;
}

export function CatalogSelect(props: { label: string; records: Dict<CatalogEntry>; value?: string; onChange: (value: string) => void; blank?: string; full?: boolean }) {
  return <Select label={props.label} value={props.value || ""} onChange={props.onChange} full={props.full}>
    <option value="">{props.blank || "Choose…"}</option>
    {Object.values(props.records).map((entry) => <option value={entry.id} key={entry.id}>{entry.name || entry.id}</option>)}
  </Select>;
}

export function MultiCatalogSelect(props: { label: string; records: Dict<CatalogEntry>; values: string[]; onChange: (values: string[]) => void; size?: number }) {
  return <div class="field">
    <label>{props.label}</label>
    <select multiple size={props.size || 12} onChange={(event) => props.onChange([...event.currentTarget.selectedOptions].map((option) => option.value))}>
      {Object.values(props.records).map((entry) => <option value={entry.id} selected={props.values.includes(entry.id)} key={entry.id}>{entry.name || entry.id}</option>)}
    </select>
    <p class="hint">Use Ctrl/Cmd-click for multiple choices.</p>
  </div>;
}

export function JsonField(props: { label: string; value: unknown; onChange: (value: unknown) => void; hint?: string }) {
  const text = JSON.stringify(props.value ?? {}, null, 2);
  return <div class="field full">
    <label>{props.label}</label>
    <textarea spellcheck={false} defaultValue={text} onInput={(event) => { try { props.onChange(JSON.parse(event.currentTarget.value || "{}")); } catch { /* keep the last valid value until the JSON is complete */ } }} />
    {props.hint && <p class="hint">{props.hint}</p>}
  </div>;
}

export function sourceText(ref?: SourceRef) {
  if (!ref) return "";
  return `${ref.file || ref.sourceId}, printed p. ${ref.printedPages?.join("–") || "?"}; lines ${ref.txtLines?.join("–") || "?"}${ref.entry ? `; ${ref.entry}` : ""}`;
}

export function Source({ entry }: { entry?: CatalogEntry }) {
  return entry?.sourceRef ? <p class="source">{sourceText(entry.sourceRef)}</p> : null;
}

export function DefinitionPreview({ entry }: { entry?: CatalogEntry }) {
  if (!entry) return null;
  const keys = ["requiredArrayId", "requiredCreatureTypeId", "requiredSubtypeId", "minCR", "maxCR", "choiceSpec", "abilityChoiceSpecs", "optionChoiceSpecs", "companionSpec", "skillChoiceGrant", "spellChoiceGrant", "linkedOptionChoiceSpec", "optionChoiceGrant", "benefit"];
  const shown: Record<string, unknown> = {};
  for (const key of keys) if (entry[key] !== undefined) shown[key] = entry[key];
  if (entry.ruleText) shown.ruleText = entry.ruleText;
  return Object.keys(shown).length ? <div class="baseline"><strong>Selected source choices</strong><pre>{JSON.stringify(shown, null, 2)}</pre></div> : null;
}

export function StepFrame(props: { step: number; children: ComponentChildren; onBack: () => void; onApply: (andContinue: boolean) => void }) {
  return <form onSubmit={(event) => { event.preventDefault(); props.onApply(false); }}>
    <div class="step-form">{props.children}</div>
    <div class="form-footer">
      <button type="button" class="btn" disabled={props.step === 0} onClick={props.onBack}>Back</button>
      <div><button type="submit" class="btn">Apply &amp; validate</button><button type="button" class="btn primary" onClick={() => props.onApply(true)}>Continue</button></div>
    </div>
  </form>;
}
