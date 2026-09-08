import { useEffect, useState } from "preact/hooks";
import { ChoiceSection, humanize } from "../choice-fields";
import { CatalogSelect, Field, Select, StepFrame } from "../components";
import type { AutomaticSelections, ChoiceRequirement, Draft, Evaluation, JsonObject, NpcCatalog, SelectionBudgets } from "../types";

export const NPC_STEPS = [
  { label: "Concept", desc: "Set the encounter use and the NPC's identity." },
  { label: "Race", desc: "Choose the race and its source-defined choices." },
  { label: "Class progression", desc: "Enter the ordered class levels and class feature choices." },
  { label: "Abilities", desc: "Choose an array method, level increases, and any custom rationale." },
  { label: "Skills and feats", desc: "Use simplified or precise skills and fill source-defined feat slots." },
  { label: "Spells, gear and effects", desc: "Configure spells, equipment, and source-backed active effects." },
  { label: "Review", desc: "Inspect engine requirements, warnings, trace inputs, and the canonical preview." },
] as const;

interface Props {
  draft: Draft;
  catalog: NpcCatalog;
  evaluation: Evaluation;
  step: number;
  setStep: (step: number) => void;
  choiceRequirements: ChoiceRequirement[];
  automaticSelections: AutomaticSelections;
  selectionBudgets: SelectionBudgets;
  onPreview: (selections: JsonObject) => void;
  onSave: (selections: JsonObject, concept: JsonObject, andContinue: boolean) => void;
  onBack: () => void;
}

export function NpcWorkflow(props: Props) {
  const current = Math.max(0, Math.min(NPC_STEPS.length - 1, props.step));
  const editorProps = { ...props, step: current };
  const editors = [
    <NpcConceptStep {...editorProps} />,
    <NpcRaceStep {...editorProps} />,
    <NpcClassStep {...editorProps} />,
    <NpcAbilityStep {...editorProps} />,
    <NpcSkillsFeatsStep {...editorProps} />,
    <NpcSpellsGearStep {...editorProps} />,
    <NpcReviewStep {...editorProps} />,
  ];
  return <div class="npc-workflow">
    <aside class="panel npc-rail"><h2>NPC creation path</h2><nav aria-label="NPC creation steps">{NPC_STEPS.map((item, index) => {
      const count = props.evaluation.issues.filter((issue) => npcPathPrefixes(index).some((prefix) => issue.path.startsWith(prefix))).length;
      return <button type="button" class={index === current ? "current" : ""} onClick={() => props.setStep(index)}><span class="n">{index === 0 ? "B" : index}</span><span><strong>{item.label}</strong><small>{count ? `${count} issue(s)` : item.desc}</small></span></button>;
    })}</nav><p class="rail-note">NPC statistics are evaluated only from catalog-backed race, class, ability, skill, feat, spell, and gear selections. Missing source data stays visible as a catalog gap.</p></aside>
    <section class="panel workspace npc-workspace"><div class="step-head"><div class="kicker">NPC creation system · step {current}</div><h2>{NPC_STEPS[current].label}</h2><p>{NPC_STEPS[current].desc}</p></div>{editors[current]}</section>
  </div>;
}

function npcPathPrefixes(step: number): string[] {
  const prefixes = [["/concept", "/selections/statblockUse"], ["/selections/raceId", "/selections/racialChoices"], ["/selections/classProgression", "/selections/classFeatureChoices"], ["/selections/abilityGeneration", "/selections/levelIncreases"], ["/selections/skillGeneration", "/selections/feats"], ["/selections/spellLoadout", "/selections/gear", "/selections/gearProfile", "/selections/activeEffects"], ["/selections/details"]];
  return prefixes[step] || ["/selections"];
}

function NpcConceptStep({ draft, step, onSave, onBack }: Props) {
  const [concept, setConcept] = useState<JsonObject>({ ...draft.concept });
  const [use, setUse] = useState(String(draft.selections.statblockUse || "full"));
  const set = (field: string, value: unknown) => setConcept((current) => ({ ...current, [field]: value }));
  return <StepFrame step={step} onBack={onBack} onApply={(next) => onSave({ statblockUse: use }, concept, next)}><div class="grid">
    <Field label="NPC name (required)" value={String(concept.name || "")} onInput={(value) => set("name", value)} />
    <Field label="Target CR (optional)" type="number" value={String(concept.targetCR ?? "")} onInput={(value) => set("targetCR", value === "" ? undefined : Number(value))} />
    <Field label="Encounter role (required)" value={String(concept.role || "")} onInput={(value) => set("role", value)} />
    <Select label="Statblock use" value={use} onChange={setUse}><option value="full">Full statblock</option><option value="encounter">Encounter statblock</option></Select>
    <Field label="Description" value={String(concept.description || "")} onInput={(value) => set("description", value)} full />
  </div><p class="source">Class-based NPC creation uses the independent NPC creation system. Target CR remains a concept note and never drives statistics.</p></StepFrame>;
}

