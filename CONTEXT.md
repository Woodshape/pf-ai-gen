# Pathfinder Monster Creation

This context covers creating Pathfinder 1e monsters with the *Pathfinder Unchained* Simple Monster Creation system and turning a monster concept into a validated, editable monster sheet.

## Language

**Monster Concept**:
The intended creature, role, theme, CR, and narrative identity that guide the creation process.
_Avoid_: Archetype when referring to the overall creature idea.

**Array**:
The CR-based Combatant, Expert, or Spellcaster baseline that supplies a monster's core statistics and option budget.

**Graft**:
A source-defined set of adjustments applied for a creature type, class, subtype, template, or size.

**Primary Class Graft**:
The single class graft that defines a class-led monster in Strict Mode. Secondary class identities are concept guidance and can only be represented through separately catalogued skills or monster options.
_Avoid_: Multiclass simulation, stacked class grafts

**Monster Option**:
A source-defined combat, magic, social, or universal ability used to specialize a monster beyond its array and grafts.

**Monster Draft**:
The current editable set of concept choices and source-valid selections for a monster. It may be incomplete, contains no calculated statistics, and changes through numbered revisions.

**Proposal**:
An initial or iterative set of typed suggestions from an AI or user, anchored to a Draft revision. A Proposal is not authoritative until selected changes are accepted and validated by the rules engine.

**Concept-to-Proposal Adapter**:
An optional boundary that translates a natural-language Monster Concept into an immutable Proposal without mutating the Monster Draft. It may infer visible assumptions, but it cannot make non-catalogued selections authoritative.
_Avoid_: AI Draft mutation, automatic proposal application

**Inferred CR**:
A visible product assumption for a missing target CR, calculated in the MVP as the sum of stated class levels minus one. It is not a source-derived Pathfinder value and remains editable until the user confirms a valid Draft selection.

**Evaluation**:
The deterministic result calculated from the current Monster Draft. It exposes the canonical Strict result and, when applicable, the effective Free result.

**Reality-Check Item**:
A review finding that records a mismatch between the concept, benchmarks, or expected behavior and an Evaluation. It can be acknowledged, resolved through strict selections, accepted through a Free Override, or dismissed; it is not itself a value change.

**Free Override**:
An explicitly accepted change to a monster-relevant calculated field layered over a valid canonical result. Free Overrides do not trigger recalculation of other fields and never alter system or provenance data.

**Strict Mode**:
The default rules-engine mode. It accepts only catalogued source selections and recalculates all derived values without arbitrary overrides.

**Free Mode**:
A non-canonical mode that starts from a valid Strict Evaluation and applies explicitly accepted Free Overrides. The canonical result remains available for comparison.

**Monster Sheet**:
The finished Pathfinder-style presentation of the selected final result. A Strict sheet uses the canonical result; a Free sheet uses only the final effective result, not both alternatives.
