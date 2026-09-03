import { useEffect, useRef, useState } from "preact/hooks";
import { execute, loadCatalog, loadNpcCatalog, newChangeId } from "./api";
import { sourceText } from "./components";
import { ProposalPanel } from "./proposal-panel";
import { STEPS, issuesForStep, stepForPath, stepStatus } from "./steps";
import { ArrayStep, ConceptStep, type EditorProps } from "./steps/basic";
import { PrimaryGraftStep, SizeStep, SpellStep, SubtypeStep, TemplateStep } from "./steps/grafts";
import { OptionsStep } from "./steps/options";
import { DamageStep, SkillsStep } from "./steps/finish";
import { NpcWorkflow } from "./steps/npc";
import type { AutomaticSelections, Catalog, Change, ChoiceRequirement, Draft, EngineResult, Evaluation, FinishedMonster, JsonObject, LibraryEntry, NpcCatalog, Proposal, SelectionBudgets } from "./types";

export function App() {
  const [catalog, setCatalog] = useState<Catalog>();
  const [npcCatalog, setNpcCatalog] = useState<NpcCatalog>();
  const [draft, setDraft] = useState<Draft>();
  const [evaluation, setEvaluation] = useState<Evaluation>();
  const [monster, setMonster] = useState<FinishedMonster>();
  const [proposal, setProposal] = useState<Proposal>();
  const [aiError, setAiError] = useState<string>();
  const [aiRunning, setAiRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [library, setLibrary] = useState<{ drafts: LibraryEntry[]; monsters: LibraryEntry[] }>();
  const [choiceRequirements, setChoiceRequirements] = useState<ChoiceRequirement[]>([]);
  const [automaticSelections, setAutomaticSelections] = useState<AutomaticSelections>({ skills: { master: [], good: [] } });
  const [selectionBudgets, setSelectionBudgets] = useState<SelectionBudgets>({ skills: { master: null, good: null } });
  const choiceRequest = useRef(0);
  const [message, setMessage] = useState<{ text: string; good?: boolean }>();

  useEffect(() => { void boot(); }, []);
  async function boot() {
    try {
      const [simpleCatalog, npcCatalogValue] = await Promise.all([loadCatalog(), loadNpcCatalog()]);
      setCatalog(simpleCatalog);
      setNpcCatalog(npcCatalogValue);
      const saved = localStorage.getItem("monster-builder.draftId");
      if (saved) {
        try { await getDraft(saved); return; } catch { localStorage.removeItem("monster-builder.draftId"); show("Saved draft uses an older catalog version; started a new draft. Previous items remain in the Library."); }
      }
      accept(await execute("draft.create", { draft: {} }));
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
  }
  function accept(result: EngineResult) {
    if (result.draft) {
      setDraft(result.draft);
      localStorage.setItem("monster-builder.draftId", result.draft.draftId);
      void refreshChoiceRequirements({ draftId: result.draft.draftId });
    }
    if (result.evaluation) setEvaluation(result.evaluation);
    if (result.monster) setMonster(result.monster);
    if (result.proposal) setProposal(result.proposal);
  }
  async function refreshChoiceRequirements(payload: JsonObject) {
    const request = ++choiceRequest.current;
    try {
      const result = await execute("draft.choiceRequirements", payload);
      if (request === choiceRequest.current) {
        setChoiceRequirements(result.requirements || []);
        setAutomaticSelections(result.automaticSelections || { skills: { master: [], good: [] } });
        setSelectionBudgets(result.selectionBudgets || { skills: { master: null, good: null } });
      }
    } catch (error) {
      if (request === choiceRequest.current) {
        setChoiceRequirements([]);
        setAutomaticSelections({ skills: { master: [], good: [] } });
        setSelectionBudgets({ skills: { master: null, good: null } });
        show(`Choice requirements unavailable: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }
  function previewChoiceRequirements(selections: JsonObject) {
    if (draft) void refreshChoiceRequirements({ draftId: draft.draftId, selectionOverrides: selections });
  }
  async function getDraft(id: string) {
    const result = await execute("draft.get", { draftId: id });
    if (result.evaluationError) {
      const detail = result.evaluationError;
      const error = new Error(
        detail.code === "catalog.version-unsupported"
          ? "This draft was created with an older catalog version. View its finished monster from the Library, or start a new draft."
          : detail.message,
      );
      (error as Error & { data?: unknown }).data = detail;
      throw error;
    }
    setMonster(undefined); setProposal(undefined); setAiError(undefined);
    accept(result);
    if (result.draft?.monsterId) accept(await execute("monster.get", { monsterId: result.draft.monsterId }));
  }
  function show(text: string, good = false) {
    setMessage({ text, good });
    window.setTimeout(() => setMessage(undefined), 4500);
  }
  if (!catalog || !npcCatalog || !draft || !evaluation) return <main class="app"><div class="panel step-form"><h1>Loading Guided Rail…</h1>{message && <p>{message.text}</p>}</div></main>;

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
        const conceptReady = Boolean(mergedConcept.name && mergedConcept.role && (targetDraft.creationSystem === "npc" || mergedConcept.targetCR !== undefined));
        const blocking = nextEvaluation.issues.some((issue) => (draft.creationSystem === "npc" ? npcStepForPath(issue.path) : stepForPath(issue.path)) === step && issue.severity !== "warning");
        if ((step === 0 && !conceptReady) || blocking) show("Resolve this step before continuing. You can still inspect another step from the rail.");
        else setStep((current) => Math.min(targetDraft.creationSystem === "npc" ? 6 : 9, current + 1));
      }
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  function addChange(changes: Change[], current: JsonObject, field: string, value: unknown, isConcept: boolean) {
    if (JSON.stringify(current[field]) === JSON.stringify(value)) return;
    const unset = value === undefined || value === "";
    changes.push({ changeId: newChangeId(field), type: unset ? (isConcept ? "unset-concept" : "unset-selection") : (isConcept ? "set-concept" : "set-selection"), field, ...(unset ? {} : { value }) });
  }
  async function deleteEntry(entry: LibraryEntry) {
    if (entry.kind === "monster" && !window.confirm(`Delete finished monster "${entry.name || "Untitled"}"? This permanently removes the exported statblock and cannot be undone.`)) return;
    if (entry.kind === "draft" && entry.status !== "active" && !window.confirm(`Delete ${entry.status} draft "${entry.name || "Untitled monster"}"? This permanently removes it and cannot be undone.`)) return;
    try {
      setBusy(true);
      if (entry.kind === "draft") await execute("draft.delete", { draftId: entry.id });
      else await execute("monster.delete", { monsterId: entry.id });
      const result = await execute("library.search", { includeArchived: true });
      setLibrary({ drafts: result.drafts || [], monsters: result.monsters || [] });
      show(`${entry.name || "Entry"} deleted.`, true);
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function createDraft() {
    if (!window.confirm("Create a new Simple Monster draft? The current draft remains persisted by its ID.")) return;
    accept(await execute("draft.create", { draft: {} })); setMonster(undefined); setProposal(undefined); setAiError(undefined); setStep(0);
  }
  async function createNpcDraft() {
    if (!window.confirm("Create a new class-based NPC draft? The current draft remains persisted by its ID.")) return;
    accept(await execute("draft.create", { draft: { creationSystem: "npc" } })); setMonster(undefined); setProposal(undefined); setAiError(undefined); setStep(0);
  }
  async function resume() {
    try {
      const result = await execute("library.search", { includeArchived: true });
      setLibrary({ drafts: result.drafts || [], monsters: result.monsters || [] });
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
  }
  async function openSaved(entry: LibraryEntry) {
    try {
      setBusy(true);
      const draftId = entry.kind === "draft" ? entry.id : entry.sourceDraftId;
      if (!draftId) throw new Error("Finished monster has no source draft.");
      try {
        await getDraft(draftId);
      } catch (error) {
        const code = (error as Error & { data?: { code?: string } }).data?.code;
        if (entry.kind !== "monster" || code !== "catalog.version-unsupported") throw error;
        const duplicate = await execute("monster.duplicate", { monsterId: entry.id });
        accept(duplicate);
        if (duplicate.draft) localStorage.setItem("monster-builder.draftId", duplicate.draft.draftId);
        await accept(await execute("monster.get", { monsterId: entry.id }));
        show(`"${entry.name || "Finished monster"}" was created with an older catalog; opened a fresh duplicate for editing. The original finished monster stays attached for export.`, true);
      }
      setLibrary(undefined); setStep(0); show(`${entry.name || "Saved monster"} loaded.`, true);
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function generateProposal(concept: string) {
    try {
      setBusy(true); setAiRunning(true); setAiError(undefined);
      accept(await execute("proposal.generate", { draftId: draft!.draftId, concept }));
      show("Immutable Pi proposal created. Review and confirm selected changes.", true);
    } catch (error) {
      const detail = error as Error & { data?: { code?: string } };
      const text = `${detail.data?.code ? `${detail.data.code}: ` : ""}${error instanceof Error ? error.message : String(error)}`;
      setAiError(text); show(text);
    }
    finally { setBusy(false); setAiRunning(false); }
  }
  async function acceptProposal(changeIds: string[]) {
    if (!proposal) return;
    try {
      setBusy(true);
      const result = await execute("proposal.accept", { proposalId: proposal.proposalId, changeIds, confirmation: { actor: "user", confirmed: true } });
      accept(result); setProposal(undefined); show("Selected proposal changes applied and revalidated.", true);
    } catch (error) { show(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function finalize() {
    if (evaluation!.status !== "valid") { show("Finalization requires a complete valid evaluation."); return; }
    try { accept(await execute("monster.finalize", guard())); show("Immutable FinishedMonster created.", true); } catch (error) { show(error instanceof Error ? error.message : String(error)); }
  }
  async function exportMonster(format: string, profile: string) {
    if (!monster) return;
    const result = await execute("monster.export", { monsterId: monster.monsterId, format, profile });
    const text = typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2);
    const url = URL.createObjectURL(new Blob([text], { type: format === "html" ? "text/html" : format === "json" ? "application/json" : "text/markdown" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${String(draft!.concept.name || "monster").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.${format === "markdown" ? "md" : format}`; anchor.click(); URL.revokeObjectURL(url);
  }

  const editorProps: EditorProps = { draft, catalog, evaluation, choiceRequirements, automaticSelections, selectionBudgets, onPreview: previewChoiceRequirements, onSave: save, onBack: () => setStep((current) => Math.max(0, current - 1)) };
  const side = <Side draft={draft} evaluation={evaluation} monster={monster} proposal={proposal} busy={busy} aiRunning={aiRunning} aiError={aiError} setStep={setStep} issueStep={draft.creationSystem === "npc" ? npcStepForPath : undefined} onGenerate={generateProposal} onAccept={acceptProposal} onClearProposal={() => setProposal(undefined)} />;
  if (draft.creationSystem === "npc") {
    return <><Header draft={draft} monster={monster} busy={busy} creationSystem="npc" onNew={createDraft} onNewNpc={createNpcDraft} onResume={resume} onFinalize={finalize} onExport={exportMonster} />
      <main class="app"><div class="summary"><span class={`pill ${evaluation.status}`}>NPC: {evaluation.status}</span><span class="pill">Revision {draft.revision}</span><span class="pill">{draft.status}</span><span class="pill mono">{draft.draftId}</span>{busy && <span class="pill incomplete">Working…</span>}</div>
        <div class="layout npc-layout"><NpcWorkflow draft={draft} catalog={npcCatalog} evaluation={evaluation} step={step} setStep={setStep} choiceRequirements={choiceRequirements} automaticSelections={automaticSelections} selectionBudgets={selectionBudgets} onPreview={previewChoiceRequirements} onSave={save} onBack={() => setStep((current) => Math.max(0, current - 1))} />{side}</div>
      </main>{library && <LibraryModal library={library} currentDraftId={draft.draftId} onClose={() => setLibrary(undefined)} onSelect={openSaved} onDelete={deleteEntry} />}{message && <div class={`toast ${message.good ? "good" : ""}`}>{message.text}</div>}</>;
  }
  const editors = [<ConceptStep {...editorProps} />, <ArrayStep {...editorProps} />, <PrimaryGraftStep {...editorProps} />, <SubtypeStep {...editorProps} />, <TemplateStep {...editorProps} />, <SizeStep {...editorProps} />, <SpellStep {...editorProps} />, <OptionsStep {...editorProps} />, <SkillsStep {...editorProps} />, <DamageStep {...editorProps} />];
  return <><Header draft={draft} monster={monster} busy={busy} creationSystem="simple-monster" onNew={createDraft} onNewNpc={createNpcDraft} onResume={resume} onFinalize={finalize} onExport={exportMonster} />
    <main class="app"><div class="summary"><span class={`pill ${evaluation.status}`}>Strict: {evaluation.status}</span><span class="pill">Revision {draft.revision}</span><span class="pill">{draft.status}</span><span class="pill mono">{draft.draftId}</span>{busy && <span class="pill incomplete">Working…</span>}</div>
      <div class="layout"><Rail draft={draft} evaluation={evaluation} step={step} setStep={setStep} /><section class="panel workspace"><div class="step-head"><div class="kicker">{step === 0 ? "Before you begin" : `Step ${step}`}</div><h2>{STEPS[step].label}</h2><p>{STEPS[step].desc}</p></div><div key={`${draft.draftId}-${step}-${draft.revision}`}>{editors[step]}</div></section>{side}</div>
    </main>{library && <LibraryModal library={library} currentDraftId={draft.draftId} onClose={() => setLibrary(undefined)} onSelect={openSaved} onDelete={deleteEntry} />}{message && <div class={`toast ${message.good ? "good" : ""}`}>{message.text}</div>}</>;
}

const savedAtFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function savedLabel(value: string | null | undefined) {
  if (!value) return "Saved time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Saved time unavailable" : `Saved ${savedAtFormatter.format(date)}`;
}

function LibraryModal(props: { library: { drafts: LibraryEntry[]; monsters: LibraryEntry[] }; currentDraftId: string; onClose: () => void; onSelect: (entry: LibraryEntry) => void; onDelete: (entry: LibraryEntry) => void }) {
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(true);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") props.onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  const matches = (entry: LibraryEntry) => (showInactive || entry.status === "active") && (!query || `${entry.name} ${entry.role} ${entry.id}`.toLowerCase().includes(query.toLowerCase()));
  const groups: Array<[string, LibraryEntry[]]> = [["Drafts", props.library.drafts.filter(matches)], ["Finished monsters", props.library.monsters.filter(matches)]];
  return <div class="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) props.onClose(); }}>
    <section class="library-modal panel" role="dialog" aria-modal="true" aria-labelledby="library-title">
      <div class="modal-head"><div><div class="kicker">Local workspace</div><h2 id="library-title">Open saved monster</h2></div><button type="button" class="btn" onClick={props.onClose}>Close</button></div>
      <div class="field"><label>Search</label><input autofocus value={query} placeholder="Name, role, or ID" onInput={(event) => setQuery(event.currentTarget.value)} /></div>
      <label class="library-toggle"><input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.currentTarget.checked)} /> Show finalized &amp; archived</label>
      <div class="library-groups">{groups.map(([label, entries]) => <section><h3>{label} <span>{entries.length}</span></h3><div class="library-list">{entries.map((entry) => {
        const current = entry.kind === "draft" ? entry.id === props.currentDraftId : entry.sourceDraftId === props.currentDraftId;
        const openable = entry.status === "active";
        return <div key={entry.id} role={openable ? "button" : undefined} tabIndex={openable ? 0 : undefined} class={`library-row ${current ? "current" : ""} ${entry.status !== "active" ? "inactive" : ""}`} onClick={() => { if (openable) props.onSelect(entry); }} onKeyDown={(event) => { if (openable && event.key === "Enter") props.onSelect(entry); }}>
          <span><strong>{entry.name || "Untitled monster"}</strong><small>{entry.creationSystem === "npc" ? `NPC level ${String(entry.level ?? "—")}` : "Simple Monster"} · CR {String(entry.cr ?? "—")}{entry.role ? ` · ${entry.role}` : ""}</small><small>{savedLabel(entry.savedAt)}</small><code>{entry.id}</code></span>
          <span class="library-meta"><span class="pill">Revision {entry.revision ?? "—"}</span>{entry.kind === "monster" && <span class="pill">Finished</span>}{entry.status !== "active" && <span class="pill">{entry.status === "finalized" ? "Finalized" : "Archived"}</span>}{current && <span class="pill valid">Current</span>}<button type="button" class="btn small danger" title={entry.kind === "monster" ? "Delete finished monster (asks for confirmation)" : "Delete draft"} onClick={(event) => { event.stopPropagation(); props.onDelete(entry); }}>Delete</button></span>
        </div>;
      })}{!entries.length && <div class="empty">No matching {label.toLowerCase()}.</div>}</div></section>)}</div>
    </section>
  </div>;
}

function Header(props: { draft: Draft; monster?: FinishedMonster; busy: boolean; creationSystem: "simple-monster" | "npc"; onNew: () => void; onNewNpc: () => void; onResume: () => void; onFinalize: () => void; onExport: (format: string, profile: string) => void }) {
  const [format, setFormat] = useState("markdown"); const [profile, setProfile] = useState("sheet");
  const npc = props.creationSystem === "npc";
  return <header class="top"><div class="top-inner"><div class="brand"><small>Pathfinder Unchained · {npc ? "Class-based NPC Creation" : "Simple Monster Creation"}</small><h1>{String(props.draft.concept.name || (npc ? "Guided-Rail NPC Builder" : "Guided-Rail Monster Builder"))}</h1></div><div class="actions"><button class="btn dark" onClick={props.onNew}>New Simple Monster</button><button class="btn dark" onClick={props.onNewNpc}>New NPC</button><button class="btn dark" onClick={props.onResume}>Open saved</button><select class="btn" value={format} onChange={(event) => setFormat(event.currentTarget.value)}><option value="markdown">Markdown</option><option value="html">HTML / Print</option><option value="json">JSON</option></select><select class="btn" value={profile} onChange={(event) => setProfile(event.currentTarget.value)}><option value="sheet">Sheet</option><option value="audit">Sheet + audit</option></select><button class="btn" disabled={!props.monster} onClick={() => props.onExport(format, profile)}>Export</button><button class="btn primary" disabled={props.busy || props.draft.status !== "active"} onClick={props.onFinalize}>Finalize</button></div></div></header>;
}

function Rail(props: { draft: Draft; evaluation: Evaluation; step: number; setStep: (step: number) => void }) {
  return <aside class="panel rail"><h2>Creation path</h2><nav aria-label="Creation steps">{STEPS.map((item, index) => { const status = stepStatus(props.draft, props.evaluation, index), count = issuesForStep(props.evaluation, index).length; return <button class={`${status} ${index === props.step ? "current" : ""}`} onClick={() => props.setStep(index)}><span class="n">{item.n}</span><span><strong>{item.label}</strong><small>{count ? `${count} issue(s)` : item.short}</small></span><span class="dot" /></button>; })}</nav><p class="rail-note">Every applied change creates a revision and is immediately evaluated by the deterministic engine. You may inspect any step at any time.</p></aside>;
}

function npcStepForPath(path: string): number {
  if (path.startsWith("/concept") || path.startsWith("/selections/statblockUse")) return 0;
  if (path.startsWith("/selections/raceId") || path.startsWith("/selections/racialChoices")) return 1;
  if (path.startsWith("/selections/classProgression") || path.startsWith("/selections/classFeatureChoices")) return 2;
  if (path.startsWith("/selections/abilityGeneration") || path.startsWith("/selections/levelIncreases")) return 3;
  if (path.startsWith("/selections/skillGeneration") || path.startsWith("/selections/feats")) return 4;
  if (path.startsWith("/selections/spellLoadout") || path.startsWith("/selections/gear" ) || path.startsWith("/selections/gearProfile")) return 5;
  return 6;
}

function npcAc(defenses: Record<string, unknown>): unknown {
  const breakdown = defenses.acBreakdown;
  if (defenses.ac == null || !breakdown || typeof breakdown !== "object") return defenses.ac;
  const labels: Record<string, string> = { armor: "armor", shield: "shield", dexterity: "Dex", size: "size" };
  const parts = Object.entries(breakdown as Record<string, number>).map(([source, bonus]) => `${bonus >= 0 ? "+" : ""}${bonus} ${labels[source] || source}`);
  return parts.length ? `${defenses.ac} (${parts.join(", ")})` : defenses.ac;
}

function Side(props: { draft: Draft; evaluation: Evaluation; monster?: FinishedMonster; proposal?: Proposal; busy: boolean; aiRunning: boolean; aiError?: string; setStep: (step: number) => void; issueStep?: (path: string) => number; onGenerate: (concept: string) => void; onAccept: (changeIds: string[]) => void; onClearProposal: () => void }) {
  const result = props.evaluation.effective as { level?: unknown; bab?: unknown; defenses?: Record<string, unknown>; abilityScores?: unknown; feats?: unknown; gear?: unknown; abilityDC?: unknown; spellDC?: unknown; spells?: Array<Record<string, unknown>>; cmb?: unknown } | null | undefined;
  const defenses = result?.defenses || {};
  const npcStats: Array<[string, unknown]> = [["Level", result?.level], ["BAB", result?.bab], ["AC", npcAc(defenses)], ["HP", defenses.hp], ["CMD", defenses.cmd], ["Fort", defenses.fortitude], ["Ref", defenses.reflex], ["Will", defenses.will], ["CMB", result?.cmb]];
  const simpleStats: Array<[string, unknown]> = [["AC", defenses.ac], ["HP", defenses.hp], ["CMD", defenses.cmd], ["Fort", defenses.fortitude], ["Ref", defenses.reflex], ["Will", defenses.will], ["Ability DC", result?.abilityDC], ["Spell DC", result?.spellDC], ["CMB", result?.cmb]];
  const stats = props.draft.creationSystem === "npc" ? npcStats : simpleStats;
  return <aside class="side"><ProposalPanel draft={props.draft} proposal={props.proposal} busy={props.busy} running={props.aiRunning} error={props.aiError} onGenerate={props.onGenerate} onAccept={props.onAccept} onClear={props.onClearProposal} /><section class="panel"><h3>Live validation</h3><div class="validation-summary">Engine status: <strong>{props.evaluation.status}</strong>. {props.evaluation.issues.length ? `${props.evaluation.issues.length} finding(s) remain.` : "No validation findings."}</div><div class="issues">{props.evaluation.issues.map((issue) => <article class={`issue ${issue.kind === "catalog-data" ? "invalid" : ""}`}><button onClick={() => props.setStep((props.issueStep || stepForPath)(issue.path))}>{issue.code} · {issue.path}</button><p>{issue.message}</p><small>{sourceText(issue.sourceRefs?.[0])}</small></article>)}</div></section>
    <section class="panel"><h3>Monster preview</h3>{result ? <><div class="stats">{stats.map(([label, value]) => <div class="stat"><span>{label}</span><b>{String(value ?? "—")}</b></div>)}</div><div class="trace"><h3>Derivation trace</h3>{props.evaluation.derivationTrace.map((item) => <details><summary>{item.rule} · {item.path}</summary><pre>{JSON.stringify(item.value, null, 2)}</pre><small>{sourceText(item.sourceRefs?.[0])}</small></details>)}</div></> : <div class="empty">Canonical and effective results appear only after a complete valid evaluation.</div>}</section>
    <section class="panel"><h3>Draft state</h3><p class="hint">Authoritative writes use <code>execute</code>. The JSON below is inspectable only.</p><details><summary class="mono">Revision {props.draft.revision} · {props.draft.fingerprint.slice(0, 12)}…</summary><pre class="draft-json">{JSON.stringify(props.draft, null, 2)}</pre></details>{props.monster && <p class="hint"><strong>Finished:</strong> <code>{props.monster.monsterId}</code></p>}</section></aside>;
}
