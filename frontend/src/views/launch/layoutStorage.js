// Per-browser layout memory (localStorage may be unavailable: private mode, blocked storage)
export const readStorage = (key) => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
export const writeStorage = (key, value) => {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // per-browser convenience only
  }
}
