// "Prompt cho Flow": a video production package (series/tap_<n>/goi_san_xuat.md) turned into per-shot prompts
// the user pastes into Google Flow, where the Veo of their Google AI plan runs (the API needs paid billing).
// The prompts themselves are made by the backend (agentdev/utils/video_package.py), the same ones Veo would get.

export const PACKAGE_FILE = 'goi_san_xuat.md'
export const BIBLE_FILE = 'ho_so_nhan_vat.md'
export const FLOW_URL = 'https://labs.google/fx/tools/flow'

const dirOf = (path) => String(path || '').split('/').slice(0, -1).join('/')
const join = (dir, name) => (dir ? `${dir}/${name}` : name)

/** Whether a product file is a production package the Flow view can read. */
export const isFlowPackage = (path) => String(path || '').split('/').pop() === PACKAGE_FILE

/**
 * The character bible of a package, as the renderer finds it: next to the episode folder
 * (series/ho_so_nhan_vat.md for series/tap_1/), else <root>/series/, else the package's own folder; '' if none.
 */
export function biblePathFor(packagePath, hasFile) {
  const episodeDir = dirOf(packagePath)
  const candidates = [join(dirOf(episodeDir), BIBLE_FILE), join('series', BIBLE_FILE), join(episodeDir, BIBLE_FILE)]
  return candidates.find((path) => hasFile(path)) || ''
}

/** Every shot as one plain-text block (copy all / .txt download), labelled with the caller's words. */
export function flowPromptsText(shots, label) {
  return (shots || [])
    .map((shot) => `${label(shot)}\n${shot.prompt}`)
    .join('\n\n')
    .concat(shots?.length ? '\n' : '')
}
