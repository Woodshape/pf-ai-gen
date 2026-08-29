import { readFile } from "node:fs/promises";
import process from "node:process";
import { createInterface } from "node:readline";
import { Type } from "typebox";
import {
  createAgentSession,
  createExtensionRuntime,
  defineTool,
  getAgentDir,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { CatalogToolState } from "./ai_tools.mjs";

const FALLBACK = ["openai-codex", "gpt-5.6-luna"];
const CONCEPT_FIELDS = ["name", "targetCR", "role", "creatureType", "description"];
const SELECTION_FIELDS = [
  "cr", "arrayId", "creatureTypeGraftId", "classGraftId", "primaryClassLevel", "secondaryClassGrafts", "classGraftChoices", "graftOptionChoices",
  "subtypeGraftIds", "subtypeGraftChoices", "templateGraftId", "templateGraftChoices", "sizeId", "saveSwap",
  "abilityModifiers", "options", "skills", "attacks", "speed", "spells", "spellListId", "spellListBenefitChoices",
  "spellLevelSource", "spellcastingAbility",
];
const field = (values) => Type.Union(values.map((value) => Type.Literal(value)));
const change = (type, fields, value) => Type.Object({
  changeId: Type.String(), type: Type.Literal(type), field: field(fields),
  ...(value ? { value } : {}),
  rationale: Type.Optional(Type.String()), sourceRefs: Type.Optional(Type.Array(Type.Any())),
}, { additionalProperties: false });
const STRINGS = Type.Array(Type.String());
const FREE_OBJECT = Type.Record(Type.String(), Type.Any());
const SKILLS = Type.Object({ master: STRINGS, good: STRINGS }, { additionalProperties: false });
const ABILITY_MODIFIERS = Type.Object(Object.fromEntries(
  ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"].map((name) => [name, Type.Optional(Type.Integer())]),
), { additionalProperties: false });
const OPTIONS = Type.Array(Type.Object({ optionId: Type.String(), parameters: Type.Optional(FREE_OBJECT) }, { additionalProperties: false }));
const SECONDARY_CLASS_GRAFTS = Type.Array(Type.Object({
  classGraftId: Type.String(), levels: Type.Integer({ minimum: 1 }),
}, { additionalProperties: false }));
const ATTACKS = Type.Array(Type.Object({
  name: Type.String(), kind: Type.Optional(Type.String()),
  attackProfile: field(["weapon.high", "weapon.low", "natural.two", "natural.three"]),
  naturalAttackId: Type.Optional(Type.String()), profileEntry: Type.Optional(Type.Integer({ minimum: 0 })),
  damageDie: Type.Optional(field(["d4", "d6", "d8", "d10", "d12", "2d6", "2d8", "3d6"])),
}, { additionalProperties: false }));
const SPELLS = Type.Array(Type.Object({
  spellId: Type.String(), spellLevelSource: Type.Optional(Type.String()), metamagic: Type.Optional(STRINGS),
}, { additionalProperties: false }));
export const proposalParameters = Type.Object({
  changes: Type.Array(Type.Union([
    change("set-selection", ["cr"], Type.Number()),
    change("set-selection", ["primaryClassLevel"], Type.Integer({ minimum: 1 })),
    change("set-selection", ["secondaryClassGrafts"], SECONDARY_CLASS_GRAFTS),
    change("set-selection", ["arrayId", "creatureTypeGraftId", "classGraftId", "templateGraftId", "sizeId", "spellListId", "spellLevelSource", "spellcastingAbility"], Type.Union([Type.String(), Type.Null()])),
    change("set-selection", ["subtypeGraftIds"], STRINGS),
    change("set-selection", ["abilityModifiers"], ABILITY_MODIFIERS),
    change("set-selection", ["skills"], SKILLS),
    change("set-selection", ["speed"], Type.Record(Type.String(), Type.Integer({ minimum: 0 }))),
    change("set-selection", ["saveSwap"], Type.Union([Type.Null(), Type.Object({ from: Type.String(), to: Type.String() }, { additionalProperties: false })])),
    change("set-selection", ["classGraftChoices", "graftOptionChoices", "subtypeGraftChoices", "templateGraftChoices", "spellListBenefitChoices"], FREE_OBJECT),
    change("set-selection", ["options"], OPTIONS), change("set-selection", ["attacks"], ATTACKS), change("set-selection", ["spells"], SPELLS),
    change("unset-selection", SELECTION_FIELDS),
    change("set-concept", ["targetCR"], Type.Number()),
    change("set-concept", CONCEPT_FIELDS.filter((name) => name !== "targetCR"), Type.String()),
    change("unset-concept", CONCEPT_FIELDS),
  ])),
  rationale: Type.String(), assumptions: Type.Array(Type.String()),
  nonCanonicalSuggestions: Type.Optional(Type.Array(Type.String())),
}, { additionalProperties: false });

class AdapterError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

const resourceLoader = (systemPrompt) => ({
  getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
  getSkills: () => ({ skills: [], diagnostics: [] }),
  getPrompts: () => ({ prompts: [], diagnostics: [] }),
  getThemes: () => ({ themes: [], diagnostics: [] }),
  getAgentsFiles: () => ({ agentsFiles: [] }),
  getSystemPrompt: () => systemPrompt,
  getSystemPromptSource: () => undefined,
  getAppendSystemPrompt: () => [],
  getAppendSystemPromptSources: () => [],
  extendResources: () => {},
  reload: async () => {},
});

const textResult = (value) => ({ content: [{ type: "text", text: JSON.stringify(value) }], details: {} });

function toolsFor(state) {
  return [
    defineTool({
      name: "catalog_list", label: "List rule catalog", description: "Required first call. Lists every source-valid selection ID by kind.",
      parameters: Type.Object({}), execute: async () => textResult(state.list()),
    }),
    defineTool({
      name: "catalog_search", label: "Search rule catalog", description: "Search source-valid records after catalog_list.",
      parameters: Type.Object({ query: Type.String(), kinds: Type.Optional(Type.Array(Type.String())), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })) }),
      execute: async (_id, args) => textResult(state.search(args.query, args.kinds, args.limit)),
    }),
    defineTool({
      name: "catalog_get", label: "Get rule record", description: "Get one exact source-valid record after catalog_list.",
      parameters: Type.Object({ kind: Type.String(), id: Type.String() }),
      execute: async (_id, args) => textResult(state.get(args.kind, args.id)),
    }),
    defineTool({
      name: "draft_choice_requirements", label: "Get Draft choice requirements", description: "Read the Engine-owned required controls, budgets, and source-backed allowed values after catalog_list.",
      parameters: Type.Object({}), execute: async () => textResult(state.choiceRequirements()),
    }),
    defineTool({
      name: "proposal_validate", label: "Validate candidate Proposal", description: "Evaluate a candidate without persistence or Draft mutation. Returns every evaluation finding and candidate choice requirement. Maximum three calls.",
      parameters: proposalParameters,
      execute: async (_id, args) => textResult(await state.validate({ ...args, nonCanonicalSuggestions: args.nonCanonicalSuggestions || [] })),
    }),
    defineTool({
      name: "emit_proposal", label: "Emit proposal", description: "Emit and terminate only with the exact candidate most recently validated as valid.",
      parameters: proposalParameters,
      execute: async (_id, args) => textResult(state.emit({ ...args, nonCanonicalSuggestions: args.nonCanonicalSuggestions || [] })),
    }),
  ];
}

