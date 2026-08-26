import { useState } from "preact/hooks";
import { StepFrame } from "../components";
import type { CatalogEntry, ChoiceValue, Dict, SelectedAttack } from "../types";
import type { EditorProps } from "./basic";

export function SkillsStep({ draft, catalog, automaticSelections, selectionBudgets, onSave, onBack }: EditorProps) {
  const existing = (draft.selections.skills as { master?: string[]; good?: string[] } | undefined) || {};
  const [master, setMaster] = useState(existing.master || []);
  const [good, setGood] = useState(existing.good || []);
  const automatic = automaticSelections.skills;
  const automaticIds = [...automatic.master, ...automatic.good].map((skill) => skill.value);
  return <StepFrame step={8} onBack={onBack} onApply={(next) => onSave({ skills: { master, good } }, {}, next)}>
    <div class="grid"><SkillPicker label="Master skills" records={catalog.skills} values={master} required={selectionBudgets.skills.master} automatic={automatic.master} unavailable={[...good, ...automaticIds]} onChange={setMaster} /><SkillPicker label="Good skills" records={catalog.skills} values={good} required={selectionBudgets.skills.good} automatic={automatic.good} unavailable={[...master, ...automaticIds]} onChange={setGood} /></div>
  </StepFrame>;
}

function SkillPicker(props: { label: string; records: Dict<CatalogEntry>; values: string[]; required: number | null; automatic: ChoiceValue[]; unavailable: string[]; onChange: (values: string[]) => void }) {
  const [addId, setAddId] = useState("");
  const available = Object.values(props.records).filter((skill) => !props.values.includes(skill.id) && !props.unavailable.includes(skill.id));
  const selected = props.values.map((id) => props.records[id]).filter(Boolean);
  return <section class="skill-picker"><div class="builder-head"><div><span class="label">{props.label}</span><small>{props.required === null ? `${props.values.length} chosen` : `${props.values.length} of ${props.required} required`} · {props.automatic.length} automatic</small></div></div>
    <div class="add-row"><div class="field"><label>Add skill</label><select value={addId} onChange={(event) => setAddId(event.currentTarget.value)}><option value="">Choose a skill…</option>{available.map((skill) => <option value={skill.id}>{skill.name}</option>)}</select></div><button type="button" class="btn primary" disabled={!addId} onClick={() => { if (!addId) return; props.onChange([...props.values, addId]); setAddId(""); }}>Add</button></div>
    <div class="builder-list">{props.automatic.map((skill) => <article class="builder-card" key={`automatic-${skill.value}`}><div class="builder-head"><div><strong>{skill.label}</strong><small>{skill.value}</small></div><span class="pill valid">Automatic</span></div></article>)}{selected.map((skill) => <article class="builder-card" key={skill.id}><div class="builder-head"><div><strong>{skill.name}</strong><small>{skill.id}</small></div><button type="button" class="btn small" onClick={() => props.onChange(props.values.filter((id) => id !== skill.id))}>Remove</button></div></article>)}</div>
    {!selected.length && !props.automatic.length && <div class="empty">No {props.label.toLowerCase()} selected.</div>}
  </section>;
}

interface AttackRow { key: string; attack: SelectedAttack }
const key = () => crypto.randomUUID();

export function DamageStep({ draft, catalog, onSave, onBack }: EditorProps) {
  const initial = ((draft.selections.attacks as SelectedAttack[] | undefined) || []).map((attack) => ({ key: key(), attack: { ...attack } }));
  const [rows, setRows] = useState<AttackRow[]>(initial);
  const [error, setError] = useState("");
  const update = (rowKey: string, values: Partial<SelectedAttack>) => setRows((current) => current.map((row) => row.key === rowKey ? { ...row, attack: { ...row.attack, ...values } } : row));
  const submit = (next: boolean) => {
    if (rows.some(({ attack }) => !attack.name.trim())) { setError("Every attack needs a name."); return; }
    setError(""); onSave({ attacks: rows.map(({ attack }) => cleanAttack(attack)) }, {}, next);
  };
  const profiles = ["weapon.high", "weapon.low", "natural.two", "natural.three"];
  const dice = ["d4", "d6", "d8", "d10", "d12", "2d6", "2d8", "3d6"];
  return <StepFrame step={9} onBack={onBack} onApply={submit}>
    <div class="add-row"><div><span class="label">Attack list</span><p class="hint">Add each weapon or natural attack, then choose its source attack profile.</p></div><button type="button" class="btn primary" onClick={() => setRows((current) => [...current, { key: key(), attack: { name: "", kind: "weapon", attackProfile: "weapon.high" } }])}>Add attack</button></div>
    <div class="builder-list">{rows.map((row) => <article class="builder-card" key={row.key}><div class="builder-head"><div><strong>{row.attack.name || "New attack"}</strong><small>Step 9 attack presentation</small></div><button type="button" class="btn small" onClick={() => setRows((current) => current.filter((item) => item.key !== row.key))}>Remove</button></div>
      <div class="builder-fields">
        <div class="field"><label>Attack name</label><input value={row.attack.name} onInput={(event) => update(row.key, { name: event.currentTarget.value })} /></div>
        <div class="field"><label>Attack profile</label><select value={row.attack.attackProfile} onChange={(event) => update(row.key, { attackProfile: event.currentTarget.value })}>{profiles.map((profile) => <option value={profile}>{profile.replace(".", " — ")}</option>)}</select></div>
        <div class="field"><label>Natural attack</label><select value={row.attack.naturalAttackId || ""} onChange={(event) => update(row.key, { naturalAttackId: event.currentTarget.value || undefined, kind: event.currentTarget.value ? "natural" : "weapon" })}><option value="">Weapon / unarmed</option>{Object.values(catalog.naturalAttacksBySize).map((attack) => <option value={attack.id}>{attack.name} — {attack.classification}, {attack.damageType}</option>)}</select></div>
        <div class="field"><label>Profile entry</label><select value={row.attack.profileEntry === undefined ? "" : String(row.attack.profileEntry)} onChange={(event) => update(row.key, { profileEntry: event.currentTarget.value === "" ? undefined : Number(event.currentTarget.value) })}><option value="">Default</option><option value="0">First profile entry</option><option value="1">Second profile entry</option><option value="2">Third profile entry</option></select></div>
        <div class="field"><label>Damage die</label><select value={row.attack.damageDie || ""} onChange={(event) => update(row.key, { damageDie: event.currentTarget.value || undefined })}><option value="">Natural attack default / choose for weapon</option>{dice.map((die) => <option value={die}>{die}</option>)}</select></div>
      </div></article>)}</div>
    {!rows.length && <div class="empty">No attacks selected yet.</div>}{error && <div class="issue invalid"><p>{error}</p></div>}
  </StepFrame>;
}

function cleanAttack(attack: SelectedAttack): SelectedAttack {
  return Object.fromEntries(Object.entries(attack).filter(([, value]) => value !== undefined && value !== "")) as unknown as SelectedAttack;
}
