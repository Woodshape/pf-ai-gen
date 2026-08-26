import { readFile } from "node:fs/promises";
import process from "node:process";
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
  "cr", "arrayId", "creatureTypeGraftId", "classGraftId", "classGraftChoices", "graftOptionChoices",
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
      name: "emit_proposal", label: "Emit proposal", description: "Emit the one immutable proposal and terminate.",
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

export async function generateProposal(input) {
  if (!input || typeof input !== "object" || !input.draft || typeof input.concept !== "string" || !input.concept.trim()) {
    throw new AdapterError("AI_OUTPUT_INVALID", "draft and a non-empty concept are required");
  }
  let catalog;
  try { catalog = JSON.parse(await readFile(input.catalogPath, "utf8")); }
  catch (error) { throw new AdapterError("CATALOG_UNAVAILABLE", error instanceof Error ? error.message : String(error)); }
  const state = new CatalogToolState(catalog);
  const cwd = input.cwd || process.cwd();
  const agentDir = getAgentDir();
  const fileSettings = SettingsManager.create(cwd, agentDir);
  const modelRuntime = await ModelRuntime.create();
  const model = await resolveModel(modelRuntime, fileSettings);
  const systemPrompt = `You translate a Pathfinder Unchained Simple Monster Creation concept into one typed Proposal.\n\nSecurity and rules:\n- Your first successful tool call MUST be catalog_list.\n- Use only IDs and parameters returned by the catalog tools. Never invent calculated statistics.\n- One primary class graft only. Represent secondary classes with catalogued options/skills.\n- If target CR is omitted but class levels are stated, propose CR = sum(levels) - 1 and record that product heuristic as an assumption.\n- When CR is known, propose both concept.targetCR and selections.cr and fill every required Strict selection through Steps 1–9, including abilityModifiers, attacks, sizeId, speed, and exact skill budgets. Use catalog tools to resolve uncertain values instead of omitting required fields.\n- The candidate Draft must evaluate as valid; fix every evaluation issue supplied during a repair attempt.\n- Non-canonical ideas belong only in nonCanonicalSuggestions.\n- Changes set or unset whole top-level concept/selection fields.\n- Finish with exactly one emit_proposal call, then do nothing else.`;
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: true, maxRetries: 1 } });
  const { session } = await createAgentSession({
    cwd, agentDir, model, modelRuntime, thinkingLevel: "medium",
    tools: ["catalog_list", "catalog_search", "catalog_get", "emit_proposal"],
    customTools: toolsFor(state), resourceLoader: resourceLoader(systemPrompt),
    sessionManager: SessionManager.inMemory(cwd), settingsManager: settings,
  });
  try {
    const repair = input.repair ? `\n\nRepair attempt: the Engine rejected or found the previous candidate incomplete. Correct every supplied error/finding and emit a complete replacement Proposal. Re-query catalog records as needed.\nEngine feedback: ${JSON.stringify(input.repair.error || input.repair.evaluation)}\nRejected Proposal: ${JSON.stringify(input.repair.proposal)}` : "";
    await session.prompt(`Monster Concept:\n${input.concept}\n\nCurrent authoritative Draft (suggest changes only; do not mutate it):\n${JSON.stringify(input.draft)}${repair}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/abort/i.test(message)) throw new AdapterError("AI_ABORTED", message);
    throw new AdapterError("AI_UNAVAILABLE", message);
  } finally {
    session.dispose();
  }
  if (!state.proposal) throw new AdapterError("AI_OUTPUT_INVALID", "Pi completed without emit_proposal");
  return { proposal: state.proposal, model: `${model.provider}/${model.id}` };
}

async function main() {
  try {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    const input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    process.stdout.write(JSON.stringify({ ok: true, ...(await generateProposal(input)) }));
  } catch (error) {
    const code = error instanceof AdapterError ? error.code : "AI_UNAVAILABLE";
    process.stdout.write(JSON.stringify({ ok: false, error: { code, message: error instanceof Error ? error.message : String(error) } }));
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) await main();
