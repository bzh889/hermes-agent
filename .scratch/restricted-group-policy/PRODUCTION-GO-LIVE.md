# Production Go-Live Guide — Restricted Group Policy

## Prerequisites

1. All 295 tests pass (verified)
2. Code review complete (0 hard violations)
3. Gateway restarted after `config.yaml` changes

## Step 1: Define a policy in config.yaml

Add under `gateway.restricted_group.policies`:

```yaml
gateway:
  restricted_group:
    policies:
      rgp-monitor-group:
        version: "rev-001"
        capabilities:
          - cq_read
          - egress_reply
          - egress_stream
          - egress_edit
          - egress_send_message
          - egress_derived_media
        conv_id: "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
        account_id: ""        # empty = wildcard (any account)
        active: true
        production_activated_by: "mtk12265"  # your owner ID
        production_activated_at: 0           # set on first activation
```

## Step 2: Restart the gateway

```bash
hermes gateway restart
```

## Step 3: Run post-deploy seam probes

Use the `run_seam_probes()` function from `gateway/phase5_capabilities.py`:

```python
from gateway.phase5_capabilities import run_seam_probes

probes = {
    "origin_binding": lambda: True,  # replace with real probe
    "egress_broker": lambda: True,
    "cq_read_broker": lambda: True,
    "model_routing_gate": lambda: True,
    "audit_chain": lambda: True,
    "semantic_history": lambda: True,
    "durable_approval": lambda: True,
    "sandbox": lambda: True,
}

results = run_seam_probes(probes)
print(results)
# All True → all seams healthy
```

## Step 4: Observation window

Monitor 30 consecutive operations in the restricted group:

```python
from gateway.phase5_capabilities import ObservationWindow

window = ObservationWindow(required_clean=30)
# After each restricted-group operation:
#   If clean: window.record_clean()
#   If violation: window.record_violation(seam, reason)
# Check: window.passed → True after 30 consecutive clean operations
```

## Step 5: Rollback

To disable the policy:

```bash
hermes config set gateway.restricted_group.policies.rgp-monitor-group.active false
hermes gateway restart
```

## Verification checklist

- [ ] config.yaml has policy definition
- [ ] Gateway restarted
- [ ] All 8 seam probes return True
- [ ] 30 consecutive operations with 0 violations
- [ ] Rollback path tested
