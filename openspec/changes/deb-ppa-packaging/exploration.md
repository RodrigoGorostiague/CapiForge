# Exploration: Debian `.deb` and Launchpad PPA Packaging

## Current install path

`./capinstall` → `uv tool install --editable .[tui]` from checkout. Works for developers; not suitable for end-user `apt install`.

## Blockers for `.deb`

1. **`pyproject.toml`** packages only `runtime*`; `storage/`, `skills/`, `assets/` are not installed.
2. **`REPO_ROOT = Path(__file__).resolve().parents[3]`** in `runtime/node/store/__init__.py` resolves to site-packages parent, not share data.
3. **`capinstall`** always runs editable uv install from `checkout_root`.

## Packaging options considered

| Option | Pros | Cons |
|--------|------|------|
| `dh-python` + pybuild | Idiomatic Debian/PPA; apt integration | Requires debian/ maintenance |
| nfpm / fpm only | Fast CI deb | Weaker policy compliance for public PPA |
| Self-contained `/opt` venv deb | Isolated deps | Duplicates system Python; larger package |

**Chosen:** `dh-python` + pybuild with share data via setuptools `data-files` and `runtime/paths.py`.

## PPA vs local deb

User target: **public Launchpad PPA** with full payload (`capiforge`, `capinstall`, share data).