async function resolveModel(runtime, settings) {
  const configuredId = settings.getDefaultModel();
  const configuredProvider = settings.getDefaultProvider();
  if (configuredId) {
    const model = configuredProvider
      ? runtime.getModel(configuredProvider, configuredId)
      : runtime.getModels().find((candidate) => candidate.id === configuredId);
    if (!model) throw new AdapterError("AI_UNAVAILABLE", `Configured Pi model is unavailable: ${configuredProvider ? `${configuredProvider}/` : ""}${configuredId}`);
    return model;
  }
  const available = await runtime.getAvailable();
  if (available.length) return available[0];
  const fallback = runtime.getModel(...FALLBACK);
  if (fallback && runtime.hasConfiguredAuth(FALLBACK[0])) return fallback;
  throw new AdapterError("AI_NOT_CONFIGURED", `No authenticated Pi model is available (fallback ${FALLBACK.join("/")}).`);
}

export async function generateProposal(input, bridge) {
  if (!input || typeof input !== "object" || !input.draft || typeof input.concept !== "string" || !input.concept.trim()) {
    throw new AdapterError("AI_OUTPUT_INVALID", "draft and a non-empty concept are required");
  }
  let catalog;
  try { catalog = JSON.parse(await readFile(input.catalogPath, "utf8")); }
  catch (error) { throw new AdapterError("CATALOG_UNAVAILABLE", error instanceof Error ? error.message : String(error)); }
  if (!bridge) throw new AdapterError("AI_UNAVAILABLE", "proposal validation bridge is unavailable");
  const state = new CatalogToolState(catalog, {
    choiceRequirements: input.choiceRequirements,
    validateProposal: (proposal, attempt) => bridge.request("proposal_validate", { proposal, attempt }),
  });
  const cwd = input.cwd || process.cwd();
  const agentDir = getAgentDir();
  const fileSettings = SettingsManager.create(cwd, agentDir);
  const modelRuntime = await ModelRuntime.create();
  const model = await resolveModel(modelRuntime, fileSettings);
  const systemPrompt = `You translate a Pathfinder Unchained Simple Monster Creation concept into one typed Proposal.\n\nSecurity and rules:\n- Your first successful tool call MUST be catalog_list.\n- Use only IDs and parameters returned by the catalog tools. Never invent calculated statistics.\n- Use one primary class graft with primaryClassLevel. It alone controls the required array, statistic adjustments, skills, class choices, and primary spellcasting.\n- Put additional classes in an ordered secondaryClassGrafts array with their exact positive levels. Each secondary is evaluated at effective CR = levels - 1 and contributes only its fixed and active CR-entry option grants plus replacement option categories; do not apply secondary arrays, statistics, skills, class choices, or primary spellcasting. Do not repeat a class graft, and do not repeat the primary class.\n- The selected CR remains the encounter CR. If target CR is omitted but class levels are stated, propose CR = sum(levels) - 1 and record that source-guided heuristic as an assumption. If target CR and secondary levels are explicit but the primary level is omitted, infer primaryClassLevel = target CR + 1 - sum(secondary levels); never preserve a multiclass.cr-mismatch finding.\n- Secondary entries that replace Secondary Magic with true spellcasting are not implemented; preserve the Engine finding instead of inventing spells.\n- When CR is known, propose both concept.targetCR and selections.cr and fill every required Strict selection through Steps 1–9, including abilityModifiers, attacks, sizeId, speed, and exact skill budgets. Use catalog tools to resolve uncertain values instead of omitting required fields.\n- Call draft_choice_requirements after catalog_list, then use its Engine-owned controls and budgets. Its automaticSelections.options list shows grants already included by the Engine; do not copy an automatic grant merely to fill slots. Choose other options unless a repeated option is intentional and useful under Duplicate Options (for example, Extra Attack twice). Put only explicit choices that consume the remaining option slots in selections.options.\n- Call proposal_validate for each candidate. It returns all evaluation findings and candidate-specific choice requirements without mutating the Draft. Fix every finding, including warnings; emit_proposal accepts only a warning-free valid evaluation. You have at most three validation calls.\n- Non-canonical ideas belong only in nonCanonicalSuggestions.\n- Changes set or unset whole top-level concept/selection fields.\n- emit_proposal accepts only the exact last candidate validated as valid. Finish with exactly one successful emit_proposal call, then do nothing else.`;
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: true, maxRetries: 1 } });
  const { session } = await createAgentSession({
    cwd, agentDir, model, modelRuntime, thinkingLevel: "medium",
    tools: ["catalog_list", "catalog_search", "catalog_get", "draft_choice_requirements", "proposal_validate", "emit_proposal"],
    customTools: toolsFor(state), resourceLoader: resourceLoader(systemPrompt),
    sessionManager: SessionManager.inMemory(cwd), settingsManager: settings,
  });
  try {
    await session.prompt(`Monster Concept:\n${input.concept}\n\nCurrent authoritative Draft (suggest changes only; do not mutate it):\n${JSON.stringify(input.draft)}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/abort/i.test(message)) throw new AdapterError("AI_ABORTED", message);
    throw new AdapterError("AI_UNAVAILABLE", message);
  } finally {
    session.dispose();
  }
  if (!state.proposal) {
    const feedback = state.lastValidation ? ` Last validation: ${JSON.stringify(state.lastValidation)}` : "";
    throw new AdapterError("PROPOSAL_INVALID", `Pi completed without emitting a validated Proposal.${feedback}`);
  }
  return { proposal: state.proposal, model: `${model.provider}/${model.id}` };
}

class StdioBridge {
  #nextId = 0;
  #pending = new Map();
  #start;
  #resolveStart;

  constructor() {
    this.#start = new Promise((resolve) => { this.#resolveStart = resolve; });
    const lines = createInterface({ input: process.stdin });
    lines.on("line", (line) => {
      let message;
      try { message = JSON.parse(line); } catch { return; }
      if (message.type === "start") this.#resolveStart(message.input);
      if (message.type === "response" && this.#pending.has(message.id)) {
        this.#pending.get(message.id)(message.value);
        this.#pending.delete(message.id);
      }
    });
  }

  start() { return this.#start; }

  request(method, payload) {
    const id = ++this.#nextId;
    return new Promise((resolve) => {
      this.#pending.set(id, resolve);
      process.stdout.write(`${JSON.stringify({ type: "request", id, method, payload })}\n`);
    });
  }

  result(value) { process.stdout.write(`${JSON.stringify({ type: "result", value })}\n`); }
}

async function main() {
  const bridge = new StdioBridge();
  try {
    const input = await bridge.start();
    bridge.result({ ok: true, ...(await generateProposal(input, bridge)) });
  } catch (error) {
    const code = error instanceof AdapterError ? error.code : "AI_UNAVAILABLE";
    bridge.result({ ok: false, error: { code, message: error instanceof Error ? error.message : String(error) } });
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) await main();
