# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

clean:
	@echo "Removing everything under 'api', 'doc', and '_build'..."
	-@rm -rf api doc _build

.PHONY: clean help Makefile

# Relative image paths are resolved from the index. In order for this image to
# be usable in the repository README.rst as well as the sphinx-generated docs,
# we need to temporarily copy it.
doc/github_review.png:
	@mkdir -p doc
	cp -a github_review.png $@

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile doc/github_review.png
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
