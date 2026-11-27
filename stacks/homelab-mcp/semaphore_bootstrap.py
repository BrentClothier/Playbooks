"""Create-only bootstrap for the fresh native Semaphore instance."""
import asyncio
import json
import os
from urllib.parse import urlsplit

import httpx

PROJECT = "HomeLab TrueNAS Operations"
REPO = "https://github.com/BrentClothier/Playbooks.git"
SMOKE = "scripts/truenas/semaphore_smoke.py"
LOCK = asyncio.Lock()


def _settings():
    if os.getenv("SEMAPHORE_BOOTSTRAP_ENABLED") != "true":
        raise ValueError("Semaphore bootstrap disabled.")
    url = os.getenv("SEMAPHORE_URL", "").rstrip("/")
    token = os.getenv("SEMAPHORE_API_TOKEN", "")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            not parsed.hostname.endswith(".ts.net") or parsed.port != 8443 or
            parsed.username is not None or parsed.password is not None or
            parsed.path or parsed.query or parsed.fragment or not token or
            os.getenv("SEMAPHORE_VERIFY_SSL", "true").lower() not in {"true", "1", "yes", "on"}):
        raise ValueError("Expected verified private Semaphore HTTPS endpoint on port 8443.")
    if os.getenv("SEMAPHORE_ALLOWED_TEMPLATES", "").strip():
        raise ValueError("Disable task execution allowlist during bootstrap.")
    return url, token


async def _request(client, method, path, payload=None):
    try:
        response = await client.request(method, path, json=payload,
            params={"sort": "name", "order": "asc"} if method == "GET" else None)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        # No upstream body, private URL, credentials or request fields.
        raise RuntimeError("Semaphore bootstrap request failed; inspect server and rerun only after checking inventory.") from None


def _rows(value):
    # Empty Go slices can serialize as null. Successful HTTP JSON only.
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise RuntimeError("Unexpected Semaphore collection response.")
    return value


def _id(row):
    ident = row.get("id")
    if type(ident) is not int or ident < 1:
        raise RuntimeError("Unexpected Semaphore resource identifier.")
    return ident


