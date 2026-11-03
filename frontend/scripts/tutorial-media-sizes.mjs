// Writes src/utils/tutorialMediaSizes.json: { "file.png": [width, height] } for every PNG / WebP /
// JPEG in public/media. The tutorial gives each image its real size so the page does not jump while
// lazy images load during scrolling. Re-run after adding or replacing tutorial images:
//   node scripts/tutorial-media-sizes.mjs
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const mediaDir = join(root, 'public', 'media')

function pngSize(buf) {
  if (buf.toString('ascii', 1, 4) !== 'PNG') return null
  return [buf.readUInt32BE(16), buf.readUInt32BE(20)]
}

function webpSize(buf) {
  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WEBP') return null
  const chunk = buf.toString('ascii', 12, 16)
  if (chunk === 'VP8X') return [1 + buf.readUIntLE(24, 3), 1 + buf.readUIntLE(27, 3)]
  if (chunk === 'VP8 ') return [buf.readUInt16LE(26) & 0x3fff, buf.readUInt16LE(28) & 0x3fff]
  if (chunk === 'VP8L') {
    const b = buf.readUInt32LE(21)
    return [1 + (b & 0x3fff), 1 + ((b >> 14) & 0x3fff)]
  }
  return null
}

function jpegSize(buf) {
  if (buf[0] !== 0xff || buf[1] !== 0xd8) return null
  let i = 2
  while (i < buf.length) {
    if (buf[i] !== 0xff) return null
    const marker = buf[i + 1]
    const len = buf.readUInt16BE(i + 2)
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      return [buf.readUInt16BE(i + 7), buf.readUInt16BE(i + 5)]
    }
    i += 2 + len
  }
  return null
}

const sizes = {}
for (const name of readdirSync(mediaDir).sort()) {
  if (!/\.(png|webp|jpe?g)$/i.test(name)) continue
  const buf = readFileSync(join(mediaDir, name))
  const size = pngSize(buf) || webpSize(buf) || jpegSize(buf)
  if (size && size[0] > 0 && size[1] > 0) sizes[name] = size
}

writeFileSync(join(root, 'src', 'utils', 'tutorialMediaSizes.json'), JSON.stringify(sizes, null, 2) + '\n')
console.log(`${Object.keys(sizes).length} image sizes written`)
