# PII Deletion/Export Request Runbook (Draft, process ticket)

**Status:** Draft / process ticket. No automated PII deletion/export workflow is implemented in MVP.

## Purpose

Define a safe, auditable process for handling customer PII export/deletion requests before pilot. This is required because PII is stored in `customer_profiles` and encrypted with `APP_SECRET_KEY`.

## Scope

- In scope: `customer_profiles` PII (phone/name/email/address as present), related request/booking linkage where legally required.
- Out of scope (for now): automatic self-service user deletion, cross-system DSR orchestration, legal sign-off.

## Roles

- **Request owner (Support/Legal):** receives request, verifies identity, opens ticket.
- **Approver (Legal/Compliance/Owner):** confirms legal basis and action.
- **Operator (Ops/Platform admin):** executes approved procedure in controlled environment.
- **Auditor:** reviews audit trail and evidence.

## Intake checklist

1. Create ticket with request ID, tenant slug, requester identity proof, request type (`export` or `delete`), timestamp, legal basis.
2. Verify identity with approved procedure; do not use bot chat alone as strong identity proof.
3. Define scope: tenant, customer profile(s), date range, related records.
4. Obtain explicit approval before any destructive action.

## Export procedure (manual, controlled)

1. Operator works in staging/test copy or approved controlled prod access window.
2. Locate records by tenant + verified identifiers using approved DB query/process.
3. Export minimum necessary fields; encrypt export file at rest; transfer via approved secure channel.
4. Record ticket ID, operator, timestamp, data scope, destination, retention of export artifact.
5. Delete temporary export artifacts after delivery per policy.

## Deletion/anonymization procedure (manual, controlled)

1. Confirm legal basis allows deletion/anonymization; some booking/accounting records may require retention.
2. Prefer **anonymization/tombstone** where business integrity/FK constraints require records to exist.
3. For `customer_profiles`: remove/overwrite PII fields, keep non-PII technical keys only if required; document rationale.
4. Do not delete `outbox`/`sync_log`/audit records blindly; apply retention policies and legal hold rules.
5. Verify application behavior after anonymization on staging first when possible.
6. Record evidence: SQL/scripts used, rows affected, backup reference, approver, operator, timestamp.

## Key rotation / re-encrypt (separate technical increment)

- Current limitation: `APP_SECRET_KEY` rotation and re-encrypt migration are **not implemented**.
- Required before pilot: `key_id` versioning, batch re-encrypt job, dry-run, rollback plan, KMS/secret manager storage.
- If key compromise suspected: incident response, rotate secrets, assess blast radius, legal/comms per policy.

## Audit & safety

- Never paste raw PII/secrets into tickets, logs, or chat.
- Keep evidence in secure approved storage.
- All manual DB actions require backup/restore point and peer review.
- Use `*_test`/staging for rehearsal; production only with approved change window.

## Ticket template

- Request ID:
- Tenant slug:
- Type: export/delete/anonymize
- Requester identity verified by:
- Legal basis/approval:
- Scope:
- Backup/restore point:
- Operator:
- Execution time:
- Rows affected/evidence:
- Artifacts deleted:
- Close-out reviewer:
