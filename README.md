# DockSmith 🐳

DockSmith is a lightweight Docker-inspired container build and runtime system built from scratch. It implements core containerization concepts including image layering, content-addressed storage, deterministic build caching, and Linux process isolation without relying on Docker, containerd, or any existing container runtime.

## Features

- Supports `FROM`, `COPY`, `RUN`, `WORKDIR`, `ENV`, and `CMD`
- Immutable content-addressed image layers
- Deterministic build cache with cache hit/miss detection
- Offline image builds and container execution
- Linux filesystem isolation for build and runtime
- Local image management (`build`, `images`, `run`, `rmi`)
- Reproducible builds using SHA-256 digests

---

## Architecture

```text
                +------------------+
                |  DockSmith CLI   |
                +--------+---------+
                         |
          +--------------+--------------+
          |                             |
          v                             v
 +----------------+         +-------------------+
 |  Build Engine  |         | Container Runtime |
 +----------------+         +-------------------+
          |                             |
          v                             v
      Layer Store              Process Isolation

~/.docksmith/
├── images/
├── layers/
└── cache/
```

---

## Supported Instructions

| Instruction | Description |
|------------|-------------|
| FROM | Use a local base image |
| COPY | Copy files from build context |
| RUN | Execute commands inside container filesystem |
| WORKDIR | Set working directory |
| ENV | Define environment variables |
| CMD | Define default runtime command |

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/rupaoruganti/DockSmith.git
cd DockSmith
```

### Import Base Image (One-Time Setup)

```bash
python3 import_base_image.py
```

This downloads/imports the base image into the local DockSmith store.

Verify:

```bash
ls ~/.docksmith/images
ls ~/.docksmith/layers
```

---

## Usage

### Build an Image

```bash
python3 docksmith.py build -t myapp:latest .
```

Example output:

```text
Step 1/3 : FROM alpine:3.18
Step 2/3 : COPY . /app [CACHE MISS]
Step 3/3 : RUN echo "Build Complete" [CACHE MISS]

Successfully built myapp:latest
```

---

### Build Without Cache

```bash
python3 docksmith.py build --no-cache -t myapp:latest .
```

---

### List Images

```bash
python3 docksmith.py images
```

Example:

```text
NAME      TAG      IMAGE ID      CREATED
myapp     latest   a3f9b2c1e2f4  2026-04-01
```

---

### Run a Container

```bash
sudo python3 docksmith.py run myapp:latest
```

---

### Override Environment Variables

```bash
sudo python3 docksmith.py run -e APP_NAME=Production myapp:latest
```

---

### Remove an Image

```bash
python3 docksmith.py rmi myapp:latest
```

---


