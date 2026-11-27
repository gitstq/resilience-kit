# Contributing to resilience-kit

Thanks for your interest in improving resilience-kit! This document explains how to propose changes and get them merged smoothly.

## Ground rules

- This is a **zero-dependency** project. New code must not import anything outside the Python standard library.
- Every behavioural change needs a corresponding test. All tests must pass before a PR can be merged.
- Keep the public API small, explicit and documented.

## Development setup

```bash
git clone https://github.com/gitstq/resilience-kit.git
cd resilience-kit
python3 -m pip install -e .
```

No virtual environment is strictly required because the project has no runtime dependencies, but using one is encouraged.

## Running tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The suite is written with `unittest` only, so it runs anywhere Python runs. Deterministic clocks are injected via `clock=` / `sleep=` parameters — prefer that pattern over `time.sleep()` in new tests.

## Commit convention

We follow the Angular conventional-commit format:

```
<type>(<scope>): <short subject>

<body> (optional)

<footer> (optional)
```

Allowed types:

| Type | Use for |
|------|---------|
| `feat` | A new feature or primitive |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `perf` | Performance improvement |
| `chore` | Tooling, build scripts, metadata |

Examples:

```
feat(ratelimit): add sliding window limiter
fix(circuitbreaker): prevent duplicate half-open probes
docs: add Traditional Chinese README
```

## Pull request checklist

- [ ] Tests added/updated and the full suite passes.
- [ ] Public symbols have docstrings and type annotations.
- [ ] README updated if behaviour or API changed.
- [ ] Commits follow the convention above.
- [ ] No third-party dependencies introduced.
- [ ] No copied source code from other projects — original implementation only.

## Reporting bugs

Open an issue with:

1. Python version and OS.
2. A minimal code snippet that reproduces the problem.
3. Expected vs actual behaviour.

## Code of conduct

Be respectful and constructive. Assume good intent, give specific feedback, and keep discussions focused on the technical merit of the change.

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
