"""
runtime.py - Container runtime for 'docksmith run'.

1. Load image manifest
2. Extract all layer tars in order into a temp rootfs
3. Merge image ENV with -e overrides (overrides win)
4. Apply WorkingDir (default /)
5. Run via the same isolate primitive as the build engine
6. Print exit code, clean up temp rootfs
"""

import os
import shutil
import sys
import tempfile

from state import State
from utils import extract_tar_to_dir
from isolate import run_isolated


class Runtime:
    def __init__(self, state: State):
        self.state = state

    def run(self, name, tag, cmd_override, env_overrides):
        manifest = self.state.load_image(name, tag)
        config   = manifest.get("config", {})
        layers   = manifest.get("layers", [])

        # Determine command
        command = cmd_override if cmd_override else config.get("Cmd", [])
        if not command:
            print(f"error: no CMD defined in {name}:{tag} and no command given", file=sys.stderr)
            return 1

        # Build environment: image ENV first, then -e overrides
        env = _env_list_to_dict(config.get("Env", []))
        env.update(env_overrides)

        workdir = config.get("WorkingDir") or "/"

        # Assemble rootfs
        tmp_root = tempfile.mkdtemp(prefix="docksmith_rootfs_")
        try:
            for layer in layers:
                lp = self.state.layer_path(layer.get("digest", ""))
                if not os.path.isfile(lp):
                    print(f"error: layer missing: {layer.get('digest')}", file=sys.stderr)
                    return 1
                extract_tar_to_dir(lp, tmp_root)

            if workdir != "/":
                os.makedirs(os.path.join(tmp_root, workdir.lstrip("/")), exist_ok=True)

            exit_code = run_isolated(
                rootfs=tmp_root, command=command, env=env, workdir=workdir,
            )
            print(f"\nContainer exited with code {exit_code}")
            return exit_code
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)


def _env_list_to_dict(env_list):
    result = {}
    for item in env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k] = v
    return result
