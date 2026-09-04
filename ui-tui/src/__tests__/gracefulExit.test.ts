import { describe, expect, it } from 'vitest'

import { classifyTerminalStreamError, shouldExitForSignal } from '../lib/gracefulExit.js'

describe('shouldExitForSignal', () => {
  it('ignores only the signals explicitly disabled for embedded dashboard chat', () => {
    expect(shouldExitForSignal('SIGINT', ['SIGINT'])).toBe(false)
    expect(shouldExitForSignal('SIGTERM', ['SIGINT'])).toBe(true)
    expect(shouldExitForSignal('SIGHUP', ['SIGINT'])).toBe(true)
  })
})

describe('classifyTerminalStreamError', () => {
  it('treats a Windows read EPERM as a dead terminal input stream', () => {
    const error = Object.assign(new Error('read EPERM'), { code: 'EPERM' })

    expect(classifyTerminalStreamError(error)).toBe('input')
  })

  it('keeps unrelated EPERM errors out of terminal cleanup', () => {
    const error = Object.assign(new Error('open EPERM'), { code: 'EPERM' })

    expect(classifyTerminalStreamError(error)).toBeNull()
  })

  it('keeps write-pipe failures on the output-stream path', () => {
    const error = Object.assign(new Error('write EPIPE'), { code: 'EPIPE' })

    expect(classifyTerminalStreamError(error)).toBe('output')
  })
})
