# docstrings2pep727

[![ci](https://github.com/pawamoy/docstrings2pep727/workflows/ci/badge.svg)](https://github.com/pawamoy/docstrings2pep727/actions?query=workflow%3Aci)
[![documentation](https://img.shields.io/badge/docs-zensical-FF9100.svg?style=flat)](https://pawamoy.github.io/docstrings2pep727/)
[![pypi version](https://img.shields.io/pypi/v/docstrings2pep727.svg)](https://pypi.org/project/docstrings2pep727/)
[![gitter](https://img.shields.io/badge/matrix-chat-4DB798.svg?style=flat)](https://app.gitter.im/#/room/#docstrings2pep727:gitter.im)

Move documentation from docstrings to PEP 727 type annotations.

## Installation

```bash
pip install docstrings2pep727
```

With [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install docstrings2pep727
```


## Usage


Add `typing-extensions>=4.8` to the project that runs the transformed code. The output imports `Doc` from `typing_extensions`.


Preview changes before editing files:


```bash
docstrings2pep727 diff src/
```


Rewrite one or more Python files or directories:


```bash
docstrings2pep727 format src/ tests/
```


Use `check` in CI. It leaves files unchanged and exits with status 1 if changes are needed.


```bash
docstrings2pep727 check src/
```


Each subcommand detects Google, NumPy, and Sphinx docstrings. To choose a style, add `--style google`, `--style numpy`, or `--style sphinx` after the subcommand.


```bash
docstrings2pep727 format --style google src/
```


The transformation moves descriptions for annotated parameters, returns, yields, receives, and attributes into `Annotated[..., Doc(...)]`.


It keeps prose and unsupported sections, such as `Raises`, in docstrings. It keeps a section if any item cannot be moved.


## Sponsors

<!-- sponsors-start -->
<!-- sponsors-end -->
