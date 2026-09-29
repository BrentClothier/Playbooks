# Model Access to the HomeLab Knowledge Base

## Problem

Putting documentation in Git is not enough by itself. A model does not
automatically know that it should open a particular repository path, and model
memory should not be treated as the durable source of HomeLab operating intent.

## Retrieval contract

The HomeLab MCP advertises server instructions that tell compatible clients to
consult the KB when a task depends on:

- architecture intent;
- migration state;
- safety rules;
- known exceptions;
- storage/backup policy;
- prior incidents;
- project history.

The MCP exposes three read-only tools:

- `homelab_kb_index` - discover allowlisted documents;
- `homelab_kb_search` - search the KB for task-relevant context;
- `homelab_kb_read` - read a specific document.

The tools fetch current public-safe content from
`BrentClothier/Playbooks/docs/homelab`, so normal KB edits do not require
rebuilding the MCP image.

## Authority rule

Use the two information planes differently:

- **Live APIs:** what is running, healthy, stopped, using resources, or failing now.
- **Knowledge base:** why the environment is designed a certain way, what the target state is, and which operational constraints must be preserved.

When they conflict about runtime state, prefer live APIs. When a live API does
not explain intent, consult the KB rather than guessing.

## Security

The KB is public-safe and is not a secret store. Models must not expect it to
contain credentials or request that secret values be added for convenience.
