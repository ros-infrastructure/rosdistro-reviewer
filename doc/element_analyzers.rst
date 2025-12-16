Writing Element Analyzers
=========================

Element Analyzers are plugins for `rosdistro-reviewer` that analyze changes in a git repository and provide feedback. They are the primary mechanism for extending the functionality of `rosdistro-reviewer` with new checks.

Each analyzer is responsible for a specific type of analysis, such as linting, style checking, or validating the structure of specific files.

Creating a New Analyzer
-----------------------

To create a new Element Analyzer, you need to:

1.  Create a new class that inherits from :py:class:`rosdistro_reviewer.element_analyzer.ElementAnalyzerExtensionPoint`.
2.  Implement the :py:meth:`~.ElementAnalyzerExtensionPoint.analyze` in your class.
3.  Register your class as a plugin in your `setup.cfg` file.

The `analyze` method
~~~~~~~~~~~~~~~~~~~~

The :py:meth:`~.ElementAnalyzerExtensionPoint.analyze` is the entry point for your analyzer. It has the following signature:

.. code-block:: python

   def analyze(
       self,
       path: Path,
       target_ref: Optional[str] = None,
       head_ref: Optional[str] = None,
   ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:

*   `path`: A `pathlib.Path` object pointing to the root of the git repository.
*   `target_ref`: The git ref of the base of the comparison (e.g., the target branch of a pull request).
*   `head_ref`: The git ref of the head of the comparison (e.g., the source branch of a pull request).

The method should return a tuple containing a list of `Criterion` objects and a list of `Annotation` objects. If no analysis is performed, it can return `(None, None)`.

Plugin Registration
~~~~~~~~~~~~~~~~~~~

To register your analyzer, add it to the `rosdistro_reviewer.element_analyzer` entry point group in your `setup.cfg` file:

.. code-block:: ini

   [options.entry_points]
   rosdistro_reviewer.element_analyzer =
       my_analyzer = my_package.my_module:MyAnalyzer

Review Data Structures
----------------------

Analyzers use three main data structures to represent the :py:class:`~.rosdistro_reviewer.review.Recommendation`, :py:class:`~.rosdistro_reviewer.review.Criterion`, and :py:class:`~.rosdistro_reviewer.review.Annotation`. These are all defined in the :py:mod:`rosdistro_reviewer.review` module.

Recommendation
~~~~~~~~~~~~~~

The :py:class:`~.rosdistro_reviewer.review.Recommendation` is an `IntEnum` that represents the overall outcome of a criterion. It has three possible values:

*   :py:attr:`Recommendation.APPROVE`: The changes satisfy the criterion.
*   :py:attr:`Recommendation.NEUTRAL`: The changes are not applicable to the criterion, or the analysis is inconclusive.
*   :py:attr:`Recommendation.DISAPPROVE`: The changes do not satisfy the criterion and need to be addressed.

Criterion
~~~~~~~~~

A :py:class:`~.rosdistro_reviewer.review.Criterion` is a `namedtuple` that represents a single check performed by the analyzer. It has two fields:

*   `recommendation`: A `Recommendation` enum value.
*   `rationale`: A string explaining the reason for the recommendation.

.. code-block:: python

   from rosdistro_reviewer.review import Criterion
   from rosdistro_reviewer.review import Recommendation

   criteria.append(Criterion(
       Recommendation.APPROVE,
       'All new files have a license header.'
   ))

Annotation
~~~~~~~~~~

An :py:class:`~.rosdistro_reviewer.review.Annotation` is a `namedtuple` used to attach a message to a specific line or range of lines in a file. This is useful for providing detailed feedback directly on the code. It has three fields:

*   `file`: The path to the file being annotated.
*   `lines`: A `range` object specifying the line number(s) for the annotation.
*   `message`: The feedback message.

.. code-block:: python

   from rosdistro_reviewer.review import Annotation

   annotations.append(Annotation(
       'path/to/my/file.py',
       range(10, 11),  # This annotates line 10
       'This line has a style issue.'
   ))

Accessing Git Changes
---------------------

The :py:mod:`rosdistro_reviewer.git_lines` module provides a helper function, :py:func:`~.rosdistro_reviewer.git_lines.get_added_lines` to get the lines that were added in a set of files between two git refs. This is often the primary input for an analyzer.

.. code-block:: python

   from rosdistro_reviewer.git_lines import get_added_lines

   changed_files = ["path/to/my/file.py"]
   added_lines = get_added_lines(
       path,
       target_ref=target_ref,
       head_ref=head_ref,
       paths=changed_files
   )
   # added_lines is a mapping of file paths to line ranges

Accessing Changed YAML Data
---------------------------

For analyzing changes in YAML files, the :py:mod:`rosdistro_reviewer.yaml_changes` module provides a more powerful alternative to ``get_added_lines``. The :py:func:`~.rosdistro_reviewer.yaml_changes.get_changed_yaml` function returns a dictionary representation of a YAML file, but with a special ``__lines__`` attribute attached to every node.

This is a two-step process:

1.  First, call :py:func:`~.rosdistro_reviewer.yaml_changes.get_changed_yaml`. This function loads the YAML file using a special loader that annotates every node (mappings, sequences, and scalars) with the line range it occupies in the source file. It then identifies which nodes were part of an added line and marks all other nodes by setting their ``__lines__`` attribute to ``None``.

2.  Next, call :py:func:`~.rosdistro_reviewer.yaml_changes.prune_changed_yaml` on the data returned by :py:func:`~.rosdistro_reviewer.yaml_changes.get_changed_yaml`. This function recursively removes any nodes from the dictionary where the ``__lines__`` attribute is ``None``, leaving you with a dictionary containing only the parts of the YAML file that have changed.

.. code-block:: python

   from rosdistro_reviewer.yaml_changes import get_changed_yaml
   from rosdistro_reviewer.yaml_changes import prune_changed_yaml

   yaml_files = ['path/to/my/file.yaml']
   changed_yaml = get_changed_yaml(
       path,
       yaml_files,
       target_ref=target_ref,
       head_ref=head_ref,
   )

   if changed_yaml:
       for file_path, yaml_data in changed_yaml.items():
           prune_changed_yaml(yaml_data)
           # The 'yaml_data' dict now contains only the changed parts of the YAML

Example Analyzer
----------------

Here is a simplified example of an analyzer that checks for the presence of "TODO" in new code:

.. code-block:: python

   from pathlib import Path
   from typing import List
   from typing import Optional
   from typing import Tuple

   from git import Repo
   from rosdistro_reviewer.element_analyzer import ElementAnalyzerExtensionPoint
   from rosdistro_reviewer.git_lines import get_added_lines
   from rosdistro_reviewer.review import Annotation
   from rosdistro_reviewer.review import Criterion
   from rosdistro_reviewer.review import Recommendation

   class TodoChecker(ElementAnalyzerExtensionPoint):
       """Checks for the presence of 'TODO' in new code."""

       def analyze(
           self,
           path: Path,
           target_ref: Optional[str] = None,
           head_ref: Optional[str] = None,
       ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
           """Perform analysis for TODOs."""
           criteria: List[Criterion] = []
           annotations: List[Annotation] = []
           recommendation = Recommendation.APPROVE

           # Get all python files in the repo
           py_files = [str(p.relative_to(path)) for p in path.glob('**/*.py')]
           added_lines = get_added_lines(
               path, target_ref=target_ref, head_ref=head_ref, paths=py_files)

           if not added_lines:
               return None, None

           with Repo(path) as repo:
               for file_path, line_ranges in added_lines.items():
                   blob = repo.tree(head_ref)[file_path]
                   lines = blob.data_stream.read().decode().splitlines()
                   for line_range in line_ranges:
                       for line_num in line_range:
                           if 'TODO' in lines[line_num - 1]:
                               recommendation = Recommendation.DISAPPROVE
                               annotations.append(Annotation(
                                   file_path,
                                   range(line_num, line_num + 1),
                                   "Found 'TODO' in new code."
                               ))

           if recommendation == Recommendation.DISAPPROVE:
               rationale = "New code should not contain 'TODO' markers."
           else:
               rationale = "No 'TODO' markers found in new code."

           criteria.append(Criterion(recommendation, rationale))
           return criteria, annotations
