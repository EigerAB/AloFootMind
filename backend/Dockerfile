FROM python:3.12-slim

WORKDIR /app

RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    zlib1g-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python - <<'EOF'
import importlib.metadata, os, site
shim = """
from importlib.metadata import PackageNotFoundError, version as _version

DistributionNotFound = PackageNotFoundError

class _Dist:
    def __init__(self, name):
        try:
            self.version = _version(name)
        except PackageNotFoundError as e:
            raise DistributionNotFound(name) from e

def get_distribution(name):
    return _Dist(name)
"""
for p in site.getsitepackages():
    if os.path.isdir(p):
        with open(os.path.join(p, "pkg_resources.py"), "w") as f:
            f.write(shim)
        print(f"pkg_resources shim written to {p}")
        break
EOF

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
