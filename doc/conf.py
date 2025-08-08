# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'rosdistro-reviewer'
copyright = '2025 Open Source Robotics Foundation, Inc'  # noqa: A001
author = 'Scott K Logan'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinxcontrib.apidoc',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'en'

# -- Options for API documentation -------------------------------------------
# https://github.com/sphinx-contrib/apidoc?tab=readme-ov-file#configuration

apidoc_module_dir = '../rosdistro_reviewer'
apidoc_toc_file = False

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_baseurl = 'https://ros-infrastructure.github.io/rosdistro-reviewer/'
html_domain_indices = False
html_use_index = False
