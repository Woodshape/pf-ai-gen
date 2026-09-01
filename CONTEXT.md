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
The class graft that defines a class-led monster’s array, foundational statistic adjustments, skills, class choices, and primary spellcasting. Its class level determines which level-dependent graft features are active.
_Avoid_: Applying every class graft as primary

**Secondary Class Graft**:
A product extension, informed by Pathfinder Unchained’s secondary-graft option-replacement precedent, for an additional class identity with an explicit positive class level evaluated at effective CR equal to level minus one. It contributes only its fixed and active CR-entry monster options; its selectable option categories replace primary categories without increasing the selectable slot count. It does not contribute an array, foundational statistics, skills, class choices, or primary spellcasting. Secondary grafts are ordered, may include any number of distinct classes, and cannot repeat the primary graft.
_Avoid_: Secondary class concept guidance, stacked foundational adjustments

**Class Progression**:
One Primary Class Graft and zero or more ordered Secondary Class Grafts, each with an explicit positive class level. The combined levels provide a source-guided CR recommendation without overriding the selected encounter CR; a disagreement remains visible as a warning.

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
A visible recommendation for a missing target CR, calculated as the sum of stated class levels minus one. Pathfinder Unchained describes class level minus one as typical rather than mandatory, so the value remains editable.

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

**Creation System**:
The independent axis selecting which source-defined construction rules evaluate a draft: `simple-monster` (Pathfinder Unchained Simple Monster Creation) or `npc` (Core Rulebook class-based NPC creation). It is immutable for the life of a draft and written on every new draft and FinishedMonster snapshot; legacy documents without the field resolve to `simple-monster` without mutation.
_Avoid_: mode (reserved for Strict/Free Mode), engine.

**Simple Monster Creation**:
The existing Pathfinder Unchained array/graft system: CR-based arrays, creature/class/subtype/template grafts, and monster options. The default creation system and the compatibility anchor for all persisted drafts.

**Class-Based NPC Creation**:
Core Rulebook class-based NPC construction using races, ordered class progression, feats, skills, spells, and NPC gear budgets to produce mechanically normal statblocks. It reuses NPC-source policies (basic/heroic arrays, average HP, gear budgets) and is not a PC character builder.

**Basic NPC / Heroic NPC**:
The derived classification of a class-based NPC: any PC class level makes it heroic; only NPC class levels make it basic. Always calculated from the class progression, never selected.

**Creation-System Adapter**:
The internal seam between the shared engine and one creation system. It owns that system's selection fields and validation, choice requirements, rules evaluation, canonical result, derivation trace, and step-to-audit mapping. The shared engine owns lifecycle, persistence, proposals, finalization, exports, and adapter selection.
_Avoid_: spreading creationSystem conditionals outside the adapter.

**Catalog Registry**:
The mapping from creation system to its independently versioned catalog. Each draft's `catalogVersion` refers to its own creation system's catalog; the Simple Monster catalog is frozen and never gains NPC data.

**Creation-System Comparison**:
A read-only benchmark comparison between an evaluation of one creation system and reference rows of another (Simple Monster arrays, Bestiary Table 1-1). Comparisons never mutate the draft or apply foreign arithmetic; class-derived bonuses and array totals must never coexist in one evaluation.
_Avoid_: conversion inside an evaluation, mixed arithmetic.