function NpcRaceStep({ draft, catalog, step, choiceRequirements, onPreview, onSave, onBack }: Props) {
  const [raceId, setRaceId] = useState(String(draft.selections.raceId || ""));
  const [choices, setChoices] = useState<JsonObject>(objectValue(draft.selections.racialChoices));
  useEffect(() => onPreview({ raceId: raceId || undefined, racialChoices: choices }), [raceId, choices]);
  const race = catalog.races[raceId];
  return <StepFrame step={step} onBack={onBack} onApply={(next) => onSave({ raceId: raceId || undefined, racialChoices: choices }, {}, next)}><div class="grid">
    <CatalogSelect label="Race" records={catalog.races} value={raceId} onChange={(value) => { setRaceId(value); setChoices({}); }} full />
    <ChoiceSection title="Racial choices" description={race ? `Source-defined choices for ${race.name}.` : undefined} requirements={choiceRequirements} pathPrefix="/selections/racialChoices" values={choices} onChange={(name, value) => setChoices((current) => ({ ...current, [name]: value }))} />
  </div>{race && <div class="baseline"><strong>Race preview</strong><pre>{JSON.stringify(pickFields(race, ["name", "sizeId", "speed", "languages", "traits", "abilityAdjustments", "senses"]), null, 2)}</pre></div>}</StepFrame>;
}

interface ClassRow { classId: string; levels: number }
interface GearRow { itemId: string; quantity: string; masterwork: boolean; enhancementBonus: string; properties: string }
function NpcClassStep({ draft, catalog, step, choiceRequirements, onPreview, onSave, onBack }: Props) {
  const initial = Array.isArray(draft.selections.classProgression) ? draft.selections.classProgression.filter(isClassRow) : [];
  const [rows, setRows] = useState<ClassRow[]>(initial);
  const [choices, setChoices] = useState<JsonObject>(objectValue(draft.selections.classFeatureChoices));
  const classes = Object.values(catalog.classes);
  useEffect(() => onPreview({ classProgression: rows, classFeatureChoices: choices }), [rows, choices]);
  const addClass = () => { const used = new Set(rows.map((row) => row.classId)); const entry = classes.find((candidate) => !used.has(candidate.id)); if (entry) setRows((current) => [...current, { classId: entry.id, levels: 1 }]); };
  return <StepFrame step={step} onBack={onBack} onApply={(next) => onSave({ classProgression: rows, classFeatureChoices: choices }, {}, next)}>
    <div class="add-row"><div><span class="label">Ordered classes</span><p class="hint">The first row is primary. Later rows are multiclass progressions and remain in the entered order.</p></div><button type="button" class="btn primary" disabled={rows.length >= classes.length} onClick={addClass}>Add class</button></div>
    <div class="builder-list">{rows.map((row, index) => <article class="builder-card" key={`${index}-${row.classId}`}><div class="builder-head"><div><strong>{index === 0 ? "Primary class" : `Class ${index + 1}`}</strong><small>{row.classId}</small></div><button type="button" class="btn small" onClick={() => setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}>Remove</button></div><div class="builder-fields"><Select label="Class" value={row.classId} onChange={(value) => setRows((current) => current.map((item, rowIndex) => rowIndex === index ? { ...item, classId: value } : item))}>{classes.filter((entry) => entry.id === row.classId || !rows.some((item, rowIndex) => rowIndex !== index && item.classId === entry.id)).map((entry) => { const unresolved = entry.catalogStatus !== undefined && entry.catalogStatus !== "resolved"; return <option value={entry.id} disabled={unresolved}>{entry.name}{unresolved ? " — not yet source-resolved" : ""}</option>; })}</Select><Field label="Levels" type="number" value={String(row.levels)} onInput={(value) => setRows((current) => current.map((item, rowIndex) => rowIndex === index ? { ...item, levels: Math.max(1, Number(value) || 1) } : item))} /></div></article>)}</div>
    {!rows.length && <div class="empty">Add the primary NPC class.</div>}
    <ChoiceSection title="Class feature choices" description="Only source-defined class choices are accepted." requirements={choiceRequirements} pathPrefix="/selections/classFeatureChoices" values={choices} onChange={(name, value) => setChoices((current) => ({ ...current, [name]: value }))} />
  </StepFrame>;
}

const ABILITIES = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"] as const;
function abilityLabel(value: string): string { return value.charAt(0).toUpperCase() + value.slice(1); }
function abilityEntryValue(value: unknown, fallback: JsonObject): JsonObject {
  const map = objectValue(value);
  return ABILITIES.reduce<JsonObject>((out, ability) => {
    const score = map[ability] ?? fallback[ability];
    if (score !== undefined && score !== "") out[ability] = String(score);
    return out;
  }, {});
}
function increaseRows(value: unknown): Array<{ level: string; ability: string }> {
  const map = objectValue(value);
  return Object.entries(map).map(([level, ability]) => ({ level, ability: String(ability ?? "") }));
}

