import glob as _glob
import hashlib
import io
import json
import os
import tarfile

def sha256_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def sha256_string(s):
    return sha256_bytes(s.encode("utf-8"))

def _zero_tarinfo(info):
    """Zero timestamps and ownership for reproducibility, preserve permissions."""
    info.mtime = 0
    info.uid   = 0
    info.gid   = 0
    info.uname = ""
    info.gname = ""
    return info

def build_tar_bytes(file_map):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tar:
        for arc_path in sorted(file_map.keys()):
            src_path = file_map[arc_path]
            if not os.path.exists(src_path):
                continue
            info = tar.gettarinfo(name=src_path, arcname=arc_path)
            info = _zero_tarinfo(info)
            if info.isreg():
                with open(src_path, "rb") as fh:
                    tar.addfile(info, fh)
            else:
                tar.addfile(info)
    return buf.getvalue()

def extract_tar_to_dir(tar_path, dest_dir):
    """Extract tar preserving permissions. Never use filter='tar' which strips them."""
    with tarfile.open(tar_path, "r:*") as tar:
        for member in tar.getmembers():
            # Sanitize path to prevent directory traversal
            if os.path.isabs(member.name):
                member.name = member.name.lstrip("/")
            target = os.path.realpath(os.path.join(dest_dir, member.name))
            if not target.startswith(os.path.realpath(dest_dir)):
                continue  # skip unsafe paths
            tar.extract(member, path=dest_dir, set_attrs=True)

def compute_manifest_digest(manifest):
    canonical = dict(manifest)
    canonical["digest"] = ""
    serialized = json.dumps(canonical, indent=2, sort_keys=False).encode("utf-8")
    return sha256_bytes(serialized)

def expand_glob(pattern, base_dir):
    full_pattern = os.path.join(base_dir, pattern)
    return sorted(_glob.glob(full_pattern, recursive=True))
