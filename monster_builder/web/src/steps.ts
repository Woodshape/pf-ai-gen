import type { Draft, Evaluation } from "./types";

export const STEPS = [
  { n: "B", label: "Before You Begin", short: "Concept", desc: "Record the monster’s concept, target CR, and encounter role. These notes guide choices but never alter statistics." },
  { n: "1", label: "Array", short: "Baseline", desc: "Choose the CR-based array and assign its three positive ability modifiers. Array values are already totals." },
  { n: "2", label: "Creature / Class Graft", short: "Class progression", desc: "Choose a creature type, one primary class graft, and any level-tagged secondary classes. Only the primary controls foundational calculations." },
  { n: "3", label: "Subtype Graft", short: "Optional", desc: "Select every relevant subtype. Subtype grants are additional and do not consume normal slots." },
  { n: "4", label: "Template Graft", short: "Optional", desc: "Apply an optional template and its source-defined choices. Automatic template traits consume normal budgets." },
  { n: "5", label: "Size Graft", short: "Size & movement", desc: "Choose size and movement. Only the listed size-graft adjustments are applied." },
  { n: "6", label: "Spells", short: "Optional magic", desc: "Choose a structured spell list or explicit spells. The engine resolves bands, frequencies, levels, and DCs." },
  { n: "7", label: "Monster Options", short: "Abilities", desc: "Select catalogued options and their typed parameters. The engine owns prerequisites and slot budgets." },
  { n: "8", label: "Skills", short: "Good / master", desc: "Assign master and good skills. Perception is automatically good without consuming a slot." },
  { n: "9", label: "Damage", short: "Attacks", desc: "Build attack presentations. The engine maps average damage to source-backed dice." },
] as const;

const fields = [
  [],
  ["cr", "arrayId", "abilityModifiers", "saveSwap"],
  ["creatureTypeGraftId", "classGraftId", "primaryClassLevel", "secondaryClassGrafts", "classGraftChoices", "graftOptionChoices"],
  ["subtypeGraftIds", "subtypeGraftChoices"],
  ["templateGraftId", "templateGraftChoices"],
  ["sizeId", "speed"],
  ["spellListId", "spellListBenefitChoices", "spells", "spellLevelSource", "spellcastingAbility"],
  ["options"],
  ["skills"],
  ["attacks"],
];

export function stepForPath(path = "") {
  if (path.startsWith("/concept/")) return 0;
  for (let step = 1; step < fields.length; step++) {
    if (fields[step].some((field) => path === `/selections/${field}` || path.startsWith(`/selections/${field}/`))) return step;
  }
  return 0;
}

export function issuesForStep(evaluation: Evaluation, step: number) {
  return evaluation.issues.filter((issue) => stepForPath(issue.path) === step);
}

export function stepStatus(draft: Draft, evaluation: Evaluation, step: number) {
  if (issuesForStep(evaluation, step).some((issue) => issue.severity !== "warning")) return "problem";
  if (step === 0) {
    const concept = draft.concept;
    return concept.name && concept.role && concept.targetCR !== undefined ? "ready" : "open";
  }
  return fields[step].some((field) => draft.selections[field] !== undefined) ? "ready" : "open";
}
