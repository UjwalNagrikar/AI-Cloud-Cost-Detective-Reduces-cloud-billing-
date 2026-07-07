"""
AI-powered cost analysis for Azure resources.
================================================
Scans every resource inside a chosen resource group and returns a
complete verdict for each one: local deterministic rules first
(fast, free, no API call), then LLM for everything that needs
deeper judgement. Every resource gets an entry in the final report --
including a "no action needed" entry for healthy resources -- so the
output is a full picture of the resource group, not just a list of
problems.
"""
import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Pointing to Groq API using your gsk_ key
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)


SYSTEM_PROMPT = """
You are an expert Azure Cloud FinOps Analyst.

The user will provide a JSON list of Azure resources belonging to a single
resource group. Analyze EVERY resource in the list -- do not skip any --
for cost optimization opportunities (e.g. wrong VM tier, overprovisioned
SQL, unused App Services, idle App Service Plans, oversized storage
accounts, orphaned load balancers, etc.).

You MUST return exactly one entry per resource provided, in the same order.
If a resource looks correctly sized and there is no meaningful savings
opportunity, still include it with severity "none" and a solution field
that says why it's fine (e.g. "Right-sized for observed usage; no action
needed.").

Return ONLY valid JSON in this exact format:
{
  "issues": [
    {
      "resource_name": "string",
      "resource_type": "string",
      "resource_group": "string",
      "issue": "string (use 'No issue detected' if healthy)",
      "suggestion": "string",
      "severity": "high" | "medium" | "low" | "none",
      "estimated_monthly_savings": "string (use '$0.00' if none)",
      "solution": "Detailed plain-text explanation of how to optimize this specific resource, or why no action is needed."
    }
  ],
  "estimated_savings": {
    "monthly": 0.00,
    "yearly": 0.00,
    "currency": "USD"
  }
}
"""


def _local_rule_check(resource: dict[str, Any]) -> dict[str, Any] | None:
    """
    Deterministic, zero-cost checks for resource types we can reason
    about confidently without an LLM call. Returns an issue dict, or
    None if this resource type isn't covered by a local rule.
    """
    resource_type = resource.get("type", "")
    name = resource.get("name", "unknown")
    resource_group = resource.get("resource_group", "")

    if resource_type == "Microsoft.Compute/disks":
        managed_by = resource.get("managed_by")
        if not managed_by:
            return {
                "resource_name": name,
                "resource_type": resource_type,
                "resource_group": resource_group,
                "issue": "Unattached Managed Disk (confirmed via managedBy)",
                "suggestion": "This disk is not attached to any VM and is still incurring storage charges.",
                "severity": "high",
                "estimated_monthly_savings": "$5-50/month (depends on SKU and size)",
                "solution": (
                    "If you no longer need this data, delete the disk. If you need to "
                    "keep it for later, take a low-cost Snapshot and delete the disk -- "
                    "that is the cheapest way to retain the data. If it must stay as a "
                    "disk, downgrade its SKU from Premium SSD to Standard HDD to cut "
                    "storage costs by up to 60%."
                ),
                "_monthly_savings_value": 15.0,
            }
        return {
            "resource_name": name,
            "resource_type": resource_type,
            "resource_group": resource_group,
            "issue": "No issue detected",
            "suggestion": f"Disk is attached to {managed_by.split('/')[-1]}; no action needed.",
            "severity": "none",
            "estimated_monthly_savings": "$0.00",
            "solution": (
                "Disk is actively attached to a VM. If cost is still a concern, check "
                "whether its SKU tier (Premium vs Standard) matches the actual IOPS "
                "needs of the workload."
            ),
            "_monthly_savings_value": 0.0,
        }

    if resource_type == "Microsoft.Network/publicIPAddresses":
        properties = resource.get("properties") or {}
        sku = resource.get("sku") or {}
        sku_name = (sku.get("name") or "Basic").lower()
        allocation_method = (properties.get("publicIPAllocationMethod") or "Dynamic").lower()
        is_attached = bool(properties.get("ipConfiguration"))

        if is_attached:
            return {
                "resource_name": name,
                "resource_type": resource_type,
                "resource_group": resource_group,
                "issue": "No issue detected",
                "suggestion": "IP is attached to an active NIC/Load Balancer; no waste here.",
                "severity": "none",
                "estimated_monthly_savings": "$0.00",
                "solution": (
                    f"In use (SKU: {sku.get('name', 'Basic')}). If this doesn't need "
                    "Standard-tier features (zone redundancy, NSG-by-default, Standard "
                    "Load Balancer pairing), downgrading to Basic SKU can reduce cost "
                    "slightly -- otherwise no action needed."
                ),
                "_monthly_savings_value": 0.0,
            }

        if sku_name == "standard":
            monthly_cost = 3.65
        elif allocation_method == "static":
            monthly_cost = 2.63
        else:
            monthly_cost = 0.0

        return {
            "resource_name": name,
            "resource_type": resource_type,
            "resource_group": resource_group,
            "issue": "Unassociated Public IP (confirmed via ipConfiguration)",
            "suggestion": "This IP is not attached to any NIC or Load Balancer and is idle.",
            "severity": "high" if monthly_cost > 0 else "low",
            "estimated_monthly_savings": f"${monthly_cost:.2f}/month" if monthly_cost > 0 else "$0.00 (not currently billed, but unused)",
            "solution": (
                "Azure does not allow pausing billing on an allocated Public IP. If you "
                "don't need this exact address, delete it. If you'll need 'an IP' again "
                "later, let Azure assign a new one dynamically for free rather than "
                "reserving this one."
            ),
            "_monthly_savings_value": monthly_cost,
        }