function NpcAbilityStep({ draft, catalog, step, onSave, onBack }: Props) {
  const current = objectValue(draft.selections.abilityGeneration);
  const [method, setMethod] = useState(typeof current.method === "string" ? current.method : "assigned-array");
  const [arrayId, setArrayId] = useState(String(current.arrayId || "npc-ability-array.heroic"));
  const array = catalog.abilityArrays[arrayId];
  const pool = Array.isArray(array?.scores) ? [...(array.scores as number[])].sort((a, b) => b - a) : [];
  const poolMap = (source: unknown): JsonObject => { const values = Array.isArray(source) ? [...(source as number[])].sort((a, b) => b - a) : []; return Object.fromEntries(ABILITIES.map((ability, index) => [ability, values[index]])); };
  const [scores, setScores] = useState<JsonObject>(() => {
    const stored = current.scores || current.assignments;
    if (stored && typeof stored === "object" && !Array.isArray(stored)) return abilityEntryValue(stored, {});
    return method === "assigned-array" ? poolMap(array?.scores) : {};
  });
  const [rows, setRows] = useState<Array<{ level: string; ability: string }>>(increaseRows(draft.selections.levelIncreases));
  const [arrayIdTouched, setArrayIdTouched] = useState(Boolean(current.arrayId));
  useEffect(() => { if (method === "assigned-array" && !arrayIdTouched) setScores(poolMap(array?.scores)); }, [method, arrayId, arrayIdTouched]);
  const setScore = (ability: string, value: string) => setScores((currentScores) => (
    value === ""
      ? Object.fromEntries(Object.entries(currentScores).filter(([key]) => key !== ability))
      : { ...currentScores, [ability]: value }
  ));
  const setRow = (index: number, field: "level" | "ability", value: string) => setRows((currentRows) => currentRows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
  const addRow = () => setRows((currentRows) => [...currentRows, { level: "", ability: "" }]);
  const submit = (next: boolean) => {
    const increases = Object.fromEntries(rows.filter((row) => row.level !== "" && row.ability !== "").map((row) => [row.level, row.ability]));
    const numericScores = method === "assigned-array" ? Object.fromEntries(Object.entries(scores).filter(([, score]) => score !== "").map(([ability, score]) => [ability, Number(score)])) : undefined;
    onSave({ abilityGeneration: { method, arrayId: arrayId || undefined, scores: numericScores }, levelIncreases: Object.keys(increases).length ? increases : undefined }, {}, next);
  };
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    <Select label="Ability generation" value={method} onChange={(value) => { setMethod(value); setScores(value === "assigned-array" ? poolMap(array?.scores) : {}); setArrayIdTouched(true); }}>
      {Object.keys(objectValue(array?.presets)).map((name) => <option value={`${name}-preset`} key={name}>{humanize(name)} preset</option>)}<option value="assigned-array">Assigned array</option>
    </Select>
    {method === "assigned-array" ? <CatalogSelect label="NPC ability array" records={catalog.abilityArrays} value={arrayId} onChange={(value) => { setArrayId(value); setArrayIdTouched(true); setScores(poolMap(catalog.abilityArrays[value]?.scores)); }} /> : <div class="field"><label>NPC ability array</label><span class="hint">{(catalog.abilityArrays[arrayId]?.name || arrayId)} — the {method.replace("-preset", "")} preset assigns these scores automatically.</span></div>}
    {method === "assigned-array" && <section class="field full"><div class="builder-head"><div><span class="label">Assigned ability scores</span><small>Assign each of the array's {pool.length} values to an ability; values already taken are hidden from the other selects.</small></div></div><div class="grid three">{ABILITIES.map((ability) => {
      const taken = ABILITIES.filter((other) => other !== ability).map((other) => String(scores[other] ?? ""));
      return <div class="field" key={ability}><label>{abilityLabel(ability)}</label><select value={String(scores[ability] ?? "")} onChange={(event) => setScore(ability, event.currentTarget.value)}><option value="">Choose…</option>{pool.filter((value) => !taken.includes(String(value))).map((value) => <option value={value} key={value}>{value}</option>)}</select></div>;
    })}</div></section>}
    <section class="field full"><div class="builder-head"><div><span class="label">Level increases</span><small>Ability score increases gained at class levels (e.g. the 4th-level increase).</small></div><button type="button" class="btn small" onClick={addRow}>Add increase</button></div>
      <div class="builder-list">{rows.length ? rows.map((row, index) => <div class="builder-card"><div class="builder-fields"><div class="field"><label>Level</label><input type="number" min="1" value={row.level} onInput={(event) => setRow(index, "level", event.currentTarget.value)} /></div><div class="field"><label>Ability</label><select value={row.ability} onChange={(event) => setRow(index, "ability", event.currentTarget.value)}><option value="">Choose…</option>{ABILITIES.map((ability) => <option value={ability} key={ability}>{abilityLabel(ability)}</option>)}</select></div></div><button type="button" class="btn small" onClick={() => setRows((currentRows) => currentRows.filter((_, rowIndex) => rowIndex !== index))}>Remove</button></div>) : <div class="empty">No level increases. Add one to give an ability bonus at a class level.</div>}</div>
    </section>
    <p class="hint full">Computed scores, modifiers, BAB, saves, and defenses are preview-only. The engine rejects them if placed in the draft. Only the catalog's supported methods are shown.</p>
  </div></StepFrame>;
}

