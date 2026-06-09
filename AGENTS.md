# rosdistro-reviewer - AI Agent Instructions

## Role & Objective

You are an expert Python developer and automation agent specialized in ROS (Robot Operating System) infrastructure tooling. Your objective is to maintain and extend `rosdistro-reviewer`, a tool designed to analyze git repositories (such as [ros/rosdistro](https://github.com/ros/rosdistro) containing changes to a rosdistro index (defined by [REP-0153](https://reps.openrobotics.org/rep-0153/)) or rosdep database (defined by [REP-0111](https://reps.openrobotics.org/rep-0111/)) and provide actionable feedback.

## Repository Structure & Organization

Below is a brief overview of the project's layout:

- **`doc/`**: Developer and user documentation.
- **`rosdistro_reviewer/`**: Core Python package containing the CLI tool, element analyzers, and submitters.
  - `element_analyzer/`: Plugin directory for checks on the repository elements (e.g., `rosdep`, `rosdistro`, `yamllint`).
  - `submitter/`: Feedback mechanisms to report review results (e.g., GitHub PR comments).
  - `verb/`: Verbs/subcommands for the command-line tool.
- **`test/`**: Comprehensive pytest-based test suite and linter wrappers.

## Strict Guardrails & Code Style

- **Copyright & License Headers**: EVERY new Python or configuration file must include the standard Apache-2.0 copyright header block at the absolute top. Failure to include this will break the test suite.
- **Linters & Typings**: Python code style is strictly enforced.
  - Style: `flake8` utilizing the `google` import order style.
  - Type Hints: 100% type annotations are required and validated via `mypy`.
  - Spelling: Validated via `scspell3k`.
- **YAML Linting**: Any YAML files or test fixtures must pass `yamllint`.
- **Extensibility**: The project heavily relies on Python `entry_points` (built on `colcon-core` concepts) for plugins, which are configured in `setup.cfg`.
  - Custom checks/analyzers are registered under `rosdistro_reviewer.element_analyzer`.
  - Feedback mechanisms are registered under `rosdistro_reviewer.submitter`.
  - Environment variables are exposed via `rosdistro_reviewer.environment_variable`.

## Documentation & Contributing

- Developer documentation, including instructions on how to create new "Element Analyzers" (plugins for new checks/features), can be found in the `doc/` directory, particularly in `doc/element_analyzers.rst`.
- General contributing guidelines are available in `CONTRIBUTING.rst`.
- **Build Docs**: To build documentation locally:
  ```bash
  python -m pip install .[doc,github]
  make -C doc html "SPHINXOPTS=--fail-on-warning --keep-going"
  ```

## Local Execution

You can run the CLI tool locally as a Python module without installation by setting the `PYTHONPATH`:

- **Run Review Local Command:**
  ```bash
  env PYTHONPATH=$PWD:$PYTHONPATH python3 -m rosdistro_reviewer
  ```

- **Run with Specific Commit-ish Refs:**
  ```bash
  env PYTHONPATH=$PWD:$PYTHONPATH python3 -m rosdistro_reviewer --target-ref main --head-ref feature-branch
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
