import { useEffect, useState } from "preact/hooks";
import { execute, loadCatalog, newChangeId } from "./api";
import { sourceText } from "./components";
import { STEPS, issuesForStep, stepForPath, stepStatus } from "./steps";
import { ArrayStep, ConceptStep, type EditorProps } from "./steps/basic";
import { PrimaryGraftStep, SizeStep, SpellStep, SubtypeStep, TemplateStep } from "./steps/grafts";
import { OptionsStep } from "./steps/options";
import { DamageStep, SkillsStep } from "./steps/finish";
import type { Catalog, Change, Draft, EngineResult, Evaluation, FinishedMonster, JsonObject } from "./types";

export function App() {
  const [catalog, setCatalog] = useState<Catalog>();
  const [draft, setDraft] = useState<Draft>();
  const [evaluation, setEvaluation] = useState<Evaluation>();
  const [monster, setMonster] = useState<FinishedMonster>();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; good?: boolean }>();

  useEffect(() => { void boot(); }, []);
  async function boot() {
    try {
      setCatalog(await loadCatalog());
      const saved = localStorage.getItem("monster-builder.draftId");
      if (saved) {
        try { await getDraft(saved); return; } catch { localStorage.removeItem("monster-builder.draftId"); }
      }
      accept(await execute("draft.create", { draft: {} }));
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
  }
  function accept(result: EngineResult) {
    if (result.draft) { setDraft(result.draft); localStorage.setItem("monster-builder.draftId", result.draft.draftId); }
    if (result.evaluation) setEvaluation(result.evaluation);
    if (result.monster) setMonster(result.monster);
  }
  async function getDraft(id: string) {
    const result = await execute("draft.get", { draftId: id });
    accept(result);
    if (result.draft?.monsterId) accept(await execute("monster.get", { monsterId: result.draft.monsterId }));
  }
  function show(text: string, good = false) {
    setMessage({ text, good });
    window.setTimeout(() => setMessage(undefined), 4500);
  }
  if (!catalog || !draft || !evaluation) return <main class="app"><div class="panel step-form"><h1>Loading Guided Rail…</h1>{message && <p>{message.text}</p>}</div></main>;

  const guard = (target: Draft = draft) => ({ draftId: target.draftId, baseRevision: target.revision, baseFingerprint: target.fingerprint });
  async function save(selections: JsonObject, concept: JsonObject, andContinue: boolean) {
    if (busy || !draft || !evaluation) return;
    const changes: Change[] = [];
    for (const [field, value] of Object.entries(selections)) addChange(changes, draft.selections, field, value, false);
    for (const [field, value] of Object.entries(concept)) addChange(changes, draft.concept, field, value, true);
    let nextEvaluation = evaluation;
    try {
      setBusy(true);
      let targetDraft = draft;
      let copied = false;
      if (changes.length && targetDraft.status !== "active") {
        const duplicate = await execute("draft.duplicate", guard(targetDraft));
        if (!duplicate.draft) throw new Error("The editable draft copy was not returned.");
        targetDraft = duplicate.draft;
        nextEvaluation = duplicate.evaluation || evaluation;
        accept(duplicate);
        setMonster(undefined);
        copied = true;
      }
      if (changes.length) {
        const result = await execute("draft.applyChanges", { ...guard(targetDraft), changes });
        accept(result);
        nextEvaluation = result.evaluation || nextEvaluation;
        show(`${copied ? "Editable copy created. " : ""}Revision ${result.draft?.revision} saved and evaluated.`, true);
      } else show("No changes to apply.", true);
      if (andContinue) {
        const mergedConcept = { ...draft.concept, ...concept };
        const conceptReady = Boolean(mergedConcept.name && mergedConcept.role && mergedConcept.targetCR !== undefined);
        const blocking = issuesForStep(nextEvaluation, step).some((issue) => issue.severity !== "warning");
        if ((step === 0 && !conceptReady) || blocking) show("Resolve this step before continuing. You can still inspect another step from the rail.");
        else setStep((current) => Math.min(9, current + 1));
      }
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  function addChange(changes: Change[], current: JsonObject, field: string, value: unknown, isConcept: boolean) {
    if (JSON.stringify(current[field]) === JSON.stringify(value)) return;
    const unset = value === undefined || value === "";
    changes.push({ changeId: newChangeId(field), type: unset ? (isConcept ? "unset-concept" : "unset-selection") : (isConcept ? "set-concept" : "set-selection"), field, ...(unset ? {} : { value }) });
  }
  async function createDraft() {
    if (!window.confirm("Create a new draft? The current draft remains persisted by its ID.")) return;
    accept(await execute("draft.create", { draft: {} })); setMonster(undefined); setStep(0);
  }
  async function resume() { const id = window.prompt("Draft ID", draft!.draftId); if (id) try { await getDraft(id); show("Draft loaded.", true); } catch (error) { show(error instanceof Error ? error.message : String(error)); } }
  async function finalize() {
    if (evaluation!.status !== "valid") { show("Finalization requires a complete valid Strict evaluation."); return; }
    try { accept(await execute("monster.finalize", guard())); show("Immutable FinishedMonster created.", true); } catch (error) { show(error instanceof Error ? error.message : String(error)); }
  }
  async function exportMonster(format: string, profile: string) {
    if (!monster) return;
    const result = await execute("monster.export", { monsterId: monster.monsterId, format, profile });
    const text = typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2);
    const url = URL.createObjectURL(new Blob([text], { type: format === "html" ? "text/html" : format === "json" ? "application/json" : "text/markdown" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${String(draft!.concept.name || "monster").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.${format === "markdown" ? "md" : format}`; anchor.click(); URL.revokeObjectURL(url);
  }

  const editorProps: EditorProps = { draft, catalog, evaluation, onSave: save, onBack: () => setStep((current) => Math.max(0, current - 1)) };
  const editors = [<ConceptStep {...editorProps} />, <ArrayStep {...editorProps} />, <PrimaryGraftStep {...editorProps} />, <SubtypeStep {...editorProps} />, <TemplateStep {...editorProps} />, <SizeStep {...editorProps} />, <SpellStep {...editorProps} />, <OptionsStep {...editorProps} />, <SkillsStep {...editorProps} />, <DamageStep {...editorProps} />];
  return <><Header draft={draft} monster={monster} busy={busy} onNew={createDraft} onResume={resume} onFinalize={finalize} onExport={exportMonster} />
    <main class="app"><div class="summary"><span class={`pill ${evaluation.status}`}>Strict: {evaluation.status}</span><span class="pill">Revision {draft.revision}</span><span class="pill">{draft.status}</span><span class="pill mono">{draft.draftId}</span>{busy && <span class="pill incomplete">Saving…</span>}</div>
      <div class="layout"><Rail draft={draft} evaluation={evaluation} step={step} setStep={setStep} /><section class="panel workspace"><div class="step-head"><div class="kicker">{step === 0 ? "Before you begin" : `Step ${step}`}</div><h2>{STEPS[step].label}</h2><p>{STEPS[step].desc}</p></div><div key={`${draft.draftId}-${step}-${draft.revision}`}>{editors[step]}</div></section><Side draft={draft} evaluation={evaluation} monster={monster} setStep={setStep} /></div>
    </main>{message && <div class={`toast ${message.good ? "good" : ""}`}>{message.text}</div>}</>;
}

function Header(props: { draft: Draft; monster?: FinishedMonster; busy: boolean; onNew: () => void; onResume: () => void; onFinalize: () => void; onExport: (format: string, profile: string) => void }) {
  const [format, setFormat] = useState("markdown"); const [profile, setProfile] = useState("sheet");
  return <header class="top"><div class="top-inner"><div class="brand"><small>Pathfinder Unchained · Simple Monster Creation</small><h1>{String(props.draft.concept.name || "Guided-Rail Monster Builder")}</h1></div><div class="actions"><button class="btn dark" onClick={props.onNew}>New draft</button><button class="btn dark" onClick={props.onResume}>Resume by ID</button><select class="btn" value={format} onChange={(event) => setFormat(event.currentTarget.value)}><option value="markdown">Markdown</option><option value="html">HTML / Print</option><option value="json">JSON</option></select><select class="btn" value={profile} onChange={(event) => setProfile(event.currentTarget.value)}><option value="sheet">Sheet</option><option value="audit">Sheet + audit</option></select><button class="btn" disabled={!props.monster} onClick={() => props.onExport(format, profile)}>Export</button><button class="btn primary" disabled={props.busy || props.draft.status !== "active"} onClick={props.onFinalize}>Finalize</button></div></div></header>;
}

function Rail(props: { draft: Draft; evaluation: Evaluation; step: number; setStep: (step: number) => void }) {
  return <aside class="panel rail"><h2>Creation path</h2><nav aria-label="Creation steps">{STEPS.map((item, index) => { const status = stepStatus(props.draft, props.evaluation, index), count = issuesForStep(props.evaluation, index).length; return <button class={`${status} ${index === props.step ? "current" : ""}`} onClick={() => props.setStep(index)}><span class="n">{item.n}</span><span><strong>{item.label}</strong><small>{count ? `${count} issue(s)` : item.short}</small></span><span class="dot" /></button>; })}</nav><p class="rail-note">Every applied change creates a revision and is immediately evaluated by the deterministic engine. You may inspect any step at any time.</p></aside>;
}

function Side(props: { draft: Draft; evaluation: Evaluation; monster?: FinishedMonster; setStep: (step: number) => void }) {
  const result = props.evaluation.effective as { defenses?: Record<string, unknown>; abilityDC?: unknown; spellDC?: unknown; cmb?: unknown } | null | undefined;
  const defenses = result?.defenses || {};
  const stats: Array<[string, unknown]> = [["AC", defenses.ac], ["HP", defenses.hp], ["CMD", defenses.cmd], ["Fort", defenses.fortitude], ["Ref", defenses.reflex], ["Will", defenses.will], ["Ability DC", result?.abilityDC], ["Spell DC", result?.spellDC], ["CMB", result?.cmb]];
  return <aside class="side"><section class="panel"><h3>Live validation</h3><div class="validation-summary">Engine status: <strong>{props.evaluation.status}</strong>. {props.evaluation.issues.length ? `${props.evaluation.issues.length} finding(s) remain.` : "No validation findings."}</div><div class="issues">{props.evaluation.issues.map((issue) => <article class={`issue ${issue.kind === "catalog-data" ? "invalid" : ""}`}><button onClick={() => props.setStep(stepForPath(issue.path))}>{issue.code} · {issue.path}</button><p>{issue.message}</p><small>{sourceText(issue.sourceRefs?.[0])}</small></article>)}</div></section>
    <section class="panel"><h3>Monster preview</h3>{result ? <><div class="stats">{stats.map(([label, value]) => <div class="stat"><span>{label}</span><b>{String(value ?? "—")}</b></div>)}</div><div class="trace"><h3>Derivation trace</h3>{props.evaluation.derivationTrace.map((item) => <details><summary>{item.rule} · {item.path}</summary><pre>{JSON.stringify(item.value, null, 2)}</pre><small>{sourceText(item.sourceRefs?.[0])}</small></details>)}</div></> : <div class="empty">Canonical and effective results appear only after a complete valid Strict evaluation.</div>}</section>
    <section class="panel"><h3>Draft state</h3><p class="hint">Authoritative writes use <code>execute</code>. The JSON below is inspectable only.</p><details><summary class="mono">Revision {props.draft.revision} · {props.draft.fingerprint.slice(0, 12)}…</summary><pre class="draft-json">{JSON.stringify(props.draft, null, 2)}</pre></details>{props.monster && <p class="hint"><strong>Finished:</strong> <code>{props.monster.monsterId}</code></p>}</section></aside>;
}
