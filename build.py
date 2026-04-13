import datetime
import hashlib
import io
import os
import sys
import tarfile
import tempfile
import time

from parser import parse_docksmithfile
from state import State
from utils import sha256_bytes, sha256_file, compute_manifest_digest, expand_glob, build_tar_bytes, extract_tar_to_dir
from isolate import run_isolated

class BuildEngine:
    def __init__(self, state, no_cache=False):
        self.state    = state
        self.no_cache = no_cache

    def build(self, docksmithfile, context, name, tag):
        instructions      = parse_docksmithfile(docksmithfile)
        total_steps       = len(instructions)
        build_start       = time.monotonic()
        layers            = []
        workdir           = ""
        env_state         = {}
        cmd_default       = []
        prev_layer_digest = None
        cache_busted      = False
        original_created  = None

        for step_idx, instr in enumerate(instructions, start=1):
            keyword = instr["instruction"]
            args    = instr["args"]
            raw     = instr["raw"]

            if keyword == "FROM":
                print(f"Step {step_idx}/{total_steps} : {raw}")
                base              = self.state.load_image(args["image"], args["tag"])
                layers            = list(base.get("layers", []))
                workdir           = base.get("config", {}).get("WorkingDir", "")
                env_state         = _env_list_to_dict(base.get("config", {}).get("Env", []))
                cmd_default       = base.get("config", {}).get("Cmd", [])
                prev_layer_digest = base.get("digest", "")
                continue

            if keyword == "WORKDIR":
                
                workdir = args["path"]
                print(f"Step {step_idx}/{total_steps} : {raw}")
                continue

            if keyword == "ENV":
               
                env_state[args["key"]] = args["value"]
                print(f"Step {step_idx}/{total_steps} : {raw}")
                continue

            if keyword == "CMD":
                cmd_default = args["cmd"]
                print(f"Step {step_idx}/{total_steps} : {raw}")
                continue

            step_start = time.monotonic()
            cache_key  = _compute_cache_key(
                keyword=keyword, args=args,
                prev_digest=prev_layer_digest or "",
                workdir=workdir, env_state=env_state,
                context=context if keyword == "COPY" else None,
                raw=raw,
            )

            hit_digest = None
            if not self.no_cache and not cache_busted:
                hit_digest = self.state.cache_get(cache_key)
                if hit_digest and not self.state.layer_exists(hit_digest):
                    hit_digest   = None
                    cache_busted = True

            if hit_digest:
                elapsed    = time.monotonic() - step_start
                layer_size = os.path.getsize(self.state.layer_path(hit_digest))
                layers.append({"digest": hit_digest, "size": layer_size, "createdBy": raw})
                prev_layer_digest = hit_digest
                print(f"Step {step_idx}/{total_steps} : {raw} [CACHE HIT] {elapsed:.2f}s")
            else:
                cache_busted = True
                if keyword == "COPY":
                    layer_bytes = self._execute_copy(args, context, workdir)
                else:
                    layer_bytes = self._execute_run(args, layers, workdir, env_state)

                layer_digest = sha256_bytes(layer_bytes)
                layer_path   = self.state.layer_path(layer_digest)
                if not os.path.isfile(layer_path):
                    with open(layer_path, "wb") as f:
                        f.write(layer_bytes)
                if not self.no_cache:
                    self.state.cache_set(cache_key, layer_digest)

                elapsed = time.monotonic() - step_start
                layers.append({"digest": layer_digest, "size": len(layer_bytes), "createdBy": raw})
                prev_layer_digest = layer_digest
                print(f"Step {step_idx}/{total_steps} : {raw} [CACHE MISS] {elapsed:.2f}s")

        all_hits = not cache_busted
        if all_hits and self.state.image_exists(name, tag):
            original_created = self.state.load_image(name, tag).get("created")

        created  = original_created or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest = {
            "name"   : name,
            "tag"    : tag,
            "digest" : "",
            "created": created,
            "config" : {
                "Env"       : [f"{k}={v}" for k, v in sorted(env_state.items())],
                "Cmd"       : cmd_default,
                "WorkingDir": workdir,
            },
            "layers": layers,
        }
        manifest["digest"] = compute_manifest_digest(manifest)
        self.state.save_image(manifest)
        elapsed_total = time.monotonic() - build_start
        short = manifest["digest"].replace("sha256:", "")[:8]
        print(f"\nSuccessfully built sha256:{short} {name}:{tag} ({elapsed_total:.2f}s)")

    def _execute_copy(self, args, context, workdir):
        src_pattern = args["src"]
        dest        = args["dest"]
        matched = expand_glob(src_pattern, context)
        matched_files = [m for m in matched if os.path.isfile(m)]
        if not matched_files:
            print(f"error: COPY: no files matched {src_pattern!r}", file=sys.stderr)
            sys.exit(1)
        file_map = {}
        multiple = len(matched_files) > 1
        for src_abs in matched_files:
            if multiple or dest.endswith("/"):
                arc_path = os.path.join(dest.lstrip("/"), os.path.basename(src_abs))
            else:
                arc_path = dest.lstrip("/")
            file_map[arc_path] = src_abs
        return build_tar_bytes(file_map)

    def _execute_run(self, args, layers, workdir, env_state):
        command           = ["/bin/sh", "-c", args["command"]]
        effective_workdir = workdir or "/"
        with tempfile.TemporaryDirectory(prefix="docksmith_run_") as rootfs:
            for layer in layers:
                lp = self.state.layer_path(layer["digest"])
                if not os.path.isfile(lp):
                    print(f"error: layer file missing: {layer['digest']}", file=sys.stderr)
                    sys.exit(1)
                extract_tar_to_dir(lp, rootfs)
            if effective_workdir != "/":
                os.makedirs(os.path.join(rootfs, effective_workdir.lstrip("/")), exist_ok=True)
            before    = _snapshot(rootfs)
            exit_code = run_isolated(rootfs=rootfs, command=command, env=env_state, workdir=effective_workdir)
            if exit_code != 0:
                print(f"error: RUN exited with code {exit_code}: {args['command']}", file=sys.stderr)
                sys.exit(exit_code)
            after = _snapshot(rootfs)
            delta = {}
            for rel, stat_after in after.items():
                if before.get(rel) != stat_after:
                    delta[rel] = os.path.join(rootfs, rel)
            return build_tar_bytes(delta)


def _compute_cache_key(keyword, args, prev_digest, workdir, env_state, context, raw):
    h = hashlib.sha256()
    def feed(s):
        h.update(s.encode("utf-8"))
        h.update(b"\x00")
    feed(prev_digest)
    feed(raw)
    feed(workdir)
    for k in sorted(env_state.keys()):
        feed(f"{k}={env_state[k]}")
    if keyword == "COPY" and context:
        for src_abs in expand_glob(args["src"], context):
            if os.path.isfile(src_abs):
                feed(os.path.relpath(src_abs, context))
                feed(sha256_file(src_abs))
    return "sha256:" + h.hexdigest()


def _snapshot(rootfs):
    snap = {}
    for dp, dns, fns in os.walk(rootfs):
        dns.sort()
        for fn in sorted(fns):
            abs_p = os.path.join(dp, fn)
            rel   = os.path.relpath(abs_p, rootfs)
            try:
                st = os.stat(abs_p)
                snap[rel] = (st.st_mtime_ns, st.st_size, st.st_mode)
            except OSError:
                pass
    return snap


def _env_list_to_dict(env_list):
    result = {}
    for item in env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k] = v
    return result
