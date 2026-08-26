import { useEffect, useState } from "preact/hooks";
import { sourceText } from "./components";
import type { Draft, Proposal } from "./types";

export function ProposalPanel(props: {
  draft: Draft;
  proposal?: Proposal;
  busy: boolean;
  running: boolean;
  error?: string;
  onGenerate: (concept: string) => void;
  onAccept: (changeIds: string[]) => void;
  onClear: () => void;
}) {
  const [concept, setConcept] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    setConcept(String(props.draft.concept.description || props.draft.concept.name || ""));
  }, [props.draft.draftId]);
  useEffect(() => setSelected(props.proposal?.changes.map((change) => change.changeId) || []), [props.proposal?.proposalId]);

  const proposal = props.proposal;
  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  return <section class="panel proposal-panel"><h3>AI proposal <span class="pill">Optional</span></h3>
    {!proposal ? <><p class="hint">Pi can suggest source-valid changes. It cannot edit the Draft until you confirm them.</p>
      <div class="field"><label for="proposal-concept">Monster concept</label><textarea id="proposal-concept" value={concept} onInput={(event) => setConcept(event.currentTarget.value)} placeholder="Goblin level 4 druid, level 1 rogue…" /></div>
      {props.running && <div class="proposal-notes" role="status">Generating with Pi… Each of up to three validation attempts can take about a minute.</div>}
      {props.error && <div class="proposal-notes warning" role="alert"><strong>AI request failed:</strong> {props.error}</div>}
      <button type="button" class="btn primary" disabled={props.busy || props.draft.status !== "active" || !concept.trim()} onClick={() => props.onGenerate(concept)}>{props.running ? "Generating…" : "Generate proposal"}</button>
    </> : <><p>{proposal.rationale}</p><p class="hint mono">Base revision {proposal.baseRevision} · {proposal.baseFingerprint.slice(0, 12)}…{proposal.model ? ` · ${proposal.model}` : ""}</p>
      {proposal.baseFingerprint !== props.draft.fingerprint && <div class="proposal-notes warning"><strong>Stale proposal:</strong> the Draft changed after generation. Generate a new proposal before accepting.</div>}
      {proposal.assumptions.length > 0 && <div class="proposal-notes"><strong>Assumptions</strong><ul>{proposal.assumptions.map((item) => <li>{item}</li>)}</ul></div>}
      <div class="proposal-changes">{proposal.changes.map((change) => <label class="proposal-change">
        <input type="checkbox" checked={selected.includes(change.changeId)} onChange={() => toggle(change.changeId)} />
        <span><strong>{change.type}: {change.field}</strong>{"value" in change && <code>{JSON.stringify(change.value)}</code>}{change.rationale && <small>{change.rationale}</small>}{change.sourceRefs?.[0] && <small>{sourceText(change.sourceRefs[0])}</small>}</span>
      </label>)}{!proposal.changes.length && <div class="empty">This proposal intentionally leaves the Draft unchanged.</div>}</div>
      {proposal.nonCanonicalSuggestions.length > 0 && <div class="proposal-notes warning"><strong>Non-canonical suggestions</strong><ul>{proposal.nonCanonicalSuggestions.map((item) => <li>{item}</li>)}</ul></div>}
      <div class="proposal-actions"><button type="button" class="btn" onClick={props.onClear}>Dismiss</button><button type="button" class="btn primary" disabled={props.busy || proposal.baseFingerprint !== props.draft.fingerprint || !selected.length} onClick={() => props.onAccept(selected)}>Accept selected</button></div>
    </>}
  </section>;
}
