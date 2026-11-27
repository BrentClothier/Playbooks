"""Semaphore scope parsing and native project guard."""
import re
from urllib.parse import urlsplit

PROJECT = "HomeLab TrueNAS Operations"


def parse(raw):
    raw = raw.strip()
    if raw == "*":
        return True, set(), set()
    pairs, projects = set(), set()
    if not raw:
        return False, pairs, projects
    for item in raw.split(","):
        m = re.fullmatch(r"([1-9][0-9]{0,9}):([1-9][0-9]{0,9}|\*)", item.strip())
        if not m:
            raise ValueError("Invalid Semaphore scope; use project:template or project:*.")
        pid, tid = m.groups()
        if tid == "*":
            projects.add(int(pid))
        else:
            pairs.add((int(pid), int(tid)))
    return False, pairs, projects


def native_endpoint(url, verify):
    p = urlsplit(url)
    return (verify and p.scheme == "https" and p.hostname and
            p.hostname.endswith(".ts.net") and p.port == 8443 and
            p.username is None and p.password is None and
            not (p.path or p.query or p.fragment))


async def verify_project(get, pid, url, verify):
    if not native_endpoint(url, verify):
        raise PermissionError("Project-wide scope requires native private HTTPS endpoint.")
    row = await get(f"/project/{pid}/")
    if not isinstance(row, dict) or row.get("id") != pid or row.get("name") != PROJECT:
        raise PermissionError("Project-wide scope limited to the dedicated native HomeLab project.")


def template_safe(row, pid, tid):
    if (not isinstance(row, dict) or row.get("id") != tid or row.get("project_id") != pid or
            any(row.get(k) for k in ("autorun", "allow_override_args_in_task",
                "allow_override_branch_in_task", "survey_vars", "jwt_params", "allow_parallel_tasks"))):
        raise PermissionError("Template identity or fixed-execution settings not verified.")
    params = row.get("task_params") or {}
    if not isinstance(params, dict) or any(v for k,v in params.items() if k.startswith("allow_override")):
        raise PermissionError("Template permits execution overrides.")


async def authorize(get, raw, pid, tid, url, verify):
    all_allowed, pairs, projects = parse(raw)
    if type(pid) is not int or type(tid) is not int or min(pid, tid) < 1:
        raise PermissionError("Invalid Semaphore target.")
    if not all_allowed and (pid, tid) not in pairs and pid not in projects:
        raise PermissionError("Semaphore template is not allowlisted.")
    if pid in projects:
        await verify_project(get, pid, url, verify)
    row = await get(f"/project/{pid}/templates/{tid}")
    if pid in projects:
        template_safe(row, pid, tid)
    elif not isinstance(row, dict) or row.get("id") != tid or row.get("project_id") != pid:
        raise PermissionError("Template identity not verified.")
    return row
