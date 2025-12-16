==================================
Contributing to rosdistro-reviewer
==================================

First off, thank you for considering contribution to `rosdistro-reviewer`.


Reporting Bugs and Requesting Features
======================================

If you encounter a bug or have a feature request, please `open an issue <https://github.com/ros-infrastructure/rosdistro-reviewer/issues>`_ on our GitHub repository. Before opening a new issue, please check to see if a similar one has already been reported.

When reporting a bug, please include as much detail as possible, including:

*   A clear and descriptive title.
*   Steps to reproduce the bug.
*   What you expected to happen.
*   What actually happened.
*   Your operating system and Python version.

Submitting Pull Requests
========================

If you'd like to contribute code to `rosdistro-reviewer`, we welcome your pull requests. Here's a quick guide:

1.  Fork the repository and create your branch from `main`.
2.  Make your changes. Try to keep your changes small and focused on a single feature or bug fix.
3.  Ensure your code is well-documented and follows the project's coding style.
4.  Add or update unit tests as appropriate.
5.  Open a `pull request <https://github.com/ros-infrastructure/rosdistro-reviewer/pulls>`_ with a clear title and description of your changes.

Running Tests and Linters
=========================

`rosdistro-reviewer` uses ``pytest`` to run unit tests and linters. Before submitting a pull request, please ensure that all tests and linters pass.

To run the full suite of tests and linters, simply run ``pytest`` from the root of the repository:

.. code-block:: console

    $ pytest

This will execute the unit tests and also run several linters to check for:

*   Code style (using `flake8`)
*   Type hint correctness (using `mypy`)
*   Correct copyright and license headers
*   Spelling in source files

If any of these checks fail, your pull request will not be able to be merged.
