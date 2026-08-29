const COLLECTIONS = {
  arrays: (catalog) => catalog.arrays,
  creatureTypes: (catalog) => catalog.grafts?.creatureTypes,
  classGrafts: (catalog) => catalog.grafts?.classGrafts,
  subtypes: (catalog) => catalog.grafts?.subtypes,
  templates: (catalog) => catalog.grafts?.templates,
  sizes: (catalog) => catalog.grafts?.sizes,
  options: (catalog) => catalog.options,
  skills: (catalog) => catalog.skills,
  naturalAttacks: (catalog) => catalog.naturalAttacksBySize,
  spellLists: (catalog) => catalog.spellLists,
  spells: (catalog) => catalog.spells,
  damageProfiles: (catalog) => catalog.damage,
};

const clone = (value) => structuredClone(value);
const canonical = (value) => JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item)
  ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right)))
  : item);

export class CatalogToolState {
  #catalog;
  #listed = false;
  #proposal;
  #choiceRequirements;
  #validateProposal;
  #validationCount = 0;
  #lastValidation;
  #lastValidProposal;

  constructor(catalog, { choiceRequirements, validateProposal } = {}) {
    this.#catalog = catalog;
    this.#choiceRequirements = choiceRequirements;
    this.#validateProposal = validateProposal;
  }

  get proposal() { return this.#proposal && clone(this.#proposal); }
  get lastValidation() { return this.#lastValidation && clone(this.#lastValidation); }

  list() {
    if (this.#proposal) throw new Error("PROPOSAL_ALREADY_EMITTED");
    const kinds = {};
    for (const [kind, records] of this.#collections()) {
      kinds[kind] = records.map(({ key, value }) => ({ id: value.id || `${kind}.${key}`, name: value.name || value.sourceRef?.entry || key }));
    }
    this.#listed = true;
    return { catalogVersion: this.#catalog.catalogVersion, kinds };
  }

  search(query, kinds, limit = 30) {
    this.#requireList();
    if (typeof query !== "string" || !query.trim()) throw new Error("CATALOG_QUERY_REQUIRED");
    const allowed = kinds?.length ? new Set(kinds) : undefined;
    const needle = query.toLocaleLowerCase();
    return this.#collections()
      .filter(([kind]) => !allowed || allowed.has(kind))
      .flatMap(([kind, records]) => records.map(({ key, value }) => ({ kind, key, ...value })))
      .filter((record) => JSON.stringify(record).toLocaleLowerCase().includes(needle))
      .slice(0, Math.max(1, Math.min(100, Number(limit) || 30)))
      .map(clone);
  }

  get(kind, id) {
    this.#requireList();
    const collection = this.#collections().find(([name]) => name === kind);
    if (!collection) throw new Error(`CATALOG_KIND_UNKNOWN: ${kind}`);
    const found = collection[1].find(({ key, value }) => key === id || value.id === id);
    if (!found) throw new Error(`CATALOG_ID_UNKNOWN: ${id}`);
    return clone({ kind, key: found.key, ...found.value });
  }

  choiceRequirements() {
    this.#requireList();
    return clone(this.#choiceRequirements || {});
  }

  async validate(proposal) {
    this.#requireList();
    if (!this.#validateProposal) throw new Error("PROPOSAL_VALIDATION_UNAVAILABLE");
    if (this.#validationCount >= 3) throw new Error("PROPOSAL_VALIDATION_LIMIT");
    this.#validationCount += 1;
    const result = await this.#validateProposal(clone(proposal), this.#validationCount);
    this.#lastValidation = clone(result);
    const evaluation = result?.result?.evaluation;
    this.#lastValidProposal = result?.ok && evaluation?.status === "valid" && evaluation.issues?.length === 0 ? canonical(proposal) : undefined;
    return clone(result);
  }

  emit(proposal) {
    this.#requireList();
    if (this.#proposal) throw new Error("PROPOSAL_ALREADY_EMITTED");
    if (this.#validateProposal && this.#lastValidProposal !== canonical(proposal)) throw new Error("PROPOSAL_VALIDATION_REQUIRED");
    this.#proposal = clone(proposal);
    return { accepted: true, terminating: true };
  }

  #requireList() {
    if (this.#proposal) throw new Error("PROPOSAL_ALREADY_EMITTED");
    if (!this.#listed) throw new Error("CATALOG_REQUIRED");
  }

  #collections() {
    return Object.entries(COLLECTIONS).map(([kind, read]) => [kind, Object.entries(read(this.#catalog) || {}).map(([key, value]) => ({ key, value }))]);
  }
}
