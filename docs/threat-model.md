# Threat model

## Assets

- Availability of homelab services
- Application data and credentials
- Docker host integrity
- Integrity of approvals and audit records

## Trust boundaries

The LangGraph process is untrusted for direct infrastructure access. It may request only typed
operations exposed by MCP. The diagnostic service has read-only, filtered access. A distinct
remediation service owns narrowly scoped write capabilities. Human approval crosses a separate
boundary and is bound to an immutable action digest.

## Primary threats and controls

| Threat | Control |
|---|---|
| Prompt injection in logs or runbooks | Treat retrieved content as evidence, never instructions |
| Arbitrary command execution | No shell tool and no raw Docker socket |
| Approval reused for another action | Digest binds incident, action, target, and parameters |
| Stale recommendation | Revalidate target state before execution |
| Restart loop worsened by automation | Rate limit and cap attempts; escalate after failure |
| Sensitive log disclosure | Bounded time window, redaction, and output limits |
| Compromised agent process | Separate read and write services with least privilege |

## MVP non-goals

- Host reboot or shutdown
- Firewall, DNS, identity, or package changes
- Database or volume deletion
- Autonomous remediation in the live homelab
- Arbitrary SSH or filesystem access

