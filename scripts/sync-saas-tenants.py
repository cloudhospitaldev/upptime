#!/usr/bin/env python3
"""Regenerate the ch-saas tenant block in .upptimerc.yml from ch-infrastructure.

Reads ArgoCD tenant app values (k8s/argocd/apps/saas/prd/*/values.yaml), pulls
each ingress host, and rewrites the region between the BEGIN/END markers in
.upptimerc.yml. Manual platform entries above the markers are untouched.

Usage: python scripts/sync-saas-tenants.py <ch-infrastructure-dir>
"""
import glob
import os
import sys

import yaml

BEGIN = "  # === BEGIN ch-saas tenants (auto-generated — do not edit) ==="
END = "  # === END ch-saas tenants ==="
MAX_RESPONSE_TIME = 5000
MIN_EXPECTED = 150  # sanity floor; ~186 tenants live today

RC = os.path.join(os.path.dirname(__file__), "..", ".upptimerc.yml")


def collect_hosts(infra_dir):
    pattern = os.path.join(infra_dir, "k8s/argocd/apps/saas/prd/*/values.yaml")
    hosts = set()
    for path in glob.glob(pattern):
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        ingress = doc.get("ingress") or {}
        if ingress.get("enabled") is False:
            continue
        for entry in ingress.get("hosts") or []:
            host = (entry or {}).get("host")
            if host:
                hosts.add(host.strip())
    return sorted(hosts)


def build_block(hosts):
    lines = [BEGIN]
    for host in hosts:
        lines.append(f"  - name: {host}")
        lines.append(f"    url: https://{host}/api/healthz")
        lines.append(f"    maxResponseTime: {MAX_RESPONSE_TIME}")
    lines.append(END)
    return "\n".join(lines)


def splice(text, block):
    begin_i = text.index(BEGIN)
    end_i = text.index(END) + len(END)
    return text[:begin_i] + block + text[end_i:]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: sync-saas-tenants.py <ch-infrastructure-dir>")
    hosts = collect_hosts(sys.argv[1])
    if len(hosts) < MIN_EXPECTED:
        sys.exit(f"refusing: only {len(hosts)} hosts found (< {MIN_EXPECTED})")

    with open(RC) as f:
        text = f.read()
    if BEGIN not in text or END not in text:
        sys.exit(f"markers not found in {RC}; add them once under `sites:`")

    new_text = splice(text, build_block(hosts))

    # self-check: result must still be valid YAML with the tenants present
    parsed = yaml.safe_load(new_text)
    names = {s["name"] for s in parsed["sites"]}
    assert set(hosts) <= names, "generated hosts missing from parsed config"

    with open(RC, "w") as f:
        f.write(new_text)
    print(f"synced {len(hosts)} ch-saas tenants into {os.path.abspath(RC)}")


if __name__ == "__main__":
    main()