function NpcSkillsFeatsStep({ draft, catalog, step, selectionBudgets, choiceRequirements, onSave, onBack }: Props) {
  const generation = objectValue(draft.selections.skillGeneration);
  const [combatOptions, setCombatOptions] = useState<JsonObject[]>(Array.isArray(draft.selections.combatOptions) ? draft.selections.combatOptions.map(objectValue) : []);
  const routineFeats = choiceRequirements.find((entry) => entry.path === "/selections/combatOptions")?.values || [];
  const weaponChoices = Object.values(catalog.items).filter((item) => item.category === "weapon" && item.catalogStatus === "resolved");
  const updateRoutine = (index: number, field: string, value: unknown) => setCombatOptions((current) => current.map((row, i) => i === index ? { ...row, [field]: value } : row));
  const [method, setMethod] = useState(String(generation.method || "simplified"));
  const [skills, setSkills] = useState<string[]>(Array.isArray(generation.skills) ? generation.skills.filter((value): value is string => typeof value === "string") : []);
  const storedRanks = objectValue(generation.ranks);
  const [ranks, setRanks] = useState<JsonObject>(() => Object.fromEntries(Object.entries(storedRanks).map(([skill, rank]) => [skill, String(rank ?? "")])));
  const selectedFeats = Array.isArray(draft.selections.feats) ? draft.selections.feats.filter((item): item is JsonObject => Boolean(item && typeof item === "object" && typeof (item as JsonObject).slotId === "string")) : [];
  const [featsBySlot, setFeatsBySlot] = useState<JsonObject>(Object.fromEntries(selectedFeats.map((item) => [String(item.slotId), item.featId ?? ""])));
  const [addSkill, setAddSkill] = useState("");
  const [specialties, setSpecialties] = useState<JsonObject>(objectValue(generation.specialties));
  const [untrained, setUntrained] = useState<string[]>(Array.isArray(generation.includeUntrained) ? generation.includeUntrained as string[] : []);
  const [languages, setLanguages] = useState(Array.isArray(generation.languages) ? generation.languages.join(", ") : "");
  const [choicesBySlot, setChoicesBySlot] = useState<JsonObject>(Object.fromEntries(selectedFeats.map((item) => [String(item.slotId), item])));
  const featChoice = (slotId: string) => {
    const feat = catalog.feats[String(featsBySlot[slotId])];
    const category = objectValue(feat?.effects).weaponProficiencyCategory;
    const choice = objectValue(feat?.choice);
    return { feat, field: String(choice.field || (category ? "weaponId" : "")), category, values: choice.values };
  };
  const choiceControl = (slotId: string) => {
    const { feat, field, category, values } = featChoice(slotId);
    const stored = objectValue(choicesBySlot[slotId])[field];
    const update = (value: unknown) => setChoicesBySlot((current) => ({ ...current, [slotId]: { ...objectValue(current[slotId]), [field]: value } }));
    const records = field === "weaponId" ? Object.values(catalog.items).filter((item) => item.catalogStatus === "resolved" && item.category === "weapon" && (!category || objectValue(item.effects).weaponCategory === category))
      : field === "skillId" ? Object.values(catalog.skills) : field === "spellIds" ? Object.values(catalog.spells) : [];
    return <>{feat && <details><summary>{String(feat.supportStatus || "Feat rules")}{Array.isArray(feat.treatments) ? ` · ${feat.treatments.join(" / ")}` : ""}</summary><p>{String(feat.rulesText || "")}</p>{Boolean(feat.supportLimitations) && <p class="hint">{String(feat.supportLimitations)}</p>}</details>}
      {field && (field === "spellIds" ? <div class="field"><label for={`feat-${slotId}`}>Spells</label><select id={`feat-${slotId}`} multiple onChange={(event) => update(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{records.map((record) => <option value={record.id} selected={Array.isArray(stored) && stored.includes(record.id)}>{record.name}</option>)}</select></div>
        : <Select label={humanize(field)} value={String(stored ?? "")} onChange={update}><option value="">Choose…</option>{records.map((record) => <option value={record.id}>{record.name}</option>)}{Array.isArray(values) && values.map((value) => <option value={String(value)}>{humanize(String(value))}</option>)}</Select>)}
    </>;
  };
  const skillBudget = objectValue(selectionBudgets?.skills);
  const specialtyField = (id: string) => catalog.skills[id]?.hasSpecialty ? <Field label={`${catalog.skills[id].name} specialty`} value={String(specialties[id] ?? "")} onInput={(value) => setSpecialties((current) => ({ ...current, [id]: value }))} /> : null;
  const slots = Array.isArray(selectionBudgets?.feats?.slots) ? selectionBudgets.feats.slots : [];
  const allFeats = Object.values(catalog.feats || {}).sort((a, b) => a.name.localeCompare(b.name));
  const available = Object.values(catalog.skills).filter((skill) => !skills.includes(skill.id)).sort((a, b) => a.name.localeCompare(b.name));
  const submit = (next: boolean) => {
    const numericRanks = Object.fromEntries(Object.entries(ranks).filter(([, rank]) => rank !== "" && Number(rank) > 0).map(([skill, rank]) => [skill, Number(rank)]));
    const feats = slots.filter((slot) => featsBySlot[slot.slotId]).map((slot) => {
      const { field } = featChoice(slot.slotId);
      const value = objectValue(choicesBySlot[slot.slotId])[field];
      return { slotId: slot.slotId, featId: featsBySlot[slot.slotId], ...(field && value ? { [field]: value } : {}) };
    });
    const displayed = new Set([...(method === "precise" ? Object.keys(numericRanks) : skills), ...untrained]);
    const selectedSpecialties = Object.fromEntries(Object.entries(specialties).filter(([id, value]) => displayed.has(id) && String(value).trim()));
    onSave({ skillGeneration: { method, ...(method === "precise" ? { ranks: numericRanks } : { skills }),
      includeUntrained: untrained, specialties: selectedSpecialties, languages: languages.split(",").map((value) => value.trim()).filter(Boolean) }, feats,
      combatOptions: combatOptions.map((row) => Object.fromEntries(Object.entries(row).filter(([, value]) => value !== ""))) }, {}, next);
  };
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    <Select label="Skill method" value={method} onChange={setMethod}><option value="simplified">Simplified skills (one or two classes)</option><option value="precise">Precise skill ranks</option></Select>
    <p class="hint">Rank budget: {String(skillBudget.rankBudget ?? "—")}; maximum ranks per skill: {String(skillBudget.maxRanks ?? "—")}.</p>
    <div class="field"><label for="npc-untrained-skills">Also display untrained skills</label><select id="npc-untrained-skills" multiple onChange={(event) => setUntrained(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{Object.values(catalog.skills).filter((skill) => !skill.trainedOnly || skill.group === "knowledge").map((skill) => <option value={skill.id} selected={untrained.includes(skill.id)} key={skill.id}>{skill.name}</option>)}</select></div>
    <Field label="Languages learned through Linguistics (comma-separated)" value={languages} onInput={setLanguages} full />
    {method === "simplified" ? <div class="field"><label>Add simplified skill</label><div class="add-row"><select value={addSkill} onChange={(event) => setAddSkill(event.currentTarget.value)}><option value="">Choose a skill…</option>{available.map((skill) => <option value={skill.id}>{skill.name}</option>)}</select><button type="button" class="btn" disabled={!addSkill} onClick={() => { setSkills([...skills, addSkill]); setAddSkill(""); }}>Add</button></div></div> : <div class="field"><label>Precise skill ranks</label><span class="hint">Set a rank value for each trained skill; the engine validates the class rank budget on review.</span></div>}
    {method === "simplified" ? <div class="field full"><div class="builder-list">{skills.map((id) => <div class="builder-card"><div class="builder-head"><strong>{catalog.skills[id]?.name || id}</strong><button type="button" class="btn small" onClick={() => setSkills(skills.filter((value) => value !== id))}>Remove</button></div>{specialtyField(id)}</div>)}</div>{!skills.length && <div class="empty">No simplified skills. Pick from the list to add class skills.</div>}</div>
      : <section class="field full"><div class="builder-head"><div><span class="label">Skill ranks</span><small>Ranks assigned to skills. Leave 0 for untrained skills.</small></div></div><div class="builder-list">{Object.values(catalog.skills).sort((a, b) => a.name.localeCompare(b.name)).map((skill) => <div class="builder-card"><div class="builder-fields"><div class="field"><label>{skill.name}</label><input type="number" min="0" value={String(ranks[skill.id] ?? "")} onInput={(event) => setRanks((current) => (event.currentTarget.value === "" ? Object.fromEntries(Object.entries(current).filter(([key]) => key !== skill.id)) : { ...current, [skill.id]: event.currentTarget.value }))} /></div>{specialtyField(skill.id)}</div></div>)}</div></section>}
    <section class="field full"><div class="builder-head"><div><span class="label">Feats</span><small>{slots.length} feat slot(s). Prerequisites are checked at acquisition level. B: base modifier; R: conditional; A: optional routine; GM: rules permission; M: metamagic ownership.</small></div></div>
      <div class="builder-list">{slots.length ? slots.map((slot) => <div class="builder-card" key={slot.slotId}><div class="builder-fields"><div class="field"><label>{humanize(slot.slotId)}</label><select value={String(featsBySlot[slot.slotId] ?? "")} onChange={(event) => setFeatsBySlot((current) => (event.currentTarget.value === "" ? Object.fromEntries(Object.entries(current).filter(([key]) => key !== slot.slotId)) : { ...current, [slot.slotId]: event.currentTarget.value }))}><option value="">Choose a feat…</option>{allFeats.map((feat) => { const unresolved = feat.catalogStatus !== undefined && feat.catalogStatus !== "resolved"; const missingEffects = feat.supportStatus === "selection-only"; return <option value={feat.id} key={feat.id} disabled={unresolved || missingEffects}>{feat.name}{unresolved ? " — not yet source-resolved" : missingEffects ? " — calculation not implemented" : ""}</option>; })}</select></div>
        {choiceControl(slot.slotId)}
      </div></div>) : <div class="empty">No feat slots for the current level.</div>}</div>
    </section>
    <section class="field full"><h3>Optional combat routines</h3><p class="hint">These never replace base statistics. Choose equipped weapons and owned feats. Selecting Point-Blank Shot describes a routine within 30 feet. Incompatible combinations are rejected on review.</p>
      {combatOptions.map((row, index) => <div class="builder-card" key={index}><div class="builder-fields">
        <Select label="Weapon / primary hand" value={String(row.weaponId || "")} onChange={(value) => updateRoutine(index, "weaponId", value)}><option value="">Choose…</option><option value="unarmed-strike">Unarmed strike (requires Improved Unarmed Strike)</option>{weaponChoices.map((item) => <option value={item.id}>{item.name}</option>)}</Select>
        <Select label="Off-hand weapon (two-weapon routine only)" value={String(row.offHandWeaponId || "")} onChange={(value) => updateRoutine(index, "offHandWeaponId", value)}><option value="">None</option><option value="unarmed-strike">Unarmed strike</option>{weaponChoices.map((item) => <option value={item.id}>{item.name}</option>)}</Select>
        <Select label="Action" value={String(row.action || "attack")} onChange={(value) => updateRoutine(index, "action", value)}><option value="attack">Single attack</option><option value="full-attack">Full attack</option></Select>
        <div class="field"><label for={`routine-options-${index}`}>Combine feat options</label><select id={`routine-options-${index}`} multiple onChange={(event) => updateRoutine(index, "options", Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{routineFeats.map((feat) => <option value={feat.value} selected={Array.isArray(row.options) && row.options.includes(feat.value)}>{feat.label}</option>)}</select></div>
        <button type="button" class="btn" onClick={() => setCombatOptions(combatOptions.filter((_, i) => i !== index))}>Remove routine</button>
      </div></div>)}
      <button type="button" class="btn" onClick={() => setCombatOptions([...combatOptions, { weaponId: "", action: "attack", options: [] }])}>Add combat routine</button>
    </section>
  </div><p class="hint">One shared skill calculation applies ranks, class bonuses, abilities, size, racial modifiers and armor penalties. Three or more classes require precise ranks.</p></StepFrame>;
}

function NpcSpellsGearStep({ draft, catalog, step, choiceRequirements, selectionBudgets, onSave, onBack }: Props) {
  const loadout = objectValue(draft.selections.spellLoadout);
  const profile = objectValue(draft.selections.gearProfile);
  const classId = selectionBudgets?.spells?.classId || "";
  const classKey = classId.replace("npc-class.", "");
  const sections: Array<{ field: string; label: string; hint: string }> = choiceRequirements
    .filter((entry) => entry.path.startsWith("/selections/spellLoadout/"))
    .map((entry) => ({ field: entry.path.split("/").at(-1)!, label: entry.label, hint: "Choose spells for the source-defined slots." }));
  const [progression, setProgression] = useState(String(profile.experienceProgression || "medium"));
  const [fantasy, setFantasy] = useState(String(profile.fantasyLevel || "normal"));
  const gear = Array.isArray(draft.selections.gear) ? draft.selections.gear.filter((item): item is JsonObject => Boolean(item && typeof item === "object" && typeof (item as JsonObject).itemId === "string")) : [];
  const [gearRows, setGearRows] = useState<GearRow[]>(gear.map((item) => ({ itemId: String(item.itemId), quantity: String(item.quantity ?? 1), masterwork: item.masterwork === true, enhancementBonus: item.enhancementBonus === undefined ? "" : String(item.enhancementBonus), properties: Array.isArray(item.properties) ? item.properties.join(", ") : Array.isArray(item.propertyIds) ? item.propertyIds.join(", ") : "" })));
  const [descriptiveGear, setDescriptiveGear] = useState(Array.isArray(draft.selections.gear) ? draft.selections.gear.filter((item): item is string => typeof item === "string").join("\n") : "");
  const [activeEffects, setActiveEffects] = useState<JsonObject[]>(Array.isArray(draft.selections.activeEffects) ? draft.selections.activeEffects.map(objectValue) : []);
  const effectRecords = catalog.activeEffects || {};
  const setEffect = (index: number, change: JsonObject) => setActiveEffects((rows) => rows.map((row, i) => i === index ? { ...row, ...change } : row));
  const selectEffect = (index: number, effectId: string) => {
    const record = effectRecords[effectId];
    const minimum = Number(objectValue((record?.tiers as unknown[] | undefined)?.[0]).level || 1);
    setActiveEffects((rows) => rows.map((row, i) => i !== index ? row : {
      effectId, sourceLevel: Math.max(Number(row.sourceLevel) || 1, minimum), enabled: row.enabled !== false,
      sourceName: row.sourceName, remainingDuration: row.remainingDuration,
      ...(Array.isArray(record?.parameters) && record.parameters.includes("energyType") ? { energyType: "fire" } : {}),
      ...(Array.isArray(record?.parameters) && record.parameters.includes("skillId") ? { skillId: "skill.acrobatics" } : {}),
    }));
  };
  const [addGear, setAddGear] = useState("");
  const [addGearQty, setAddGearQty] = useState("1");
  const gearUsed = new Set(gearRows.map((row) => row.itemId));
  const gearItems = Object.values(catalog.items || {}).sort((a, b) => a.name.localeCompare(b.name));
  const spellLevels = Object.keys(objectValue(selectionBudgets?.spells?.levels)).map(Number).sort((a, b) => a - b);
  const spellsForLevel = (level: number) => Object.values(catalog.spells || {}).filter((spell) => Number((spell.levelsByClass as Record<string, number> | undefined)?.[classKey]) === level).sort((a, b) => a.name.localeCompare(b.name));
  const [loadoutRows, setLoadoutRows] = useState<JsonObject>(() => {
    const result: JsonObject = {};
    for (const section of sections) {
      const stored = objectValue(loadout[section.field]);
      result[section.field] = Object.fromEntries(Object.entries(stored).map(([level, ids]) => [level, Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : []]));
    }
    return result;
  });
  const [pickers, setPickers] = useState<JsonObject>(() => Object.fromEntries(sections.map((section) => [section.field, {}])));
  const setLoadout = (field: string, level: string, ids: string[]) => setLoadoutRows((current) => ({ ...current, [field]: { ...objectValue(current[field]), [level]: ids } }));
  const setPicker = (field: string, level: string, value: string) => setPickers((current) => ({ ...current, [field]: { ...objectValue(current[field]), [level]: value } }));
  const budget = objectValue(selectionBudgets?.spells?.levels as unknown);
  const slotCount = (field: string, level: string) => {
    const entry = budget[level];
    if (field === "known" && typeof entry === "number") return String(entry);
    if (entry && typeof entry === "object" && !Array.isArray(entry)) {
      const slots = entry as JsonObject;
      return field === "domainPrepared" ? String(slots.domain ?? 0) : String(Number(slots.total ?? 0) - Number(slots.domain ?? 0));
    }
    return "";
  };
  const submit = (next: boolean) => {
    const spellLoadout = Object.fromEntries(sections.map((section) => [section.field, objectValue(loadoutRows[section.field])]));
    const cleanedGear = gearRows.filter((row) => row.itemId).map((row) => {
      const item: JsonObject = { itemId: row.itemId, quantity: Math.max(1, Number(row.quantity) || 1) };
      if (row.masterwork) item.masterwork = true;
      const enhancement = Number(row.enhancementBonus);
      if (Number.isInteger(enhancement) && enhancement > 0) item.enhancementBonus = enhancement;
      const properties = row.properties.split(",").map((value) => value.trim()).filter(Boolean);
      if (properties.length) item.properties = properties;
      return item;
    });
    onSave({ activeEffects, spellLoadout: sections.length ? spellLoadout : undefined, gearProfile: { experienceProgression: progression, fantasyLevel: fantasy }, gear: [...cleanedGear, ...descriptiveGear.split("\n").map((name) => name.trim()).filter(Boolean)] }, {}, next);
  };
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    {sections.length ? sections.map((section) => <section class="field full" key={section.field}><div class="builder-head"><div><span class="label">{section.label}</span><small>{section.hint}</small></div></div><div class="builder-list">{spellLevels.filter((level) => section.field !== "domainPrepared" || Number(slotCount(section.field, String(level))) > 0).map((level) => {
      const ids = (objectValue(loadoutRows[section.field])[String(level)] || []) as string[];
      const chosen = String(objectValue(pickers[section.field])[String(level)] ?? "");
      const slots = slotCount(section.field, String(level));
      return <div class="builder-card" key={level}><div class="builder-head"><div><strong>Level {level}</strong><small>{ids.length} chosen{slots ? ` · ${slots} slot(s)` : ""}</small></div></div><div class="add-row"><select value={String(chosen)} onChange={(event) => setPicker(section.field, String(level), event.currentTarget.value)}><option value="">Choose a level-{level} spell…</option>{spellsForLevel(level).filter((spell) => section.field !== "known" || !ids.includes(spell.id)).map((spell) => <option value={spell.id} key={spell.id}>{spell.name}</option>)}</select><button type="button" class="btn" disabled={!chosen} onClick={() => { if (!chosen) return; setLoadout(section.field, String(level), [...ids, chosen]); setPicker(section.field, String(level), ""); }}>Add</button></div><div class="builder-list">{ids.map((id, index) => <div class="builder-card" key={`${id}-${index}`}><div class="builder-head"><div><strong>{catalog.spells[id]?.name || id}</strong></div><button type="button" class="btn small" onClick={() => setLoadout(section.field, String(level), ids.filter((_, position) => position !== index))}>Remove</button></div></div>)}</div></div>;
    })}</div></section>) : <div class="empty">The current class has no source-backed spell list; the loadout stays empty.</div>}
    <section class="field full"><h3>Active Effects</h3><p class="hint">Effects are already active on this NPC. Use the supplying caster or class level, not necessarily the recipient's level. The GM verifies legal activation, targets and source ownership; this does not grant spells or class features. Duration, spell slots and performance/rage rounds are tracked in play. Same-type bonuses overlap.</p>
      <div class="builder-list">{activeEffects.map((row, index) => {
        const record = effectRecords[String(row.effectId)];
        const parameters = Array.isArray(record?.parameters) ? record.parameters : [];
        return <article class="builder-card" key={index}><div class="builder-fields">
          <Select label={`Effect ${index + 1}`} value={String(row.effectId || "")} onChange={(id) => selectEffect(index, id)}>{Object.values(effectRecords).filter((effect) => effect.catalogStatus === "resolved").map((effect) => <option value={effect.id} key={effect.id}>{effect.name}</option>)}</Select>
          <Field label="Source caster / class level (1–20)" type="number" value={String(row.sourceLevel ?? 1)} onInput={(value) => setEffect(index, { sourceLevel: Number(value) })} />
          <label class="field"><span>Active</span><input type="checkbox" checked={row.enabled !== false} onChange={(event) => setEffect(index, { enabled: event.currentTarget.checked })} /></label>
          {parameters.includes("energyType") && <Select label="Energy type" value={String(row.energyType || "fire")} onChange={(value) => setEffect(index, { energyType: value })}>{["acid", "cold", "electricity", "fire", "sonic"].map((energy) => <option value={energy}>{humanize(energy)}</option>)}</Select>}
          {parameters.includes("skillId") && <CatalogSelect label="Affected skill" records={catalog.skills} value={String(row.skillId || "")} onChange={(value) => setEffect(index, { skillId: value })} />}
          <Field label="Source name (optional)" value={String(row.sourceName || "")} onInput={(value) => setEffect(index, { sourceName: value || undefined })} />
          <Field label="Remaining duration (GM tracked, optional)" value={String(row.remainingDuration || "")} onInput={(value) => setEffect(index, { remainingDuration: value || undefined })} />
        </div><p class="hint">{String(record?.rulesText || "")}</p><button type="button" class="btn small" onClick={() => setActiveEffects((rows) => rows.filter((_, i) => i !== index))}>Remove effect</button></article>;
      })}</div>
      <button type="button" class="btn" onClick={() => setActiveEffects((rows) => [...rows, { effectId: "npc-effect.mage-armor", sourceLevel: 1, enabled: true }])}>Add active effect</button>
    </section>
    <Select label="Experience progression" value={progression} onChange={setProgression}><option value="slow">Slow</option><option value="medium">Medium</option><option value="fast">Fast</option></Select>
    <Select label="Fantasy level" value={fantasy} onChange={setFantasy}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></Select>
    <section class="field full"><div class="builder-head"><div><span class="label">Mechanical equipment</span><small>These catalog items contribute rules and prices to this statblock. Use descriptive equipment below for everything else.</small></div></div>
      <div class="add-row"><select value={addGear} onChange={(event) => setAddGear(event.currentTarget.value)}><option value="">Choose an item…</option>{gearItems.filter((item) => !gearUsed.has(item.id)).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><input type="number" min="1" value={addGearQty} onInput={(event) => setAddGearQty(event.currentTarget.value)} /><button type="button" class="btn primary" disabled={!addGear} onClick={() => { if (!addGear) return; setGearRows((current) => [...current, { itemId: addGear, quantity: addGearQty || "1", masterwork: false, enhancementBonus: "", properties: "" }]); setAddGear(""); setAddGearQty("1"); }}>Add</button></div>
      <div class="builder-list">{gearRows.length ? gearRows.map((row, index) => { const record = catalog.items[row.itemId]; const customizable = record?.category === "weapon" || record?.category === "armor" || record?.category === "shield"; return <div class="builder-card" key={`${row.itemId}-${index}`}><div class="builder-fields"><div class="field"><label>Item</label><span class="hint">{record?.name || row.itemId}</span></div><div class="field"><label>Quantity</label><input type="number" min="1" value={row.quantity} onInput={(event) => setGearRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: event.currentTarget.value } : item))} /></div>{customizable && <><label class="field"><span>Masterwork</span><input type="checkbox" checked={row.masterwork} onChange={(event) => setGearRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, masterwork: event.currentTarget.checked } : item))} /></label><div class="field"><label>Enhancement</label><input type="number" min="0" max="5" value={row.enhancementBonus} onInput={(event) => setGearRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, enhancementBonus: event.currentTarget.value } : item))} /></div><div class="field"><label>{record?.category === "weapon" ? "Weapon qualities" : "Properties"}</label><input value={row.properties} placeholder={record?.category === "weapon" ? "flaming, keen" : "Source-backed IDs"} onInput={(event) => setGearRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, properties: event.currentTarget.value } : item))} /><small>{record?.category === "weapon" ? "Comma-separated supported qualities; validation runs on review." : "Comma-separated property IDs; validation runs on review."}</small></div></>}</div><button type="button" class="btn small" onClick={() => setGearRows((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove</button></div>; }) : <div class="empty">No gear. Add catalog items with quantities.</div>}</div>
    </section>
    <div class="field full"><label>Descriptive equipment — one item per line</label><textarea value={descriptiveGear} onInput={(event) => setDescriptiveGear(event.currentTarget.value)} /><small>No automatic effects or pricing, even if a line names a weapon or magic item.</small></div>
  </div><p class="hint">Use an empty spell loadout for noncasters. Gear prices, effects, category budgets, and copper-piece totals come from the NPC catalog only.</p></StepFrame>;
}

