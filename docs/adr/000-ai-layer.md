# ADR 000: AI layer architecture and P0 scope

- **Status:** Accepted for P0 scope; implementation decisions remain open where noted.
- **Date:** 2026-10-27

## Context

The platform already provides a medallion data pipeline (bronze, silver, and gold) and an optional AI package under `src/vnecom/ai`. The AI package is organized into domain, application, infrastructure, interfaces, agents, and pipelines. Its domain ports and entities are framework-independent; provider and interface integrations are kept at the edges. Existing AI use cases beyond basic text generation are placeholders.

The project has optional dependencies for several AI capabilities, but dependency availability is not itself an architecture decision. P0 should establish the boundary and record the decisions deliberately deferred, without claiming retrieval, orchestration, evaluation, or deployment behavior that is not implemented or otherwise specified.

## Decision

For P0, treat the AI layer as an optional capability within the existing `vnecom` project. Preserve the separation between framework-independent domain/application code and replaceable infrastructure/interface adapters. AI functionality must not become a prerequisite for the existing data platform or alter its bronze/silver/gold responsibilities.

P0 establishes this boundary and decision process only. It does **not** select a vector store, agent framework, embedding provider/model, text-to-SQL policy, or entity-resolution method. Those choices require the planned ADRs below. No production retrieval or agent behavior is implied by this ADR.

## Consequences

- Existing non-AI workflows remain independent of optional AI dependencies and services.
- Future AI integrations should enter through explicit ports/adapters rather than coupling domain logic to a provider or framework.
- The five unresolved design choices are tracked in the [ADR index](README.md); their status is planned, not decided.
- This ADR does not prescribe infrastructure, data flows, schemas, model quality targets, or rollout details beyond the stated P0 boundary.

## Planned decisions

See the [ADR index](README.md) for the five planned decision records and their current status.
