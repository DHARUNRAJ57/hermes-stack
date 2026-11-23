"""Checks for the Hermes + Cognee stack. Run from this folder while the stack is up.

    python smoke_test.py            connections: memory tools, Hermes health and key
    python smoke_test.py --memory   also save a marker with remember and find it with recall
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

MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8001/mcp")
HERMES_BASE = os.environ.get("HERMES_BASE", "http://127.0.0.1:8642")
MEMORY_TOOLS = {"remember", "recall", "forget"}
DATASET = "hermes_shared"


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


async def call(session: ClientSession, name: str, arguments: dict) -> tuple[bool, str]:
    result = await session.call_tool(name, arguments)
    text = result_text(result)
    return (not result.isError and not text.startswith("Error")), text


async def check_memory(report: Report, deep: bool) -> None:
    try:
        async with streamablehttp_client(MEMORY_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                missing = MEMORY_TOOLS - names
                if missing:
                    report.fail("shared memory tools", f"missing {sorted(missing)}")
                else:
                    report.ok("shared memory tools", ", ".join(sorted(MEMORY_TOOLS)) + f"  ({MEMORY_URL})")

                if deep:
                    marker = f"stack-smoke-{uuid.uuid4().hex[:12]}"
                    ok, text = await call(session, "remember", {"data": f"Smoke test marker {marker}.", "dataset_name": DATASET})
                    if not ok:
                        report.fail("remember", text[:300])
                    else:
                        report.ok("remember", "saved")
                        ok, found = await call(session, "recall", {"query": f"smoke test marker {marker}", "datasets": DATASET})
                        if ok and marker in found:
                            report.ok("recall round trip", "marker found")
                        else:
                            report.warn("recall round trip", "marker not found yet. Check again after indexing finishes.")
    except Exception as exc:  # noqa: BLE001 - any connection problem is a reported check
        report.fail("shared memory connection", f"{type(exc).__name__}: {exc}")


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
    parser.add_argument("--memory", action="store_true", help="save a marker with remember and find it with recall")
    parser.add_argument("--chat", action="store_true", help="send one request to Hermes")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
