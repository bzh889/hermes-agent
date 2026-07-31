Make `.\hermes desktop` install and launch reliably on the MTK Windows network.

- Current state: the real command still fails while Electron's postinstall downloads its binary with `read ECONNRESET`; npm removes the staged Electron package before Hermes can recover.
- Completion proof: run the unmodified `.\hermes desktop` path through dependency installation and confirm the Desktop process starts.
- Next: move Electron's binary fetch after npm installation, use the Windows certificate store, then run focused tests and the real command.
- Guardrails: never disable TLS verification; preserve all pre-existing worktree changes.
- Deferred: npm dependency deprecation notices are separate maintenance work unless they cause this install failure.
