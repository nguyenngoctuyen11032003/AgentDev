import { describe, expect, it } from 'vitest'
import { buildTree, fileBadge, flattenTree } from './labOutputs.js'

describe('fileBadge', () => {
  it('labels common source files like a code editor explorer', () => {
    expect(fileBadge('main.js')).toEqual({ label: 'JS', tone: 'js' })
    expect(fileBadge('App.jsx').tone).toBe('react')
    expect(fileBadge('vite.config.ts')).toEqual({ label: 'TS', tone: 'ts' })
    expect(fileBadge('package.json')).toEqual({ label: '{}', tone: 'json' })
    expect(fileBadge('package-lock.json').tone).toBe('config')
    expect(fileBadge('.gitignore').tone).toBe('config')
    expect(fileBadge('.env.example').tone).toBe('config')
    expect(fileBadge('README.md').tone).toBe('md')
  })
  it('returns null for files drawn with their kind icon', () => {
    expect(fileBadge('logo.png')).toBeNull()
    expect(fileBadge('clip.mp4')).toBeNull()
  })
})

describe('buildTree', () => {
  it('lists folders before files', () => {
    const tree = buildTree([{ path: '.gitignore' }, { path: 'server/a.js' }, { path: 'client/b.js' }])
    expect(flattenTree(tree, new Set()).map((r) => r.node.name)).toEqual(['client', 'server', '.gitignore'])
  })
})
