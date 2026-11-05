"""Deterministic fixture repo for ``bench_projects``: built at run time, never vendored into git.

    from scripts.bench_repo_gen import build_repo
    info = build_repo(Path(tmp) / "repo", seed=1234, bug=True)

The repo is a python package (``pkg``) of many small modules plus a fast unittest-style pytest suite
(about 1,600 files, whole suite well under 30 s) and is git-initialised with one baseline commit.
Three places are reserved for the benchmark tasks:

  pkg/core/mathx.py   ``clamp`` (with ``bug=True`` it has an off-by-one and tests/test_core_mathx.py is red)
  pkg/core/text.py    where the ``truncate_words`` feature is added (task b)
  pkg/core/norm.py    ``normalize_value``, used by ``info["norm_users"]`` modules (task c, rename)
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List

N_SUBPACKAGES = 30
N_MODULES = 40  # per subpackage
N_DOCS = 360
N_NORM_USERS = 14  # modules that call normalize_value (task c needs >= 10 files)

GITIGNORE = "__pycache__/\n*.pyc\n.pytest_cache/\n"
PYTEST_INI = "[pytest]\ntestpaths = tests\naddopts = -p no:cacheprovider\n"

MATHX = '''"""Small numeric helpers."""


def clamp(value, lo, hi):
    """Limit ``value`` to the closed range [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return {above}
    return value
'''

TEXT = '''"""Small text helpers."""


def slugify(text):
    """Lower-case words joined by single dashes."""
    return "-".join(text.lower().split())
'''

NORM = '''"""Value normalisation shared by many modules."""


def normalize_value(x):
    """Parse a number-like value and round it to 2 decimals."""
    return round(float(str(x).strip()), 2)
'''

TEST_MATHX = '''from pkg.core.mathx import clamp


def test_clamp_inside():
    assert clamp(5, 0, 10) == 5


def test_clamp_below():
    assert clamp(-3, 0, 10) == 0


def test_clamp_above():
    assert clamp(15, 0, 10) == 10
'''

TEST_TEXT = '''from pkg.core.text import slugify


def test_slugify():
    assert slugify("Hello  Big World") == "hello-big-world"
'''

TEST_NORM = '''from pkg.core.norm import normalize_value


def test_normalize_value():
    assert normalize_value(" 2.345 ") == 2.35 or normalize_value(" 2.345 ") == 2.34
    assert normalize_value(7) == 7.0
'''


def _module_source(sub: int, mod: int, rng: random.Random, uses_norm: bool) -> str:
    k, d = rng.randint(2, 9), rng.randint(1, 99)
    lines = [f'"""Generated module sub{sub:02d}.m{mod:02d}."""']
    if uses_norm:
        lines.append("from pkg.core.norm import normalize_value")
    lines += ["", f"K = {k}", f"D = {d}", "", "",
              "def scale(x):", "    return x * K + D", "", "",
              "def label(x):", f'    return f"s{sub:02d}m{mod:02d}-{{x}}"', "", "",
              "def total(values):", "    return sum(scale(v) for v in values)"]
    if uses_norm:
        lines += ["", "", "def clean(x):", "    return normalize_value(x) + K"]
    return "\n".join(lines) + "\n"


def _test_source(sub: int, mods: Dict[int, Dict[str, Any]]) -> str:
    names = ", ".join(f"m{m:02d}" for m in sorted(mods))
    out = [f"from pkg.sub{sub:02d} import {names}", ""]
    for m, spec in sorted(mods.items()):
        k, d = spec["k"], spec["d"]
        out += ["", f"def test_m{m:02d}():",
                f"    assert m{m:02d}.scale(2) == {2 * k + d}",
                f'    assert m{m:02d}.label(1) == "s{sub:02d}m{m:02d}-1"',
                f"    assert m{m:02d}.total([1, 2]) == {3 * k + 2 * d}"]
        if spec["norm"]:
            out.append(f"    assert m{m:02d}.clean(\"1.5\") == {1.5 + k}")
    return "\n".join(out) + "\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # LF, no BOM, whatever the platform


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", *args], cwd=repo,
                          capture_output=True, text=False, check=check)


def build_repo(dest: Path, *, seed: int = 1234, bug: bool = False, subpackages: int = N_SUBPACKAGES,
               docs: int = N_DOCS) -> Dict[str, Any]:
    """Create the repo in ``dest`` (must not exist or be empty) and return facts about it."""
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    norm_users = sorted(rng.sample([(s, m) for s in range(subpackages) for m in range(N_MODULES)], N_NORM_USERS))
    norm_set = set(norm_users)

    _write(dest, ".gitignore", GITIGNORE)
    _write(dest, "pytest.ini", PYTEST_INI)
    _write(dest, "README.md", "# Fixture repo (generated for bench_projects)\n")
    _write(dest, "pkg/__init__.py", '"""Fixture package."""\n')
    _write(dest, "pkg/core/__init__.py", "")
    _write(dest, "pkg/core/mathx.py", MATHX.format(above="hi - 1" if bug else "hi"))
    _write(dest, "pkg/core/text.py", TEXT)
    _write(dest, "pkg/core/norm.py", NORM)
    _write(dest, "tests/test_core_mathx.py", TEST_MATHX)
    _write(dest, "tests/test_core_text.py", TEST_TEXT)
    _write(dest, "tests/test_core_norm.py", TEST_NORM)

    for sub in range(subpackages):
        _write(dest, f"pkg/sub{sub:02d}/__init__.py", "")
        specs: Dict[int, Dict[str, Any]] = {}
        for mod in range(N_MODULES):
            uses = (sub, mod) in norm_set
            src = _module_source(sub, mod, rng, uses)
            _write(dest, f"pkg/sub{sub:02d}/m{mod:02d}.py", src)
            k = int(src.split("K = ")[1].split("\n")[0])
            d = int(src.split("D = ")[1].split("\n")[0])
            specs[mod] = {"k": k, "d": d, "norm": uses}
        _write(dest, f"tests/test_sub{sub:02d}.py", _test_source(sub, specs))
    for i in range(docs):
        _write(dest, f"docs/note_{i:03d}.md", f"# Note {i}\n\nGenerated filler {rng.getrandbits(32):08x}.\n")

    git(dest, "init", "-q")
    git(dest, "config", "user.name", "bench")
    git(dest, "config", "user.email", "bench@example.invalid")
    git(dest, "config", "core.autocrlf", "false")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "baseline")

    files = [p for p in dest.rglob("*") if p.is_file() and ".git" not in p.relative_to(dest).parts]
    user_files = [f"pkg/sub{s:02d}/m{m:02d}.py" for s, m in norm_users]
    return {
        "root": dest,
        "seed": seed,
        "bug": bug,
        "file_count": len(files),
        "norm_users": user_files,
    }


def list_files(repo: Path) -> List[str]:
    return sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")
                  if p.is_file() and ".git" not in p.relative_to(repo).parts)
