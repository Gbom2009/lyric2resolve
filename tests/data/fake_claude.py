"""Fake `claude` CLI for tests: speaks the real stream-json event shapes (Claude Code 2.1.x).

Prompt (stdin) commands:
  "TOOL <name> <json-args>"  -> starts the MCP server from --mcp-config, calls the tool, reports it
  anything else              -> echoes "echo: <prompt>"
Env FAKE_CLAUDE_MODE: login | limit | nosession (fails on --resume) | slow
Env FAKE_CLAUDE_LOG: file to append the received argv (JSON) to.
"""

import json
import os
import subprocess
import sys
import time
import uuid


def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def arg(args, name):
    return args[args.index(name) + 1] if name in args else None


def mcp_call(config_path, tool, tool_args):
    cfg = json.load(open(config_path, encoding="utf-8"))["mcpServers"]["lyric2resolve"]
    env = dict(os.environ, **cfg.get("env", {}))
    p = subprocess.Popen([cfg["command"], *cfg["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, encoding="utf-8", env=env)

    def rpc(i, method, params):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    init = rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "fake", "version": "0"}})
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    res = rpc(2, "tools/call", {"name": tool, "arguments": tool_args})
    p.stdin.close()
    p.wait(timeout=10)
    return init, res["result"]


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        print("2.1.325 (Claude Code)")
        return 0
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "\n")
    mode = os.environ.get("FAKE_CLAUDE_MODE", "")
    prompt = sys.stdin.read()
    sid = arg(args, "--session-id") or arg(args, "--resume") or str(uuid.uuid4())
    if mode == "nosession" and "--resume" in args:
        sys.stderr.write(f"No conversation found with session ID: {sid}\n")
        return 1
    out({"type": "system", "subtype": "init", "session_id": sid, "model": "fake",
         "mcp_servers": [{"name": "lyric2resolve", "status": "connected"}], "claude_code_version": "2.1.325"})
    if mode == "login":
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "Not logged in · Please run /login"})
        return 1
    if mode == "limit":
        out({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1794811200,
                                                             "rateLimitType": "five_hour"}})
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "Claude usage limit reached. Your limit will reset at 5pm."})
        return 1
    if mode == "slow":
        time.sleep(30)
    if prompt.startswith("TOOL "):
        _, name, rest = prompt.split(" ", 2)
        tool_args = json.loads(rest)
        out({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": f"mcp__lyric2resolve__{name}", "input": tool_args}]}})
        _, res = mcp_call(arg(args, "--mcp-config"), name, tool_args)
        out({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "content": res["content"], "is_error": res["isError"]}]}})
        text = ("tool failed: " if res["isError"] else "done: ") + res["content"][0]["text"][:200]
    else:
        text = f"echo: {prompt}"
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}, "session_id": sid})
    out({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour",
                                                         "unifiedWindows": {"five_hour": {"utilization": 0.12}}}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": sid,
         "num_turns": 1, "permission_denials": []})
    return 0


if __name__ == "__main__":
    sys.exit(main())
