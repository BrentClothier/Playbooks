# ADR 0003: Isolate Independent Project IaC State

Status: Accepted

## Context

Adding the Humboldt VM to the original HomeLab OpenTofu root produced a plan containing unrelated changes to existing workloads.

## Decision

Projects with independent lifecycle and risk should receive a dedicated OpenTofu root/state.

The Humboldt platform therefore lives under:

`opentofu/humboldt/`

and must be planned/applied independently from the original root.

## Consequence

Automation templates must point to the project-specific root. A generic root apply is not an acceptable substitute.
