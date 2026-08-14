import os from 'node:os'

import type { TestProjectConfiguration } from 'vitest/config'
import { defineConfig } from 'vitest/config'

const isWindows = process.platform === 'win32'

const reactUi: TestProjectConfiguration = {
  extends: './vite.config.ts',
  test: {
    name: 'ui',
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
    // Reusing two thread workers avoids paying a fresh jsdom process startup
    // for every file on Windows. Per-file isolation made this suite take about
    // 50 minutes and intermittently hit Vitest's worker-start deadline; the
    // full suite is the guard against cross-file mock or state leakage.
    pool: isWindows ? 'threads' : 'forks',
    maxWorkers: isWindows ? 2 : undefined,
    // Cold jsdom setup can exceed Vitest's 5000ms default under CI/load.
    // Windows pays a higher transform/environment startup cost, so keep a
    // bounded 30s budget there while preserving the tighter 15s elsewhere.
    testTimeout: isWindows ? 30_000 : 15_000
  }
}

const electronNative: TestProjectConfiguration = {
  test: {
    name: 'electron',
    environment: 'node',
    include: ['electron/**/*.test.ts', 'scripts/**.test.{ts,mjs}'],
    // Native Git and SSH subprocesses are slow enough on Windows that running
    // several test files at once can exceed Vitest's per-test deadline. Keep
    // each isolated file, but run them sequentially with realistic cold-start
    // headroom. The production subprocesses retain their own hard timeouts.
    maxWorkers: isWindows ? 1 : undefined,
    fileParallelism: isWindows ? false : undefined,
    testTimeout: isWindows ? 30_000 : undefined,
    // os.tmpdir() can live below a user HOME that is itself a Git repository.
    // Stop fixture repos from walking upward and mutating that parent repo.
    env: isWindows ? { GIT_CEILING_DIRECTORIES: os.tmpdir() } : undefined
  }
}

export default defineConfig({
  test: {
    projects: [reactUi, electronNative]
  }
})
