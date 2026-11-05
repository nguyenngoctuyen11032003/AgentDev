// Tabs of the Lab page: scoring a workflow, and Batch Run (formerly its own /batch-run page).
export const LAB_TAB = Object.freeze({ SCORE: 'score', BATCH: 'batch' })
export const LAB_TABS = Object.freeze([LAB_TAB.SCORE, LAB_TAB.BATCH])

export const labTabFromQuery = (value) => {
  const raw = Array.isArray(value) ? value[0] : value
  return raw === LAB_TAB.BATCH ? LAB_TAB.BATCH : LAB_TAB.SCORE
}

// Arrow / Home / End move between tabs (WAI-ARIA tabs pattern); null for any other key
export const nextLabTab = (current, key) => {
  const index = LAB_TABS.indexOf(current)
  if (key === 'ArrowRight') return LAB_TABS[(index + 1) % LAB_TABS.length]
  if (key === 'ArrowLeft') return LAB_TABS[(index - 1 + LAB_TABS.length) % LAB_TABS.length]
  if (key === 'Home') return LAB_TABS[0]
  if (key === 'End') return LAB_TABS[LAB_TABS.length - 1]
  return null
}
