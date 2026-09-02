# Prove the origin-bound egress boundary end to end

Type: task
Status: open
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 17, 18

## Question

Execute the complete Egress Escape Matrix against the implemented Broker and approved non-production fixtures. For every current and dynamically registered Restricted Task emitter, first prove safe pre-gate reachability, then verify the policy-defined exact-origin outcome, forced cross-group/DM/platform/account/tenant/thread/route denial before adapter invocation where required, independent source-and-target readback, restart and indeterminate-result reconciliation, same-identity retry only after confirmed absence, and cleanup. Capture and verify relay frames preserve both logical and transport platform identities; run concurrent cron deliveries and simultaneous process watchers to prove no ContextVar, target, or completion cross-talk; restart with a deliberately stale/reused PID and prove `host_start_time` prevents adoption of the wrong process. Fix implementation defects rather than weakening tests; attach content-minimized evidence with exact counts, target readback, failures, and blockers. This ticket does not authorize production Monitor Group activation.
