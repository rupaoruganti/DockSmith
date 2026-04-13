#!/usr/bin/env python3
"""
docksmith - A simplified Docker-like build and runtime system.
CLI entry point.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state import State
from build import BuildEngine
from runtime import Runtime


def cmd_build(args):
    context = os.path.abspath(args.context)
    if not os.path.isdir(context):
        print(f"error: context directory not found: {context}", file=sys.stderr)
        sys.exit(1)

    docksmithfile = os.path.join(context, "Docksmithfile")
    if not os.path.isfile(docksmithfile):
        print(f"error: no Docksmithfile found in {context}", file=sys.stderr)
        sys.exit(1)

    if ":" not in args.tag:
        print("error: tag must be in <name>:<tag> format (e.g. myapp:latest)", file=sys.stderr)
        sys.exit(1)

    name, tag = args.tag.split(":", 1)
    state = State()
    engine = BuildEngine(state, no_cache=args.no_cache)
    engine.build(docksmithfile, context, name, tag)


def cmd_images(args):
    state = State()
    images = state.list_images()
    if not images:
        print("No images found.")
        return
    fmt = "{:<20} {:<10} {:<14} {}"
    print(fmt.format("NAME", "TAG", "ID", "CREATED"))
    for img in images:
        digest = img.get("digest", "")
        short_id = digest.replace("sha256:", "")[:12] if digest else "unknown"
        print(fmt.format(img.get("name",""), img.get("tag",""), short_id, img.get("created","")))


def cmd_rmi(args):
    if ":" not in args.name_tag:
        print("error: argument must be in <name>:<tag> format", file=sys.stderr)
        sys.exit(1)
    name, tag = args.name_tag.split(":", 1)
    state = State()
    state.remove_image(name, tag)
    print(f"Removed {args.name_tag}")


def cmd_run(args):
    if ":" not in args.name_tag:
        print("error: argument must be in <name>:<tag> format", file=sys.stderr)
        sys.exit(1)
    name, tag = args.name_tag.split(":", 1)
    env_overrides = {}
    for item in (args.env or []):
        if "=" not in item:
            print(f"error: -e value must be KEY=VALUE, got: {item}", file=sys.stderr)
            sys.exit(1)
        k, v = item.split("=", 1)
        env_overrides[k] = v
    state = State()
    rt = Runtime(state)
    exit_code = rt.run(name, tag, cmd_override=args.cmd or [], env_overrides=env_overrides)
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(prog="docksmith")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    p_build = subparsers.add_parser("build")
    p_build.add_argument("-t", dest="tag", required=True, metavar="name:tag")
    p_build.add_argument("--no-cache", action="store_true")
    p_build.add_argument("context")
    p_build.set_defaults(func=cmd_build)

    p_images = subparsers.add_parser("images")
    p_images.set_defaults(func=cmd_images)

    p_rmi = subparsers.add_parser("rmi")
    p_rmi.add_argument("name_tag", metavar="name:tag")
    p_rmi.set_defaults(func=cmd_rmi)

    p_run = subparsers.add_parser("run")
    p_run.add_argument("-e", dest="env", action="append", metavar="KEY=VALUE")
    p_run.add_argument("name_tag", metavar="name:tag")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()