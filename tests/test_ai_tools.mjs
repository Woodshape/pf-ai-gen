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
