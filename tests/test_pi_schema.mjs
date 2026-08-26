import assert from "node:assert/strict";
import test from "node:test";
import { Value } from "typebox/value";
import { proposalParameters } from "../monster_builder/pi_adapter.mjs";

const base = { changes: [], rationale: "", assumptions: [], nonCanonicalSuggestions: [] };
const proposal = (change) => ({ ...base, changes: [change] });

test("proposal schema binds concept and selection fields to their change types", () => {
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "name", type: "set-concept", field: "name", value: "Hunter" })), true);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "name", type: "set-selection", field: "name", value: "Hunter" })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "array", type: "set-selection", field: "arrayId", value: "array.combatant" })), true);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "ac", type: "set-selection", field: "ac", value: 99 })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "skills", type: "set-selection", field: "skills", value: ["skill.perception"] })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "skills", type: "set-selection", field: "skills", value: { master: ["skill.perception"], good: [] } })), true);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "options", type: "set-selection", field: "options", value: [{ optionId: "option.extra-attack", choices: {} }] })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "attack", type: "set-selection", field: "attacks", value: [{ name: "longsword" }] })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "attack", type: "set-selection", field: "attacks", value: [{ name: "longsword", attackProfile: "weapon.high", damageDie: "1d8" }] })), false);
  assert.equal(Value.Check(proposalParameters, proposal({ changeId: "attack", type: "set-selection", field: "attacks", value: [{ name: "longsword", attackProfile: "weapon.high", damageDie: "d8" }] })), true);
});
