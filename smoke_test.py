"""Checks for the Hermes + Hindsight stack. Run from this folder while the stack is up.

    python smoke_test.py            connections: Hindsight tools, Hermes health and key
    python smoke_test.py --memory   also save a marker with retain and find it with recall
    python smoke_test.py --chat     also send one request to Hermes

Needs: pip install mcp httpx   (once, on this PC)
Exit code 0 means every check passed. 1 means at least one failed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8888/mcp/hermes/")
HERMES_BASE = os.environ.get("HERMES_BASE", "http://127.0.0.1:8642")
MEMORY_TOOLS = {"retain", "recall"}


def read_env_value(name: str) -> str:
    """Read one value from .env in this folder. The value is never printed."""
    value = os.environ.get(name, "")
    if value:
        return value
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return ""


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, name: str, detail: str = "") -> None:
        print(f"PASS  {name}" + (f" - {detail}" if detail else ""))

    def warn(self, name: str, detail: str = "") -> None:
        print(f"WARN  {name}" + (f" - {detail}" if detail else ""))

    def fail(self, name: str, detail: str = "") -> None:
        self.failures += 1
        print(f"FAIL  {name}" + (f" - {detail}" if detail else ""))


def result_text(result) -> str:
    return "\n".join(part.text for part in result.content if getattr(part, "type", None) == "text")


def text_arg(tool, value: str) -> dict:
    """Build the arguments for a tool from its own schema: the first required text field gets the value."""
    schema = getattr(tool, "inputSchema", None) or {}
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []
    names = [n for n in required if (props.get(n) or {}).get("type") == "string"] or [
        n for n, p in props.items() if (p or {}).get("type") == "string"
    ]
    return {names[0] if names else "content": value}


async def check_memory(report: Report, deep: bool) -> None:
    try:
        async with streamablehttp_client(MEMORY_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                missing = MEMORY_TOOLS - set(tools)
                if missing:
                    report.fail("Hindsight memory tools", f"missing {sorted(missing)}")
                else:
                    report.ok("Hindsight memory tools", f"{len(tools)} tools  ({MEMORY_URL})")

                if deep and not missing:
                    marker = f"stack-smoke-{uuid.uuid4().hex[:12]}"
                    saved = await session.call_tool("retain", text_arg(tools["retain"], f"Smoke test marker {marker}."))
                    saved_text = result_text(saved)
                    if saved.isError or saved_text.startswith("Error"):
                        report.fail("retain", saved_text[:300])
                    else:
                        report.ok("retain", "saved")
                        found = await session.call_tool("recall", text_arg(tools["recall"], f"smoke test marker {marker}"))
                        found_text = result_text(found)
                        if not found.isError and marker in found_text:
                            report.ok("recall round trip", "marker found")
                        else:
                            report.warn("recall round trip", "marker not found yet. Check again after indexing finishes.")
    except Exception as exc:  # noqa: BLE001 - any connection problem is a reported check
        report.fail("Hindsight connection", f"{type(exc).__name__}: {exc}")


async def check_hermes(report: Report, chat: bool) -> None:
    key = read_env_value("HERMES_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            health = await client.get(f"{HERMES_BASE}/health")
            if health.status_code == 200:
                report.ok("Hermes /health", HERMES_BASE)
            else:
                report.fail("Hermes /health", f"HTTP {health.status_code}")
            if not key:
                report.fail("Hermes key", "HERMES_API_KEY not found in .env")
                return
            models = await client.get(f"{HERMES_BASE}/v1/models", headers={"Authorization": f"Bearer {key}"})
            if models.status_code == 200:
                report.ok("Hermes API key", "accepted")
            else:
                report.fail("Hermes API key", f"HTTP {models.status_code}. The key must match HERMES_API_KEY in .env.")
                return
            if chat:
                payload = {"model": "hermes-agent", "messages": [{"role": "user", "content": "Reply with the single word OK."}], "stream": False}
                reply = await client.post(f"{HERMES_BASE}/v1/chat/completions", json=payload, headers={"Authorization": f"Bearer {key}"})
                data = reply.json() if reply.status_code == 200 else {}
                choice = (data.get("choices") or [{}])[0]
                if reply.status_code == 200 and choice.get("finish_reason") != "error" and not (data.get("hermes") or {}).get("failed"):
                    report.ok("Hermes chat", str((choice.get("message") or {}).get("content", ""))[:80].replace("\n", " "))
                else:
                    detail = (data.get("hermes") or {}).get("error") or f"HTTP {reply.status_code}"
                    report.fail("Hermes chat", str(detail)[:300])
    except httpx.HTTPError as exc:
        report.fail("Hermes API", f"{type(exc).__name__}: {exc}")


async def run(args: argparse.Namespace) -> int:
    report = Report()
    await check_memory(report, deep=args.memory)
    await check_hermes(report, chat=args.chat)
    print()
    if report.failures:
        print(f"{report.failures} check(s) failed. See README.md, Troubleshooting.")
        return 1
    print("All checks passed.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--memory", action="store_true", help="save a marker with retain and find it with recall")
    parser.add_argument("--chat", action="store_true", help="send one request to Hermes")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
