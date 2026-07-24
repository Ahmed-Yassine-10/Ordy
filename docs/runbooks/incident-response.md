# Incident response runbook

Ordy takes real actions for real restaurants. An incident here can mean wrong orders,
leaked customer data, or a runaway vendor bill. This runbook is written to be followed at
3am by whoever is on call.

## Severity

| Sev | Meaning | Examples | Response |
|---|---|---|---|
| **SEV1** | Customer data exposure, cross-tenant leak, or the agent placing unauthorized orders | RLS bypass, action gate defeated, credential leak | Page immediately; all-hands; tenant notification clock starts (72h GDPR) |
| **SEV2** | Core function down or degraded for many tenants | Voice sessions failing, orders not reaching dashboards, DB unavailable | Page; target mitigation < 1h |
| **SEV3** | Single-tenant or degraded-but-working | One restaurant's workflow drifted, webhook backlog | Next business day |
| **SEV4** | Cosmetic / no customer impact | Dashboard glitch | Backlog |

## First 15 minutes

1. **Declare.** Post in `#incident` with severity, one-line symptom, and your name as IC.
   Declaring early is free; a missed SEV1 is not.
2. **Stop the bleeding before diagnosing.** Reach for the kill switches below.
3. **Preserve evidence.** Do not delete pods, rows, or artifacts. Snapshot logs/traces by
   conversation or action id.
4. **Start a timeline** in the incident doc — every action with a timestamp.

## Kill switches

| Situation | Action |
|---|---|
| Agent taking bad actions | Disable the tool per tenant: `PUT /v1/restaurants/{id}/tools/{key}` `{"enabled": false}` — takes effect on the next turn |
| Browser automation misbehaving | `POST /v1/restaurants/{id}/workflows/{wid}/disable` → orders fall back to Ordy's own store |
| Vendor spend runaway | Cost circuit breaker trips automatically; to force it, set the tenant/platform budget to 0 and redeploy config |
| A tenant under abuse | Tighten caps in `restaurant_tools.caps`; set `voice_enabled=false` to stop new sessions |
| Bad deploy | Roll back the image tag (previous SHA is always deployable); migrations are expand-migrate-contract so a rollback does not require a down-migration |

## Playbooks

### Suspected cross-tenant data exposure (SEV1)
1. Capture the offending request/query and the `restaurant_id` involved.
2. Verify with the RLS isolation suite against a snapshot — is the policy missing, or was
   the tenant context set wrong?
3. If a policy is missing: apply it immediately (`ALTER TABLE … FORCE ROW LEVEL SECURITY`
   + policy), then audit which rows were reachable and for how long.
4. Determine affected tenants from audit logs. Start the **72-hour** notification clock.
5. Post-incident: add the missing table to the CI isolation test list — the gap must be
   impossible to reintroduce.

### The agent placed an unauthorized/wrong order (SEV1)
1. Pull `action_executions` for the conversation — the stored **validation report** shows
   exactly which checks ran and what passed.
2. If the gate passed something it shouldn't: disable the tool for all tenants (feature
   flag), then write a failing red-team test **before** the fix.
3. Contact affected restaurants directly; cancel orders via the compensation path.

### Vendor cost spike (SEV2)
1. Check the breaker state and per-tenant `usage_records` — is it one tenant, one model
   tier, or platform-wide?
2. If abuse: tighten that tenant's rate limits and caps.
3. If a loop: identify the conversation, end the session, and cap the per-conversation
   action budget.

### Orders not reaching a restaurant (SEV2)
1. Check the adapter: is the integration down and did the **fallback to native** fire?
   (`orders.executed_via` shows what actually happened.)
2. If orders are in Ordy but staff didn't see them, this is a notification failure, not an
   order-loss — tell the restaurant immediately and read them the pending list.

## Communication

- **Internal:** `#incident` channel, IC owns updates every 30 min for SEV1/2.
- **Tenants:** status page for platform-wide; direct email/phone for tenant-specific data
  or order incidents. Say what happened, what we did, what they should do.
- **Regulators:** personal-data breaches → 72 hours (GDPR Art. 33). Legal is looped in at
  declaration time for any SEV1 involving customer data.

## After

Within 5 business days: blameless post-incident review covering timeline, contributing
factors, what detected it (and what should have), and action items with owners. Every
SEV1/2 must produce at least one **test or gate** that would have caught it.
