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


## ChatGPT action refresh

ChatGPT workspaces keep a frozen snapshot of an approved custom MCP app's
available tools and input schemas. Adding tools to the live HomeLab MCP server
does not automatically add those actions to an already approved ChatGPT app.

After adding or changing MCP tools:

1. verify the new HomeLab MCP image is deployed and healthy;
2. in ChatGPT Workspace settings, open Apps and locate the HomeLab/TestApp app;
3. open Action control and choose Refresh to scan the live MCP server;
4. review the diff and enable the new read-only actions as appropriate;
5. publish/save the updated action set if the workspace UI requires it;
6. start a new chat and verify the new actions are visible.

For a draft/developer app, use its manage/edit flow and rescan tools rather
than assuming a new chat will refresh the action schema.

This refresh requirement is a ChatGPT app-registration concern, not a reason to
redeploy the HomeLab MCP again when the live server already exposes the tools.