def _fallback_entry(resource: dict[str, Any]) -> dict[str, Any]:
    """Used only if GPT's response drops a resource we sent it."""
    return {
        "resource_name": resource.get("name", "unknown"),
        "resource_type": resource.get("type", ""),
        "resource_group": resource.get("resource_group", ""),
        "issue": "Not returned by AI analysis",
        "suggestion": "Re-run analysis or review this resource manually.",
        "severity": "low",
        "estimated_monthly_savings": "$0.00",
        "solution": "The AI analysis step did not return a verdict for this resource; needs manual review.",
    }


def analyze_costs(
    resources: list[dict[str, Any]],
    resource_group: str | None = None,
) -> dict[str, Any]:
    """
    Analyze all resources in `resources`, optionally scoped to a single
    `resource_group`. Every resource gets exactly one entry in the
    returned `issues` list -- flagged, healthy, or "needs review" if the
    AI step failed to cover it.
    """
    if resource_group:
        resources = [r for r in resources if r.get("resource_group") == resource_group]

    issues: list[dict[str, Any]] = []
    total_monthly_savings = 0.0
    ai_resources: list[dict[str, Any]] = []

    for resource in resources:
        local_result = _local_rule_check(resource)
        if local_result is not None:
            total_monthly_savings += local_result.pop("_monthly_savings_value", 0.0)
            issues.append(local_result)
        else:
            ai_resources.append(resource)

    if ai_resources and client.api_key:
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", # Using Groq's fast model
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Analyze every one of these Azure resources for cost "
                            "optimization. Return one entry per resource, including "
                            "healthy ones:\n\n" + json.dumps(ai_resources, indent=2)
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            ai_result = json.loads(response.choices[0].message.content)
            ai_issues = ai_result.get("issues", [])
            issues.extend(ai_issues)

            savings = ai_result.get("estimated_savings", {})
            total_monthly_savings += savings.get("monthly", 0.0)

            # Safety net: make sure every resource we sent actually got a verdict back.
            returned_names = {i.get("resource_name") for i in ai_issues}
            for resource in ai_resources:
                if resource.get("name") not in returned_names:
                    issues.append(_fallback_entry(resource))

        except Exception as e:
            print(f"AI Analysis failed: {str(e)}")
            # Don't silently drop resources just because the API call failed.
            for resource in ai_resources:
                issues.append(_fallback_entry(resource))

    total_yearly_savings = total_monthly_savings * 12
    resources_with_issues = sum(
        1 for i in issues if i.get("severity") not in ("none", None)
    )

    return {
        "issues": issues,
        "estimated_savings": {
            "monthly": round(total_monthly_savings, 2),
            "yearly": round(total_yearly_savings, 2),
            "currency": "USD",
        },
        "summary": {
            "total_resources": len(resources),
            "resources_with_issues": resources_with_issues,
            "resources_healthy": len(resources) - resources_with_issues,
        },
    }