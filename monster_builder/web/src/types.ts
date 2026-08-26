export type Dict<T> = Record<string, T>;
export type JsonObject = Record<string, unknown>;

export interface SourceRef {
  file?: string;
  sourceId?: string;
  section?: string;
  txtLines?: number[];
  printedPages?: number[];
  entry?: string;
}

export interface CatalogEntry {
  id: string;
  name: string;
  sourceRef?: SourceRef;
  ruleText?: string;
  [key: string]: unknown;
}

export interface ParameterSpec {
  type: "enum" | "enum-array" | "string" | "string-array" | "integer" | "selected-attack" | "selected-attacks" | "selected-speed";
  values?: string[];
  catalogKind?: string;
  optional?: boolean;
  internal?: boolean;
  minCount?: number;
  maxCount?: number;
  count?: number;
  sourceDefaultCount?: number;
}

export interface ChoiceValue {
  value: string;
  label: string;
  sourceRefs?: SourceRef[];
}

export interface AutomaticSelections {
  skills: { master: ChoiceValue[]; good: ChoiceValue[] };
}

export interface SelectionBudgets {
  skills: { master: number | null; good: number | null };
}

export interface ChoiceRequirement {
  path: string;
  label: string;
  type: "enum" | "enum-array" | "string" | "string-array" | "integer";
  required: boolean;
  values?: ChoiceValue[];
  minCount?: number;
  maxCount?: number;
  sourceRefs?: SourceRef[];
}

export interface OptionDefinition extends CatalogEntry {
  category: string;
  parameters?: Dict<ParameterSpec>;
}

export interface NaturalAttackDefinition extends CatalogEntry {
  classification: string;
  damageType: string;
}

export interface Catalog {
  arrays: Dict<CatalogEntry>;
  grafts: {
    creatureTypes: Dict<CatalogEntry>;
    classGrafts: Dict<CatalogEntry>;
    subtypes: Dict<CatalogEntry>;
    templates: Dict<CatalogEntry>;
    sizes: Dict<CatalogEntry>;
  };
  options: Dict<OptionDefinition>;
  skills: Dict<CatalogEntry>;
  naturalAttacksBySize: Dict<NaturalAttackDefinition>;
  spellLists: Dict<CatalogEntry>;
  spells: Dict<CatalogEntry>;
}

export interface SelectedOption {
  optionId: string;
  parameters?: JsonObject;
}

export interface SelectedAttack {
  name: string;
  kind?: string;
  attackProfile: string;
  naturalAttackId?: string;
  profileEntry?: number;
  damageDie?: string;
}

export interface Draft {
  draftId: string;
  revision: number;
  fingerprint: string;
  status: string;
  monsterId?: string;
  concept: JsonObject;
  selections: JsonObject;
}

export interface Issue {
  code: string;
  path: string;
  message: string;
  kind: string;
  severity: string;
  sourceRefs?: SourceRef[];
}

export interface Evaluation {
  status: "incomplete" | "invalid" | "valid";
  issues: Issue[];
  effective?: JsonObject | null;
  derivationTrace: Array<{ path: string; rule: string; value: unknown; sourceRefs?: SourceRef[] }>;
}

export interface FinishedMonster {
  monsterId: string;
}

export interface ProposalChange extends Change {
  rationale?: string;
  sourceRefs?: SourceRef[];
}

export interface Proposal {
  proposalId: string;
  draftId: string;
  baseRevision: number;
  baseFingerprint: string;
  catalogVersion: string;
  changes: ProposalChange[];
  rationale: string;
  assumptions: string[];
  nonCanonicalSuggestions: string[];
  model?: string;
}

export interface LibraryEntry {
  kind: "draft" | "monster";
  id: string;
  name: string;
  cr?: number;
  role: string;
  status: string;
  revision?: number;
  savedAt?: string | null;
  sourceDraftId?: string;
}

export interface EngineResult {
  draft?: Draft;
  evaluation?: Evaluation;
  monster?: FinishedMonster;
  proposal?: Proposal;
  requirements?: ChoiceRequirement[];
  automaticSelections?: AutomaticSelections;
  selectionBudgets?: SelectionBudgets;
  drafts?: LibraryEntry[];
  monsters?: LibraryEntry[];
  content?: unknown;
}

export interface Change {
  changeId: string;
  type: "set-selection" | "unset-selection" | "set-concept" | "unset-concept";
  field: string;
  value?: unknown;
}
