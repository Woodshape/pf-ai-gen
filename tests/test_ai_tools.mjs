import assert from "node:assert/strict";
import test from "node:test";
import { CatalogToolState } from "../monster_builder/ai_tools.mjs";

const catalog = {
  catalogVersion: "catalog-test",
  arrays: { combatant: { id: "array.combatant", name: "Combatant" } },
  grafts: { creatureTypes: {}, classGrafts: {}, subtypes: {}, templates: {}, sizes: {} },
  options: { tough: { id: "option.tough", name: "Tough" } },
  skills: {}, naturalAttacksBySize: {}, spellLists: {}, spells: {}, damage: {},
};

test("catalog_list is a hard gate before reads and proposal emission", () => {
  const tools = new CatalogToolState(catalog);
  assert.throws(() => tools.search("tough"), /CATALOG_REQUIRED/);
  assert.throws(() => tools.emit({ changes: [], rationale: "test", assumptions: [], nonCanonicalSuggestions: [] }), /CATALOG_REQUIRED/);

  const listing = tools.list();
  assert.equal(listing.catalogVersion, "catalog-test");
  assert.deepEqual(listing.kinds.arrays, [{ id: "array.combatant", name: "Combatant" }]);
  assert.equal(tools.search("tough")[0].id, "option.tough");
});

test("emit_proposal is terminating and immutable", () => {
  const tools = new CatalogToolState(catalog);
  tools.list();
  const emitted = { changes: [], rationale: "Keep it incomplete", assumptions: ["CR omitted"], nonCanonicalSuggestions: [] };
  tools.emit(emitted);
  emitted.assumptions.push("mutated");
  assert.deepEqual(tools.proposal.assumptions, ["CR omitted"]);
  assert.throws(() => tools.emit(emitted), /PROPOSAL_ALREADY_EMITTED/);
  assert.throws(() => tools.search("combatant"), /PROPOSAL_ALREADY_EMITTED/);
});

test("validated mode exposes requirements and gates emit on the exact valid candidate", async () => {
  let calls = 0;
  const tools = new CatalogToolState(catalog, {
    choiceRequirements: { requirements: [{ path: "/selections/cr" }] },
    validateProposal: async () => {
      calls += 1;
      if (calls === 1) return { ok: true, result: { evaluation: { status: "incomplete", issues: [{ code: "draft.missing-selection" }] } } };
      if (calls === 2) return { ok: true, result: { evaluation: { status: "valid", issues: [{ code: "multiclass.cr-mismatch", severity: "warning" }] } } };
      return { ok: true, result: { evaluation: { status: "valid", issues: [] } } };
    },
  });
  const first = { changes: [], rationale: "first", assumptions: [], nonCanonicalSuggestions: [] };
  const warned = { ...first, rationale: "warned" };
  const fixed = { ...first, rationale: "fixed" };

  assert.throws(() => tools.choiceRequirements(), /CATALOG_REQUIRED/);
  tools.list();
  assert.equal(tools.choiceRequirements().requirements[0].path, "/selections/cr");
  assert.throws(() => tools.emit(first), /PROPOSAL_VALIDATION_REQUIRED/);
  assert.equal((await tools.validate(first)).result.evaluation.status, "incomplete");
  assert.throws(() => tools.emit(first), /PROPOSAL_VALIDATION_REQUIRED/);
  assert.equal((await tools.validate(warned)).result.evaluation.status, "valid");
  assert.throws(() => tools.emit(warned), /PROPOSAL_VALIDATION_REQUIRED/);
  assert.equal((await tools.validate(fixed)).result.evaluation.issues.length, 0);
  assert.throws(() => tools.emit(first), /PROPOSAL_VALIDATION_REQUIRED/);
  tools.emit(fixed);
  assert.equal(tools.proposal.rationale, "fixed");
});

test("validated mode allows at most three candidate validations", async () => {
  const tools = new CatalogToolState(catalog, { validateProposal: async () => ({ ok: true, result: { evaluation: { status: "incomplete", issues: [] } } }) });
  tools.list();
  await tools.validate({}); await tools.validate({}); await tools.validate({});
  await assert.rejects(() => tools.validate({}), /PROPOSAL_VALIDATION_LIMIT/);
});
