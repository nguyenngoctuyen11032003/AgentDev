import { describe, it, expect } from 'vitest'
import { isEchoOfLastReply } from '@/views/launch/launchEvents.js'

const reply = (name, text) => ({ type: 'dialogue', name, text, isRight: false })
const user = (text) => ({ type: 'dialogue', name: 'User', text, isRight: true })

describe('isEchoOfLastReply', () => {
  it('flags a forwarded copy of the reply just shown', () => {
    const chat = [user('test'), reply('Intake', 'Xin chào!\n'), { type: 'notification', message: 'x' }]
    expect(isEchoOfLastReply(chat, '  Xin chào!')).toBe(true)
  })
  it('keeps a different answer and the same text from an earlier turn', () => {
    expect(isEchoOfLastReply([user('a'), reply('Intake', 'one')], 'two')).toBe(false)
    expect(isEchoOfLastReply([reply('Intake', 'same'), user('again')], 'same')).toBe(false)
  })
  it('ignores empty text and an empty chat', () => {
    expect(isEchoOfLastReply([], 'x')).toBe(false)
    expect(isEchoOfLastReply([reply('A', 'x')], '  ')).toBe(false)
  })
})
