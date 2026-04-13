"""
isolate.py - Linux process isolation primitive.

Used by BOTH the build engine (RUN) and the container runtime (docksmith run).

Strategy:
  - 'unshare --user --map-root-user' gives us a user namespace where we
    appear as uid 0 (root), granting CAP_SYS_CHROOT without real root.
  - '--mount --uts --pid --fork' add mount, UTS and PID namespace isolation.
  - A small Python helper script is exec'd under unshare; it calls
    os.chroot() into the assembled rootfs, then os.execvp() the command.
  - The child process cannot access any host path outside the rootfs.
"""

import json
import os
import subprocess
import sys
import tempfile


def run_isolated(rootfs: str, command: list, env: dict, workdir: str = "/") -> int:
    """
    Execute `command` inside `rootfs` with namespace + chroot isolation.

    Parameters
    ----------
    rootfs  : absolute path to the assembled rootfs directory
    command : argv list to exec inside the container
    env     : environment variables dict (clean — only these are visible)
    workdir : working directory inside the container (default "/")

    Returns exit code (int).
    """
    if not command:
        print("error: no command to execute", file=sys.stderr)
        return 1

    # Ensure workdir exists inside rootfs
    host_workdir = os.path.join(rootfs, workdir.lstrip("/"))
    os.makedirs(host_workdir, exist_ok=True)

    helper = _build_helper(rootfs, command, env, workdir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="docksmith_helper_"
    ) as tmp:
        tmp.write(helper)
        helper_path = tmp.name

    os.chmod(helper_path, 0o755)

    try:
        unshare_cmd = [
            "unshare",
            "--mount",
            "--uts",
            "--pid",
            "--fork",
            "--user",
            "--map-root-user",
            sys.executable,
            helper_path,
        ]
        result = subprocess.run(unshare_cmd)
        return result.returncode
    finally:
        try:
            os.unlink(helper_path)
        except OSError:
            pass


def _build_helper(rootfs: str, command: list, env: dict, workdir: str) -> str:
    """
    Generate a self-contained Python script that chroots and execs the command.
    Runs as virtual root inside the user namespace.
    """
    return f"""#!/usr/bin/env python3
import os, sys

rootfs  = {json.dumps(rootfs)}
command = {json.dumps(command)}
env     = {json.dumps(env)}
workdir = {json.dumps(workdir)}

# Mount /proc so tools like 'ps' work inside the container
proc_dir = os.path.join(rootfs, "proc")
os.makedirs(proc_dir, exist_ok=True)
os.system(f"mount -t proc proc {{proc_dir}} 2>/dev/null")

# chroot into the assembled rootfs
try:
    os.chroot(rootfs)
except PermissionError as e:
    print(f"error: chroot failed: {{e}}", file=sys.stderr)
    print("hint: ensure 'unshare' supports --user --map-root-user on this system",
          file=sys.stderr)
    sys.exit(1)

# Set working directory
try:
    os.chdir(workdir)
except Exception:
    os.chdir("/")

# Replace environment entirely
os.environ.clear()
for k, v in env.items():
    os.environ[k] = v

# Exec the command (replaces this helper process)
try:
    os.execvp(command[0], command)
except FileNotFoundError:
    print(f"error: executable not found inside container: {{command[0]}}", file=sys.stderr)
    sys.exit(127)
except Exception as e:
    print(f"error: exec failed: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
