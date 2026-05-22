# rosdistro-reviewer - AI Agent Instructions

## Code Style & Architecture

- **Linters & Typings**: Python code style is enforced by `flake8` (using `google` import order style) and typed via `mypy`. Spell-checking is done via `scspell3k`. All of these checks are wrapped and executed as pytest test cases (see Testing section below).
- **YAML Linting**: YAML files are linted via `yamllint`.
- **Extensibility**: The project heavily relies on Python `entry_points` (built on `colcon-core` concepts) for plugins.
  - Custom checks/analyzers are registered under `rosdistro_reviewer.element_analyzer`.
  - Feedback mechanisms are registered under `rosdistro_reviewer.submitter`.
  - Environment variables are exposed via `rosdistro_reviewer.environment_variable`.

## Documentation & Contributing

- Developer documentation, including instructions on how to create new "Element Analyzers" (plugins for new checks/features), can be found in the `doc/` directory, particularly in `doc/element_analyzers.rst`.
- General contributing guidelines are available in `CONTRIBUTING.rst` (or `doc/contributing.rst`).
- **Build Docs**: To build documentation locally:
  ```bash
  python -m pip install .[doc,github]
  make -C doc html "SPHINXOPTS=--fail-on-warning --keep-going"
  ```

## Testing & Linting

The linters for this repository are implemented as tests. They can be selected or deselected using the `linter` pytest marker.

- **Run Functional Tests:**
  ```bash
  env PYTHONPATH=$PWD:$PYTHONPATH python3 -m pytest test -m 'not linter'
  ```

- **Run Linters:**
  ```bash
  env PYTHONPATH=$PWD:$PYTHONPATH python3 -m pytest test -m linter
  ```

- **Run All Tests & Linters:**
  ```bash
  env PYTHONPATH=$PWD:$PYTHONPATH python3 -m pytest test
  ```
