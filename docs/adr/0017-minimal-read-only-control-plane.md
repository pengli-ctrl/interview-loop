# ADR-017: Minimal Read-Only Control Plane

## Status

Accepted

## Context

The platform has enough runtime primitives to demonstrate agent architecture, but candidates and operators need different surfaces. Exposing internal model, tool and trace data in the interview workflow would increase cognitive load and disclosure risk.

## Decision

Add a local admin mode controlled by `admin_mode`:

- candidate navigation remains unchanged when admin mode is disabled;
- direct access to the admin view redirects to the dashboard when disabled;
- admin mode adds a sixth read-only view;
- the view reads the same scenario registry, model gateway, tool registry, SQLite AgentRuns and evaluation datasets used by runtime services;
- no destructive or production configuration mutation is allowed.

## Consequences

Positive:

- demonstrates a platform control plane without adding microservices;
- separates candidate experience from operator diagnostics;
- administrators can inspect actual routing, tools, traces and evaluation health;
- visibility is controlled by an explicit local switch.

Negative:

- the switch is local configuration, not production SSO/RBAC;
- editing scenario, model and quota settings is deferred;
- SQLite and process-local quotas limit multi-user administration.

## Follow-up

Replace local admin mode with OIDC/RBAC, add audited configuration changes, and move data access to tenant-scoped production APIs.
