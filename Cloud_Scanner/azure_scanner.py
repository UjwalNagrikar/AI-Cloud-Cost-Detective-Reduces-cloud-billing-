import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator


class AzureCliError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _find_az() -> str:
    """
    Locate Azure CLI executable on Windows/Linux/macOS.
    Raises AzureCliError if not found.
    """
    candidates = [
        shutil.which("az"),
        shutil.which("az.cmd"),
        r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise AzureCliError(
        "Azure CLI is not installed or cannot be found. "
        "Install it from https://aka.ms/installazurecli and run 'az login'.",
        status_code=503,
    )


# ── Lazy singleton: resolved only on first actual CLI call ─────────────────────
_AZ_EXECUTABLE: str | None = None


def _get_az() -> str:
    """Return the cached Azure CLI path, resolving it lazily on first call."""
    global _AZ_EXECUTABLE
    if _AZ_EXECUTABLE is None:
        _AZ_EXECUTABLE = _find_az()
    return _AZ_EXECUTABLE


def _run_az(command: list[str], timeout: int = 120) -> Any:
    """
    Execute an Azure CLI command and return parsed JSON output.
    The first element must be 'az'; it is replaced with the resolved executable.
    """
    az = _get_az()
    if command and command[0].lower() == "az":
        command = [az, *command[1:]]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AzureCliError("Azure CLI command timed out.", status_code=504) from exc
    except FileNotFoundError as exc:
        raise AzureCliError(
            f"Azure CLI executable not found: {az}", status_code=503
        ) from exc

    if result.returncode != 0:
        error = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Unknown Azure CLI error."
        )
        raise AzureCliError(error)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AzureCliError("Azure CLI returned invalid JSON.") from exc


def _chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ── Public API ─────────────────────────────────────────────────────────────────

def list_resource_groups() -> list[dict[str, str | None]]:
    """Return a list of Azure resource groups (name + location)."""
    groups = _run_az(["az", "group", "list", "--output", "json"])
    return [
        {
            "name": group.get("name"),
            "location": group.get("location"),
        }
        for group in groups
        if group.get("name")
    ]


def _fetch_full_details(resource_ids: list[str], batch_size: int = 20) -> dict[str, dict[str, Any]]:
    """
    `az resource list` only returns shallow metadata -- properties, sku, kind
    and managedBy come back empty for most resource types. This fetches the
    full detail (including managedBy, which tells you whether a disk is
    actually attached to a VM) for every resource ID, in batches to avoid
    command-line length limits and to keep the request count reasonable for
    large resource groups.

    If a batch call fails (e.g. one bad ID in the batch), falls back to
    fetching that batch one ID at a time rather than losing the whole batch.
    """
    detail_by_id: dict[str, dict[str, Any]] = {}
    if not resource_ids:
        return detail_by_id

    for batch in _chunked(resource_ids, batch_size):
        try:
            details = _run_az(["az", "resource", "show", "--ids", *batch, "--output", "json"])
        except AzureCliError:
            details = []
            for single_id in batch:
                try:
                    d = _run_az(["az", "resource", "show", "--ids", single_id, "--output", "json"])
                    details.append(d)
                except AzureCliError:
                    # Permissions issue, deleted-mid-scan, or unsupported type.
                    # Skip it -- the shallow record from `resource list` is
                    # still used as a fallback so the resource isn't dropped.
                    continue

        if isinstance(details, dict):
            details = [details]

        for d in details or []:
            if isinstance(d, dict) and d.get("id"):
                detail_by_id[d["id"]] = d

    return detail_by_id


def scan_resource_group(resource_group: str) -> list[dict[str, Any]]:
    """
    List every resource inside *resource_group* -- no type filter, so this
    covers VMs, disks, NICs, public IPs, storage accounts, App Services,
    SQL databases, load balancers, and anything else Azure has in the RG --
    then enriches each one with full detail (sku, kind, properties, and
    managedBy) via `az resource show`.

    Each returned dict contains at minimum:
        name, type, location, resource_group, sku, kind, tags,
        properties, managed_by
    """
    shallow = _run_az(
        [
            "az", "resource", "list",
            "--resource-group", resource_group,
            "--output", "json",
        ]
    )

    if not isinstance(shallow, list):
        raise AzureCliError(
            f"Unexpected response while scanning resource group '{resource_group}'."
        )

    resource_ids = [r.get("id") for r in shallow if isinstance(r, dict) and r.get("id")]
    detail_by_id = _fetch_full_details(resource_ids)

    normalised: list[dict[str, Any]] = []
    for res in shallow:
        if not isinstance(res, dict):
            continue

        detail = detail_by_id.get(res.get("id"), {})
        # Full detail wins where available; shallow record fills any gaps.
        merged = {**res, **detail}

        normalised.append(
            {
                "name": merged.get("name") or "unknown",
                "type": merged.get("type") or "unknown",
                "location": merged.get("location") or "unknown",
                "resource_group": merged.get("resourceGroup") or resource_group,
                "sku": merged.get("sku"),
                "kind": merged.get("kind"),
                "tags": merged.get("tags") or {},
                "properties": merged.get("properties") or {},
                "managed_by": merged.get("managedBy"),  # e.g. VM ID a disk is attached to, or None
            }
        )

    return normalised