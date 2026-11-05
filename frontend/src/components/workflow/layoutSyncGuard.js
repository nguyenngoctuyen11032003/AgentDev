/**
 * Decide whether a saved Vue Flow layout may be reconciled against the YAML graph (and the result
 * written back). Reconciling against a graph that failed to load, failed to parse, or still belongs
 * to the previously open workflow would drop every step from the layout and the save would wipe the
 * stored positions, so only a graph parsed for this very workflow qualifies.
 *
 * @param {object} state
 * @param {string} state.workflowName        workflow whose layout is being loaded
 * @param {string|null} state.yamlLoadedFor  workflow whose YAML last loaded AND parsed successfully
 * @param {*} state.loadError                YAML load error of the last attempt (falsy when ok)
 * @param {*} state.parseError               YAML parse error of the last attempt (falsy when ok)
 * @param {*} state.graph                    the parsed `graph` section
 * @returns {boolean}
 */
export const canReconcileLayout = ({ workflowName, yamlLoadedFor, loadError, parseError, graph } = {}) => {
  if (!workflowName || yamlLoadedFor !== workflowName) return false
  if (loadError || parseError) return false
  return Boolean(graph) && typeof graph === 'object' && !Array.isArray(graph)
}
