#!/usr/bin/env python3
"""
import_base_image.py - One-time setup: download Alpine 3.18 and register it.

Usage:
  python3 import_base_image.py                    # download from CDN
  python3 import_base_image.py --local <file>     # import from local tar.gz
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import State
from utils import compute_manifest_digest

ALPINE_URL  = ("https://dl-cdn.alpinelinux.org/alpine/v3.18/releases/x86_64/"
               "alpine-minirootfs-3.18.6-x86_64.tar.gz")
ALPINE_NAME = "alpine"
ALPINE_TAG  = "3.18"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def import_image(local_tar=None):
    state = State()
    if state.image_exists(ALPINE_NAME, ALPINE_TAG):
        print(f"Image {ALPINE_NAME}:{ALPINE_TAG} already in local store.")
        return

    if local_tar:
        src = os.path.abspath(local_tar)
        if not os.path.isfile(src):
            print(f"error: file not found: {src}", file=sys.stderr); sys.exit(1)
        print(f"Importing from local file: {src}")
    else:
        import tempfile
        print(f"Downloading {ALPINE_URL} ...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            tmp_path = tmp.name
        try:
            urllib.request.urlretrieve(ALPINE_URL, tmp_path,
                lambda b, bs, ts: print(f"\r  {min(100, b*bs*100//ts) if ts>0 else '...'}%",
                                        end="", flush=True))
            print()
            src = tmp_path
        except Exception as e:
            print(f"error: download failed: {e}", file=sys.stderr); sys.exit(1)

    print("Computing digest ...")
    layer_digest = sha256_file(src)
    layer_path   = state.layer_path(layer_digest)
    layer_size   = os.path.getsize(src)

    if not os.path.isfile(layer_path):
        shutil.copy2(src, layer_path)

    if not local_tar and os.path.isfile(src):
        os.unlink(src)

    manifest = {
        "name"   : ALPINE_NAME,
        "tag"    : ALPINE_TAG,
        "digest" : "",
        "created": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config" : {"Env": [], "Cmd": ["/bin/sh"], "WorkingDir": ""},
        "layers" : [{"digest": layer_digest, "size": layer_size,
                     "createdBy": f"imported alpine:{ALPINE_TAG} rootfs"}],
    }
    manifest["digest"] = compute_manifest_digest(manifest)
    state.save_image(manifest)

    print(f"Imported {ALPINE_NAME}:{ALPINE_TAG}  digest={manifest['digest']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", metavar="PATH")
    args = ap.parse_args()
    import_image(local_tar=args.local)
