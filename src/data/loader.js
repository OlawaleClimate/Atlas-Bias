const biasModules = import.meta.glob("./entries/*.json", { eager: true });

export function loadBiasEntries() {
  return Object.values(biasModules)
    .map((module) => module.default)
    .sort((a, b) => a.name.localeCompare(b.name));
}