def _find(rows, name):
    matches = [r for r in rows if r.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError("Duplicate bootstrap resource; no changes made to it.")
    return matches[0] if matches else None


async def _ensure(client, path, payload, compare):
    row = _find(_rows(await _request(client, "GET", path)), payload["name"])
    created = row is None
    if created:
        await _request(client, "POST", path, payload)
        row = _find(_rows(await _request(client, "GET", path)), payload["name"])
    if row is None or not compare(row):
        raise RuntimeError("Bootstrap resource missing or differs from reviewed configuration; no overwrite.")
    return {"id": _id(row), "created": created}


def _matches(row, expected):
    return all(row.get(k) == v for k, v in expected.items())


async def _bootstrap(client):
    projects = _rows(await _request(client, "GET", "/projects"))
    if any(p.get("name") != PROJECT for p in projects):
        raise ValueError("Unexpected projects on target; bootstrap is restricted to the fresh instance.")
    project = await _ensure(client, "/projects",
        {"name": PROJECT, "alert": False, "max_parallel_tasks": 1, "demo": False, "type": ""},
        lambda r: r.get("name") == PROJECT)
    pid = project["id"]
    prefix = f"/project/{pid}"
    key = await _ensure(client, prefix + "/keys",
        {"name": "Public Git - no credentials", "type": "none", "project_id": pid},
        lambda r: _matches(r, {"type": "none", "project_id": pid}) and not r.get("source_storage_type"))
    repo_fields = {"project_id": pid, "git_url": REPO, "git_branch": "main",
                   "ssh_key_id": key["id"], "monorepo": False}
    repo = await _ensure(client, prefix + "/repositories",
        {"name": "HomeLab Playbooks", **repo_fields}, lambda r: _matches(r, repo_fields))
    env_fields = {"project_id": pid, "json": "{}", "env": "{}"}
    env = await _ensure(client, prefix + "/environment",
        {"name": "Empty - no credentials", **env_fields},
        lambda r: r.get("project_id") == pid and json.loads(r.get("json") or "{}") == {}
        and json.loads(r.get("env") or "{}") == {} and not r.get("secrets")
        and not r.get("secret_storage_id") and not r.get("sync_enabled"))
    fields = {"project_id": pid, "repository_id": repo["id"], "environment_ids": [env["id"]],
              "playbook": SMOKE, "app": "python", "arguments": "[]",
              "git_branch": "main"}
    def matches_template(r):
        return (_matches(r, fields) and not r.get("inventory_id")
                and not any(r.get(k) for k in ("autorun", "allow_override_args_in_task",
                     "allow_override_branch_in_task", "survey_vars", "vaults",
                     "runner_tag", "executor_image", "working_directory", "build_template_id", "jwt_params")))
    smoke = await _ensure(client, prefix + "/templates",
        {"name": "HomeLab Runner Smoke Test", **fields, "autorun": False,
         "allow_override_args_in_task": False, "allow_override_branch_in_task": False,
         "description": "No host access or credentials; print runner marker only.",
         "task_params": {}}, matches_template)
    return {"project": project, "repository": repo, "no_auth_key": key,
            "empty_variable_group": env, "smoke_template": smoke,
            "execution_enabled": False,
            "coverage": "Create-only bootstrap; no TrueNAS host inventory, credentials, backups or execution."}


async def bootstrap(confirmation):
    if confirmation != "bootstrap:homelab-truenas-operations":
        raise ValueError("Exact bootstrap confirmation required.")
    url, token = _settings()
    async with LOCK:
        async with httpx.AsyncClient(base_url=url + "/api",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                verify=True, follow_redirects=False, trust_env=False,
                timeout=10) as client:
            return await _bootstrap(client)


async def prepare_backups(confirmation):
    from semaphore_policy import native_endpoint, parse, template_safe
    if confirmation != "prepare:homelab-backup-templates":
        raise ValueError("Exact backup template confirmation required.")
    url = os.getenv("SEMAPHORE_URL", "").rstrip("/")
    token = os.getenv("SEMAPHORE_API_TOKEN", "")
    verify = os.getenv("SEMAPHORE_VERIFY_SSL", "true").lower() in {"true", "1", "yes", "on"}
    if not token or not native_endpoint(url, verify):
        raise ValueError("Expected native verified HTTPS endpoint.")
    all_allowed, pairs, scoped = parse(os.getenv("SEMAPHORE_ALLOWED_TEMPLATES", ""))
    if all_allowed or len(scoped) != 1:
        raise ValueError("Expected one dedicated project scope, not a global wildcard.")
    pid = next(iter(scoped))
    prefix = f"/project/{pid}"
    async with LOCK:
        async with httpx.AsyncClient(base_url=url + "/api",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                verify=True, follow_redirects=False, trust_env=False, timeout=10) as client:
            project = await _request(client, "GET", prefix + "/")
            if not _matches(project, {"id": pid, "name": PROJECT}):
                raise ValueError("Unexpected project.")
            repo = _find(_rows(await _request(client, "GET", prefix + "/repositories")), "HomeLab Playbooks")
            if not repo or not _matches(repo, {"project_id": pid, "git_url": REPO, "git_branch": "main", "monorepo": False}):
                raise ValueError("Reviewed repository not found.")
            key = _find(_rows(await _request(client, "GET", prefix + "/keys")), "Public Git - no credentials")
            if not key or key.get("type") != "none" or _id(key) != repo.get("ssh_key_id") or key.get("source_storage_type"):
                raise ValueError("Expected no-auth Git key.")
            groups = _rows(await _request(client, "GET", prefix + "/environment"))
            desired = []
            for operation in ("verify", "restore"):
                group = _find(groups, "TrueNAS Backup " + operation.capitalize())
                if not group or group.get("project_id") != pid:
                    raise ValueError("Owner must create both private backup variable groups first.")
                desired.append((operation, _id(group)))
            if desired[0][1] == desired[1][1]:
                raise ValueError("Distinct variable groups required.")
            results = {}
            for operation, eid in desired:
                fields = {"project_id": pid, "repository_id": _id(repo), "environment_ids": [eid],
                          "playbook": "scripts/truenas/semaphore_backup.py", "app": "python",
                          "arguments": "[]", "git_branch": "main"}
                def compare(row):
                    template_safe(row, pid, _id(row))
                    return (_matches(row, fields) and not any(row.get(k) for k in
                        ("inventory_id", "vaults", "runner_tag", "executor_image",
                         "working_directory", "build_template_id")))
                results[operation] = await _ensure(client, prefix + "/templates",
                    {"name": "TrueNAS Backup " + operation.capitalize(), **fields,
                     "autorun": False, "allow_override_args_in_task": False,
                     "allow_override_branch_in_task": False, "task_params": {}}, compare)
            return {"project_id": pid, "templates": results,
                    "coverage": "Template metadata only; owner-provisioned keys and host restrictions not verified. No tasks started."}


def register(mcp):
    @mcp.tool
    async def semaphore_bootstrap_truenas(confirmation: str):
        """Create only the fresh native HomeLab project, public Git repository, no-auth key, empty variable group and credential-free smoke template. Confirm bootstrap:homelab-truenas-operations. No task execution, host credentials or updates."""
        return await bootstrap(confirmation)

    @mcp.tool
    async def semaphore_prepare_backup_templates(confirmation: str):
        """Create two fixed backup templates after owner installs restricted runner and private variable groups. Confirm prepare:homelab-backup-templates. No execution."""
        return await prepare_backups(confirmation)
