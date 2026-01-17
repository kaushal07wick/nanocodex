#!/usr/bin/env python3
import os
import json
import subprocess
import urllib.request
import glob
import re

API_URL = "https://api.openai.com/v1/responses"
MODEL = os.getenv("MODEL", "gpt-5.2")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
CWD = os.getcwd()

if not OPENAI_KEY:
    raise SystemExit("OPENAI_API_KEY missing")

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW = "\033[34m", "\033[36m", "\033[32m", "\033[33m"

def sep():
    import shutil
    return DIM + "─" * shutil.get_terminal_size().columns + RESET

# tools
def run_shell(cmd):
    p = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, err = p.communicate()
    return {
        "stdout": out,
        "stderr": err,
        "exit_code": p.returncode
    }

def read_file(path, offset=0, limit=None):
    with open(path) as f:
        lines = f.readlines()
    limit = limit if limit is not None else len(lines)
    chunk = lines[offset:offset + limit]
    return "".join(f"{offset+i+1:4}| {l}" for i, l in enumerate(chunk))

def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)
    return "ok"

def glob_files(pat, path="."):
    files = glob.glob(os.path.join(path, pat), recursive=True)
    return "\n".join(sorted(files)) if files else "none"

def grep_files(pat, path="."):
    rx = re.compile(pat)
    hits = []
    for fp in glob.glob(os.path.join(path, "**"), recursive=True):
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp) as f:
                for i, line in enumerate(f, 1):
                    if rx.search(line):
                        hits.append(f"{fp}:{i}:{line.rstrip()}")
        except Exception:
            pass
    return "\n".join(hits[:50]) if hits else "none"

def log_tool(name, args, result):
    label = name.replace("_files", "").replace("_", " ").title()
    key = next(iter(args.values()), "")

    print(f"{GREEN}● {label}({key}){RESET}")

    if name == "read_file":
        n = result.count("\n") + 1
        print(f"{DIM}  └ {args['path']} ... +{n} lines{RESET}")

    elif name == "glob_files":
        files = result.splitlines()
        if files and files[0] != "none":
            print(f"{DIM}  └ {files[0]} ... +{len(files)-1} files{RESET}")
        else:
            print(f"{DIM}  └ none{RESET}")

    elif name == "grep_files":
        print(f"{DIM}  └ {len(result.splitlines())} matches{RESET}")

    elif name == "run_shell":
        pass

    elif name == "write_file":
        print(f"{DIM}  └ wrote {args['path']}{RESET}")


# registry
TOOLS = [
    {
        "type": "function",
        "name": "run_shell",
        "description": "Run a non-destructive shell command (ls, wc, cat, grep, find)",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": { "type": "string" }
            },
            "required": ["cmd"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "read_file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": { "type": "string" },
                "offset": { "type": "integer" },
                "limit": { "type": "integer" }
            },
            "required": ["path"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "write_file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": { "type": "string" },
                "content": { "type": "string" }
            },
            "required": ["path", "content"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "glob_files",
        "parameters": {
            "type": "object",
            "properties": {
                "pat": { "type": "string" },
                "path": { "type": "string" }
            },
            "required": ["pat"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "grep_files",
        "parameters": {
            "type": "object",
            "properties": {
                "pat": { "type": "string" },
                "path": { "type": "string" }
            },
            "required": ["pat"],
            "additionalProperties": False
        }
    }
]

TOOL_IMPL = {
    "run_shell": run_shell,
    "read_file": read_file,
    "write_file": write_file,
    "glob_files": glob_files,
    "grep_files": grep_files,
}

# call openai
def call_openai(input_items):
    payload = {
        "model": MODEL,
        "instructions": (
            "You are a careful & concise coding assistant with tool access.\n"
            f"Current directory: {CWD}\n"
            "Rules:\n"
            "- Use tools when you need concrete data\n"
            "- Never assume file contents\n"
            "- Do not run destructive shell commands\n"
            "- Use tools silently to gather evidence\n"
            "- Do NOT explain while using tools\n"
            "- After all tools are done, produce ONE concise output_text\n"
        ),
        "tools": TOOLS,
        "input": input_items,
        "max_output_tokens": 4096
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
    )

    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():

    print(" ")
    print(f"               {BOLD}nanocodex{RESET} | {DIM}{MODEL}{RESET} | {DIM}cwd={CWD}{RESET}\n")
    print(" ")
    
    input_items = []
    while True:
        print(sep())
        q = input(f"{BLUE}❯{RESET} ").strip()
        print(sep())

        if q in ("exit", "/q", "/quit"):
            print(f"{YELLOW}Exiting nanocode{RESET}")
            break
        if q in ("/c", "clear"):
            print(f"{DIM}Conversation cleared{RESET}\n")
            continue
        if not q:
            continue

        input_items.append({"role": "user", "content": q})

        while True:
            resp = call_openai(input_items)
            output = resp.get("output", [])

            tool_calls = []

            for item in output:
                if item["type"] == "function_call":
                    tool_calls.append(item)

                elif item["type"] == "output_text":
                    print(f"{CYAN}=>{RESET} {item['content'][0]['text']}")

                elif item["type"] == "message":
                    for c in item.get("content", []):
                        if c["type"] == "output_text":
                            print(f"{CYAN}=>{RESET} {c['text']}")


            if not tool_calls:
                break

            for fc in tool_calls:
                name = fc["name"]
                args = json.loads(fc["arguments"])

                result = TOOL_IMPL[name](**args)
                log_tool(name, args, result)

                input_items.append(fc)
                input_items.append({
                    "type": "function_call_output",
                    "call_id": fc["call_id"],
                    "output": json.dumps(result)
                })

if __name__ == "__main__":
    main()
