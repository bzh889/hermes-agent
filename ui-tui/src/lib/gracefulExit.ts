interface SetupOptions {
  cleanups?: (() => Promise<void> | void)[]
  failsafeMs?: number
  ignoredSignals?: GracefulSignal[]
  onError?: (scope: 'uncaughtException' | 'unhandledRejection', err: unknown) => void
  onSignal?: (signal: NodeJS.Signals) => void
}

export type GracefulSignal = 'SIGHUP' | 'SIGINT' | 'SIGTERM'

const SIGNALS: readonly GracefulSignal[] = ['SIGINT', 'SIGTERM', 'SIGHUP']

const SIGNAL_EXIT_CODE: Record<GracefulSignal, number> = {
  SIGHUP: 129,
  SIGINT: 130,
  SIGTERM: 143
}

let wired = false

export const shouldExitForSignal = (signal: GracefulSignal, ignoredSignals: readonly GracefulSignal[] = []) =>
  !ignoredSignals.includes(signal)

export type TerminalStreamErrorKind = 'input' | 'output'

const TERMINAL_STREAM_ERRNOS = new Set(['EBADF', 'EINVAL', 'EIO', 'EPIPE', 'EPERM'])

/** Classify a broken terminal stream without treating unrelated errors as fatal. */
export const classifyTerminalStreamError = (err: unknown): TerminalStreamErrorKind | null => {
  const value = err as { code?: unknown; message?: unknown } | null
  const code = typeof value?.code === 'string' ? value.code : ''

  if (!TERMINAL_STREAM_ERRNOS.has(code)) {
    return null
  }

  const message = typeof value?.message === 'string' ? value.message : String(err)

  if (/^read\b/i.test(message)) {
    return 'input'
  }

  if (/^write\b/i.test(message)) {
    return 'output'
  }

  return null
}

export function setupGracefulExit({
  cleanups = [],
  failsafeMs = 4000,
  ignoredSignals = [],
  onError,
  onSignal
}: SetupOptions = {}) {
  if (wired) {
    return
  }

  wired = true

  let shuttingDown = false

  const exit = (code: number, signal?: NodeJS.Signals) => {
    if (shuttingDown) {
      return
    }

    shuttingDown = true

    if (signal) {
      onSignal?.(signal)
    }

    setTimeout(() => process.exit(code), failsafeMs).unref?.()

    void Promise.allSettled(cleanups.map(fn => Promise.resolve().then(fn))).finally(() => process.exit(code))
  }

  for (const sig of SIGNALS) {
    process.on(sig, () => {
      if (!shouldExitForSignal(sig, ignoredSignals)) {
        return
      }

      exit(SIGNAL_EXIT_CODE[sig], sig)
    })
  }

  process.on('uncaughtException', err => onError?.('uncaughtException', err))
  process.on('unhandledRejection', reason => onError?.('unhandledRejection', reason))
}
