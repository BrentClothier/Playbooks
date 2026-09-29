# ADR 0002: Guard Portainer Git Redeploys

Status: Accepted

## Context

An earlier Portainer automation path caused stack environment metadata to be lost. A repair attempt using a generic stack update with an empty Env array compounded the problem.

## Decision

Automated Git-backed redeploys must:

- use the dedicated Git redeploy endpoint;
- run only against explicitly tested Portainer versions;
- validate Git metadata and environment structure;
- omit Env from the redeploy request so existing values are preserved;
- verify metadata after the call;
- refuse HomeLab MCP self-redeployment;
- treat asynchronous deployment completion separately from API acceptance.

## Validation

The revised path was tested on Portainer 2.45.1 using the `family-archive` Git-backed stack. The deployment completed with 18 environment variables and Git metadata preserved.

## Consequence

Portainer upgrades may require re-validating API semantics before automated redeploys are enabled for the new version.
