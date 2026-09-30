# Installed-wheel runtime verification

A real pre-fix wheel contained Python modules but omitted all six web files and
`invest/upstream_registry.json`. Editable/source tests could not detect this:
they still read those files from the checkout. Non-editable installation would
lose the workbench assets and upstream catalogue.

`pyproject.toml` now explicitly includes the registry and the HTML/CSS/JavaScript
files as package data. The package name, version, runtime dependencies,
application behavior and upstream licensing remain unchanged.

## Reproduce

```sh
python -m pip wheel . --wheel-dir dist
python -m pip install --no-index --find-links dist invest
python tools/wheel_smoke.py dist
```

The smoke tool accepts either a wheel file or a directory containing exactly
one Invest wheel. It checks the archive members, installs that wheel into a
new temporary target with no dependency download, and starts an isolated
Python process outside the checkout. It asserts that the imported package is
inside that target, then verifies:

- Registry data is present and queryable
- Six workbench/legacy HTML, JavaScript and CSS routes serve the packaged files
- A clearly synthetic dataset can run an 18-case study, save it and download
  the same authoritative result through real loopback HTTP
- No real provider call or frozen holdout observation occurs

The pre-fix wheel is rejected for its seven missing assets. The repaired wheel
passes the complete smoke. Four unit tests additionally check import safety,
missing/ambiguous artifact rejection and isolated/no-download subprocess flags.
Full source pytest: 569 passed, 13 optional skips, 348 passing subtests.

The dedicated installed-wheel workflow runs on Ubuntu and Windows with Python
3.11/3.12. Each build, install and smoke command has its own failing step.
Exact-head CI must be checked after publication. This verifies actual packaged
HTTP/API assets, not browser rendering or a frozen Windows EXE.

This patch does not publish a package to PyPI or change the documented optional
SDK/source-vendor behavior. No user data or credentials enter build artifacts.
