import { describe, expect, it } from 'vitest'
import { CATEGORY_IDS, categoryOf, countByCategory, filterSkills, groupByCategory } from './skillCategories'

const skills = [
  { name: 'remotion-render', description: 'Render MP4', category: 'video' },
  { name: 'heygen', description: 'Avatar video', category: 'video' },
  { name: 'systematic-debugging', description: 'When a test fails', category: 'dev' },
  { name: 'legacy', description: 'No category from an old backend' }
]

describe('skillCategories', () => {
  it('matches the backend category ids and order', () => {
    expect(CATEGORY_IDS).toEqual(['video', 'image', 'audio', 'motion', 'marketing', 'design', 'dev', 'workflow', 'docs', 'other'])
  })

  it('treats unknown or missing categories as other', () => {
    expect(categoryOf({ category: 'cooking' })).toBe('other')
    expect(categoryOf({})).toBe('other')
  })

  it('counts every category, including empty ones and all', () => {
    const counts = countByCategory(skills)
    expect(counts).toMatchObject({ all: 4, video: 2, dev: 1, other: 1, image: 0 })
  })

  it('groups only non-empty categories, in display order', () => {
    expect(groupByCategory(skills).map((g) => [g.id, g.skills.length])).toEqual([['video', 2], ['dev', 1], ['other', 1]])
  })

  it('filters by query inside a category', () => {
    expect(filterSkills(skills, { query: 'avatar' }).map((s) => s.name)).toEqual(['heygen'])
    expect(filterSkills(skills, { category: 'video', query: 'test' })).toEqual([])
    expect(filterSkills(skills, { category: 'dev' }).map((s) => s.name)).toEqual(['systematic-debugging'])
  })

  it('finds skills by words in the plain-language guide', () => {
    const guided = [{ name: 'heygen-video', description: 'Presenter videos', guide: { purpose: 'Tạo video người dẫn chuyện' } }]
    expect(filterSkills(guided, { query: 'người dẫn' })).toHaveLength(1)
  })
})
