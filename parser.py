import json
import sys

VALID_INSTRUCTIONS = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}

def parse_docksmithfile(path):
    with open(path) as f:
        lines = f.readlines()
    instructions = []
    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\n").strip()
        if not line or line.startswith("#"):
            continue
        parts   = line.split(None, 1)
        keyword = parts[0].upper()
        rest    = parts[1] if len(parts) > 1 else ""
        if keyword not in VALID_INSTRUCTIONS:
            print(f"error: unrecognised instruction '{parts[0]}' on line {lineno}", file=sys.stderr)
            sys.exit(1)
        args = _parse_args(keyword, rest, lineno)
        instructions.append({"instruction": keyword, "args": args, "raw": line, "lineno": lineno})
    if not instructions:
        print("error: Docksmithfile is empty", file=sys.stderr)
        sys.exit(1)
    if instructions[0]["instruction"] != "FROM":
        print(f"error: first instruction must be FROM", file=sys.stderr)
        sys.exit(1)
    return instructions

def _parse_args(keyword, rest, lineno):
    def err(msg):
        print(f"error: line {lineno}: {msg}", file=sys.stderr)
        sys.exit(1)
    rest = rest.strip()
    if keyword == "FROM":
        if not rest: err("FROM requires an image argument")
        image, tag = (rest.split(":", 1) if ":" in rest else (rest, "latest"))
        return {"image": image.strip(), "tag": tag.strip()}
    if keyword == "COPY":
        tokens = rest.split()
        if len(tokens) < 2: err("COPY requires <src> and <dest>")
        return {"src": " ".join(tokens[:-1]), "dest": tokens[-1]}
    if keyword == "RUN":
        if not rest: err("RUN requires a command")
        return {"command": rest}
    if keyword == "WORKDIR":
        if not rest: err("WORKDIR requires a path")
        return {"path": rest}
    if keyword == "ENV":
        if "=" not in rest: err("ENV requires KEY=VALUE format")
        key, value = rest.split("=", 1)
        if not key.strip(): err("ENV key must not be empty")
        return {"key": key.strip(), "value": value.strip()}
    if keyword == "CMD":
        try:
            cmd_list = json.loads(rest)
        except json.JSONDecodeError as e:
            err(f"CMD must be a valid JSON array: {e}")
        if not isinstance(cmd_list, list) or not all(isinstance(x, str) for x in cmd_list):
            err("CMD must be a JSON array of strings")
        return {"cmd": cmd_list}
