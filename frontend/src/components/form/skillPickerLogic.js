// Pure helpers for SkillPicker (kept out of the SFC so they can be unit-tested without a DOM).

export const namesFrom = (value) =>
  (value?.allow || []).map((entry) => (typeof entry === 'string' ? entry : entry?.name)).filter(Boolean)

// Enabled with an empty allow-list means "every skill" in the runtime; the runtime skips malformed
// skills (valid: false), so they are never counted as ticked.
export function selectedNames(modelValue, library) {
  if (!modelValue?.enabled) return []
  const names = namesFrom(modelValue)
  return names.length ? names : library.filter((s) => s.valid).map((s) => s.name)
}

// Ticked skills that were deleted from the library stay visible so the user can untick them.
export function buildOptions(modelValue, library) {
  const known = new Set(library.map((s) => s.name))
  const missing = namesFrom(modelValue)
    .filter((n) => !known.has(n))
    .map((name) => ({ name, description: '', missing: true }))
  return [...library.filter((s) => s.valid), ...missing]
}

export function toggledValue(selected, name, checked) {
  const next = new Set(selected)
  if (checked) next.add(name)
  else next.delete(name)
  const names = [...next]
  return names.length ? { enabled: true, allow: names.map((n) => ({ name: n })) } : null
}