function NpcReviewStep({ draft, evaluation, choiceRequirements, automaticSelections, selectionBudgets, step, onSave, onBack }: Props) {
  const current = objectValue(draft.selections.details);
  const [alignment, setAlignment] = useState(String(current.alignment || ""));
  const [religion, setReligion] = useState(String(current.religion || ""));
  const [languages, setLanguages] = useState(Array.isArray(current.languages) ? current.languages.filter((value): value is string => typeof value === "string").join(", ") : "");
  const [detailsText, setDetailsText] = useState(formatJson(current));
  const [error, setError] = useState("");
  const submit = (next: boolean) => { try { setError(""); const parsed = parseJson(detailsText, "details"); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("details must be a JSON object"); const details = parsed as JsonObject; onSave({ details: { ...details, alignment: alignment || undefined, religion: religion || undefined, languages: languages.split(",").map((value) => value.trim()).filter(Boolean) } }, {}, next); } catch (caught) { setError(String(caught)); } };
  const canonical = evaluation.canonical || evaluation.effective;
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid"><Field label="Alignment" value={alignment} onInput={setAlignment} /><Field label="Religion" value={religion} onInput={setReligion} /><Field label="Additional languages (comma-separated)" value={languages} onInput={setLanguages} full /><JsonArea label="Other user-owned details JSON" value={detailsText} onChange={setDetailsText} full /></div>{error && <div class="issue invalid"><p>{error}</p></div>}
    <section class="baseline"><strong>Choice requirements</strong><p class="hint">{choiceRequirements.length} source-defined requirement(s). Automatic racial and class grants remain engine-owned.</p>{choiceRequirements.length ? <ul>{choiceRequirements.slice(0, 12).map((requirement) => <li><code>{requirement.path}</code> — {requirement.label}</li>)}</ul> : <p class="hint">No requirements returned for the current selections.</p>}</section>
    <section class="baseline"><strong>Selection budgets</strong><pre>{JSON.stringify(selectionBudgets, null, 2)}</pre><strong>Automatic selections</strong><pre>{JSON.stringify(automaticSelections, null, 2)}</pre></section>
    {canonical ? <section class="baseline"><strong>Canonical NPC preview</strong><pre>{JSON.stringify(canonical, null, 2)}</pre><details><summary>Derivation trace</summary><pre>{JSON.stringify(evaluation.derivationTrace, null, 2)}</pre></details></section> : <section class="empty">Canonical values appear only after every required source-backed selection is complete. Current status: {evaluation.status}.</section>}
  </StepFrame>;
}

function isClassRow(value: unknown): value is ClassRow {
  return Boolean(value && typeof value === "object" && typeof (value as ClassRow).classId === "string" && typeof (value as ClassRow).levels === "number");
}

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseJson(text: string, label: string): unknown {
  try { return JSON.parse(text); } catch (error) { throw new Error(`${label} must be valid JSON: ${error instanceof Error ? error.message : String(error)}`); }
}

function pickFields(entry: JsonObject, fields: string[]): JsonObject {
  return Object.fromEntries(fields.filter((field) => entry[field] !== undefined).map((field) => [field, entry[field]]));
}

function JsonArea(props: { label: string; value: string; onChange: (value: string) => void; full?: boolean }) {
  return <div class={`field ${props.full ? "full" : ""}`}><label>{props.label}</label><textarea value={props.value} onInput={(event) => props.onChange(event.currentTarget.value)} spellcheck={false} /></div>;
}
