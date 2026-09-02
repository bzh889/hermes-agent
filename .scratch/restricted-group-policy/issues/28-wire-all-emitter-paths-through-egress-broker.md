# 28 — Wire all emitter paths through the Egress Broker

**What to build:** Every outbound emitter path in the codebase routes through the Egress Broker when operating in restricted context. This includes: final reply, streamed commentary/segment/progress, edit_message, send_message (text, media, reaction, loop mutation), automatic MEDIA/bare-path delivery, TTS, image/audio/video/document delivery, cron fan-out and mirroring, delegated/background completion, Kanban notification, and plugin/webhook/API emitters. Each path calls the Broker before invoking the adapter; paths marked DENY by the policy are blocked before invocation. An E2E test proves a reply arrives in the origin group and a cross-group send is denied with no message delivered to the deny target.

**Blocked by:** 27 — Audit chain: HMAC-linked intent/outcome records

**Status:** ready-for-agent

- [ ] Reply path routes through Broker
- [ ] Stream/progress/edit path routes through Broker
- [ ] send_message (text, media) path routes through Broker
- [ ] send_message reaction path routes through Broker (DENY in restricted context)
- [ ] send_message loop mutation path routes through Broker (DENY in restricted context)
- [ ] Automatic MEDIA/bare-path delivery routes through Broker
- [ ] TTS delivery routes through Broker
- [ ] Cron fan-out path routes through Broker (DENY in restricted context)
- [ ] Cron mirroring path routes through Broker (DENY in restricted context)
- [ ] Delegated/background completion routes through Broker (must return through Broker)
- [ ] Kanban notification path routes through Broker (DENY in restricted context)
- [ ] Integration test: each ALLOW path delivers to the origin group
- [ ] Integration test: each DENY path is blocked before adapter invocation
- [ ] E2E test: reply arrives in origin group; cross-group send denied; no message at deny target
