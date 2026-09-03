import { useEffect, useState } from "preact/hooks";
import { ChoiceSection } from "../choice-fields";
import { CatalogSelect, Field, Select, StepFrame } from "../components";
import type { AutomaticSelections, ChoiceRequirement, Draft, Evaluation, JsonObject, NpcCatalog, SelectionBudgets } from "../types";

export const NPC_STEPS = [
  { label: "Concept", desc: "Set the encounter use and the NPC's identity." },
  { label: "Race", desc: "Choose the race and its source-defined choices." },
  { label: "Class progression", desc: "Enter the ordered class levels and class feature choices." },
  { label: "Abilities", desc: "Choose an array method, level increases, and any custom rationale." },
  { label: "Skills and feats", desc: "Use simplified or precise skills and fill source-defined feat slots." },
  { label: "Spells and gear", desc: "Configure Adept or other source-backed spells and the NPC gear budget." },
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
  const prefixes = [["/concept", "/selections/statblockUse"], ["/selections/raceId", "/selections/racialChoices"], ["/selections/classProgression", "/selections/classFeatureChoices"], ["/selections/abilityGeneration", "/selections/levelIncreases"], ["/selections/skillGeneration", "/selections/feats"], ["/selections/spellLoadout", "/selections/gear", "/selections/gearProfile"], ["/selections/details"]];
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
function NpcClassStep({ draft, catalog, step, choiceRequirements, onPreview, onSave, onBack }: Props) {
  const initial = Array.isArray(draft.selections.classProgression) ? draft.selections.classProgression.filter(isClassRow) : [];
  const [rows, setRows] = useState<ClassRow[]>(initial);
  const [choices, setChoices] = useState<JsonObject>(objectValue(draft.selections.classFeatureChoices));
  const classes = Object.values(catalog.classes);
  useEffect(() => onPreview({ classProgression: rows, classFeatureChoices: choices }), [rows, choices]);
  const addClass = () => { const used = new Set(rows.map((row) => row.classId)); const entry = classes.find((candidate) => !used.has(candidate.id)); if (entry) setRows((current) => [...current, { classId: entry.id, levels: 1 }]); };
  return <StepFrame step={step} onBack={onBack} onApply={(next) => onSave({ classProgression: rows, classFeatureChoices: choices }, {}, next)}>
    <div class="add-row"><div><span class="label">Ordered classes</span><p class="hint">The first row is primary. Later rows are multiclass progressions and remain in the entered order.</p></div><button type="button" class="btn primary" disabled={rows.length >= classes.length} onClick={addClass}>Add class</button></div>
    <div class="builder-list">{rows.map((row, index) => <article class="builder-card" key={`${index}-${row.classId}`}><div class="builder-head"><div><strong>{index === 0 ? "Primary class" : `Class ${index + 1}`}</strong><small>{row.classId}</small></div><button type="button" class="btn small" onClick={() => setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}>Remove</button></div><div class="builder-fields"><Select label="Class" value={row.classId} onChange={(value) => setRows((current) => current.map((item, rowIndex) => rowIndex === index ? { ...item, classId: value } : item))}>{classes.filter((entry) => entry.id === row.classId || !rows.some((item, rowIndex) => rowIndex !== index && item.classId === entry.id)).map((entry) => <option value={entry.id}>{entry.name}</option>)}</Select><Field label="Levels" type="number" value={String(row.levels)} onInput={(value) => setRows((current) => current.map((item, rowIndex) => rowIndex === index ? { ...item, levels: Math.max(1, Number(value) || 1) } : item))} /></div></article>)}</div>
    {!rows.length && <div class="empty">Add the primary NPC class.</div>}
    <ChoiceSection title="Class feature choices" description="Only source-defined class choices are accepted." requirements={choiceRequirements} pathPrefix="/selections/classFeatureChoices" values={choices} onChange={(name, value) => setChoices((current) => ({ ...current, [name]: value }))} />
  </StepFrame>;
}

function NpcAbilityStep({ draft, catalog, step, onSave, onBack }: Props) {
  const current = objectValue(draft.selections.abilityGeneration);
  const [method, setMethod] = useState(String(current.method || "assigned"));
  const primaryClass = Array.isArray(draft.selections.classProgression) && draft.selections.classProgression.length > 0 && typeof (draft.selections.classProgression as JsonObject[])[0]?.classId === "string" ? String((draft.selections.classProgression as JsonObject[])[0].classId) : "";
  const [arrayId, setArrayId] = useState(String(current.arrayId || ""));
  const [preset, setPreset] = useState(String(current.preset || current.role || ""));
  const [scores, setScores] = useState(formatJson(current.scores || current.assignments || {}));
  const [rationale, setRationale] = useState(String(current.rationale || ""));
  const [increases, setIncreases] = useState(formatJson(draft.selections.levelIncreases || {}));
  const [error, setError] = useState("");
  const submit = (next: boolean) => {
    try {
      const parsedScores = parseJson(scores, "ability scores");
      const parsedIncreases = parseJson(increases, "level increases");
      setError("");
      onSave({ abilityGeneration: { method, arrayId: arrayId || undefined, preset: preset || undefined, scores: parsedScores, rationale: rationale || undefined }, levelIncreases: parsedIncreases }, {}, next);
    } catch (caught) { setError(String(caught)); }
  };
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    <Select label="Ability generation" value={method} onChange={setMethod}><option value="assigned">Assigned array</option><option value="preset">Source preset</option><option value="melee-preset">Melee preset</option>{primaryClass === "npc-class.druid" ? <option value="divine-preset">Divine preset</option> : null}<option value="ranged-preset">Ranged preset</option><option value="skill-preset">Skill preset</option><option value="arcane-preset">Arcane preset</option><option value="custom">Custom scores</option></Select>
    <CatalogSelect label="NPC ability array" records={catalog.abilityArrays} value={arrayId} onChange={setArrayId} blank="Choose source array…" />
    <Field label="Preset name (when applicable)" value={preset} onInput={setPreset} />
    <Field label="Custom rationale (required for custom)" value={rationale} onInput={setRationale} full />
    <JsonArea label="Assigned or custom scores (JSON object)" value={scores} onChange={setScores} full />
    <JsonArea label="Level increases (JSON object, for example {&quot;4&quot;:&quot;strength&quot;})" value={increases} onChange={setIncreases} full />
  </div>{error && <div class="issue invalid"><p>{error}</p></div>}<p class="hint">Computed scores, modifiers, BAB, saves, and defenses are preview-only. The engine rejects them if placed in the draft.</p></StepFrame>;
}

function NpcSkillsFeatsStep({ draft, catalog, step, onSave, onBack }: Props) {
  const generation = objectValue(draft.selections.skillGeneration);
  const [method, setMethod] = useState(String(generation.method || "simplified"));
  const [skills, setSkills] = useState<string[]>(Array.isArray(generation.skills) ? generation.skills.filter((value): value is string => typeof value === "string") : []);
  const [ranks, setRanks] = useState(formatJson(generation.ranks || {}));
  const [feats, setFeats] = useState(formatJson(draft.selections.feats || []));
  const [addSkill, setAddSkill] = useState("");
  const [error, setError] = useState("");
  const available = Object.values(catalog.skills).filter((skill) => !skills.includes(skill.id)).sort((a, b) => a.name.localeCompare(b.name));
  const submit = (next: boolean) => { try { setError(""); onSave({ skillGeneration: { method, skills, ranks: parseJson(ranks, "skill ranks") }, feats: parseJson(feats, "feats") }, {}, next); } catch (caught) { setError(String(caught)); } };
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    <Select label="Skill method" value={method} onChange={setMethod}><option value="simplified">Simplified skills</option><option value="precise">Precise skill ranks</option></Select>
    <div class="field"><label>Add simplified skill</label><div class="add-row"><select value={addSkill} onChange={(event) => setAddSkill(event.currentTarget.value)}><option value="">Choose a skill…</option>{available.map((skill) => <option value={skill.id}>{skill.name}</option>)}</select><button type="button" class="btn" disabled={!addSkill} onClick={() => { setSkills([...skills, addSkill]); setAddSkill(""); }}>Add</button></div></div>
    <div class="field full"><div class="builder-list">{skills.map((id) => <div class="builder-card"><div class="builder-head"><strong>{catalog.skills[id]?.name || id}</strong><button type="button" class="btn small" onClick={() => setSkills(skills.filter((value) => value !== id))}>Remove</button></div></div>)}</div></div>
    <JsonArea label="Precise skill ranks (JSON object)" value={ranks} onChange={setRanks} full />
    <JsonArea label="Feat selections (JSON array of {slotId, featId})" value={feats} onChange={setFeats} full />
  </div>{error && <div class="issue invalid"><p>{error}</p></div>}<p class="hint">The engine supplies automatic class skills, enforces simplified multiclass limits, validates precise rank budgets, and checks feat prerequisites.</p></StepFrame>;
}

function NpcSpellsGearStep({ draft, catalog, step, onSave, onBack }: Props) {
  const [spellText, setSpellText] = useState(formatJson(draft.selections.spellLoadout || {}));
  const profile = objectValue(draft.selections.gearProfile);
  const [progression, setProgression] = useState(String(profile.experienceProgression || "medium"));
  const [fantasy, setFantasy] = useState(String(profile.fantasyLevel || "normal"));
  const [gearText, setGearText] = useState(formatJson(draft.selections.gear || []));
  const [error, setError] = useState("");
  const submit = (next: boolean) => { try { setError(""); onSave({ spellLoadout: parseJson(spellText, "spell loadout"), gearProfile: { experienceProgression: progression, fantasyLevel: fantasy }, gear: parseJson(gearText, "gear") }, {}, next); } catch (caught) { setError(String(caught)); } };
  const spellCount = Object.keys(catalog.spells).length;
  const itemCount = Object.keys(catalog.items).length;
  return <StepFrame step={step} onBack={onBack} onApply={submit}><div class="grid">
    <JsonArea label={`Spell loadout JSON (${spellCount} catalog entries)`} value={spellText} onChange={setSpellText} full />
    <Select label="Experience progression" value={progression} onChange={setProgression}><option value="slow">Slow</option><option value="medium">Medium</option><option value="fast">Fast</option></Select>
    <Select label="Fantasy level" value={fantasy} onChange={setFantasy}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></Select>
    <JsonArea label={`Gear selections JSON (${itemCount} catalog entries)`} value={gearText} onChange={setGearText} full />
  </div>{error && <div class="issue invalid"><p>{error}</p></div>}<p class="hint">Use an empty spell loadout for noncasters. Gear prices, effects, category budgets, and copper-piece totals come from the NPC catalog only.</p></StepFrame>;
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
