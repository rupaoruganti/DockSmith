import os
import json
import sys

class State:
    def __init__(self, root=None):
        self.root       = root or os.path.join(os.path.expanduser("~"), ".docksmith")
        self.images_dir = os.path.join(self.root, "images")
        self.layers_dir = os.path.join(self.root, "layers")
        self.cache_dir  = os.path.join(self.root, "cache")
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in (self.images_dir, self.layers_dir, self.cache_dir):
            os.makedirs(d, exist_ok=True)

    def _manifest_path(self, name, tag):
        safe = f"{name}_{tag}.json".replace("/", "_")
        return os.path.join(self.images_dir, safe)

    def image_exists(self, name, tag):
        return os.path.isfile(self._manifest_path(name, tag))

    def load_image(self, name, tag):
        path = self._manifest_path(name, tag)
        if not os.path.isfile(path):
            print(f"error: image not found: {name}:{tag}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            return json.load(f)

    def save_image(self, manifest):
        path = self._manifest_path(manifest["name"], manifest["tag"])
        with open(path, "w") as f:
            json.dump(manifest, f, indent=2)

    def list_images(self):
        manifests = []
        for fname in sorted(os.listdir(self.images_dir)):
            if fname.endswith(".json"):
                with open(os.path.join(self.images_dir, fname)) as f:
                    try:
                        manifests.append(json.load(f))
                    except Exception:
                        pass
        return manifests

    def remove_image(self, name, tag):
        path = self._manifest_path(name, tag)
        if not os.path.isfile(path):
            print(f"error: image not found: {name}:{tag}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            manifest = json.load(f)
        os.remove(path)
        for layer in manifest.get("layers", []):
            lp = self.layer_path(layer.get("digest", ""))
            if os.path.isfile(lp):
                os.remove(lp)

    def layer_path(self, digest):
        return os.path.join(self.layers_dir, digest.replace(":", "_"))

    def layer_exists(self, digest):
        return os.path.isfile(self.layer_path(digest))

    def _cache_index_path(self):
        return os.path.join(self.cache_dir, "cache_index.json")

    def _load_cache_index(self):
        path = self._cache_index_path()
        if not os.path.isfile(path):
            return {}
        with open(path) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

    def _save_cache_index(self, index):
        with open(self._cache_index_path(), "w") as f:
            json.dump(index, f, indent=2)

    def cache_get(self, cache_key):
        return self._load_cache_index().get(cache_key)

    def cache_set(self, cache_key, layer_digest):
        index = self._load_cache_index()
        index[cache_key] = layer_digest
        self._save_cache_index(index)
