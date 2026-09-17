# The install documentation, executable.
#
# Every install command below is copied VERBATIM from README.md's "Install"
# section, and tests/test_install_docs.py asserts that correspondence (and that
# it extracted a non-zero number of commands, so a renamed heading fails loudly
# rather than silently checking nothing). The two cannot drift.
#
# THE ONLY SUBSTITUTIONS are the two commands that get the source into place:
#     git clone https://github.com/EricssonResearch/yang-to-rdf.git
#         -> COPY . .        (so the image builds before publication, and in CI
#                             where the commit under test is not yet pushed)
#     cd yang-to-rdf
#         -> WORKDIR /yang-to-rdf
# Nothing else differs, and tests/test_install_docs.py asserts both that these two
# are declared here and that every OTHER command appears verbatim below.
#
# Build and run:
#     docker build -t yang-to-rdf .
#     docker run --rm -v "$PWD/examples:/yang-to-rdf/examples:ro" yang-to-rdf
#
# examples/ is excluded by .dockerignore to keep the image small, so the
# reproducibility stage needs it mounted; without the mount that stage FAILS
# with a message saying so, rather than skipping quietly.
FROM python:3.12-slim

# ca-certificates: fetching the pinned YANG set from forge.3gpp.org over TLS.
# git: the provenance stage records HEAD and whether the tree is dirty.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

# Pinned uv, so the image itself is reproducible rather than tracking latest.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

WORKDIR /yang-to-rdf

# .dockerignore excludes .git, so `git rev-parse` cannot work inside the image.
# Pass the revision in so the provenance stage can still say what it measured.
# Without these the report records head="unknown" and dirty=null, and the
# provenance line says "cleanliness UNKNOWN" rather than implying a clean build:
#   docker build -t yang-to-rdf \
#     --build-arg GIT_HEAD="$(git rev-parse HEAD)" \
#     --build-arg GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)" \
#     --build-arg GIT_DIRTY="$(test -n "$(git status --porcelain)" && echo 1 || echo 0)" .
ARG GIT_HEAD=""
ARG GIT_BRANCH=""
ARG GIT_DIRTY=""
ENV Y2R_GIT_HEAD=${GIT_HEAD} \
    Y2R_GIT_BRANCH=${GIT_BRANCH} \
    Y2R_GIT_DIRTY=${GIT_DIRTY}

# Substitutes for the README's `git clone` + `cd` (see the note above).
COPY . .

# Verbatim from README.md "Install".
RUN uv sync --locked

# `git status` inside the image would otherwise report the tree as untrusted.
RUN git config --global --add safe.directory /yang-to-rdf

# One entry point, all stages. Arguments pass through, e.g. `--offline`.
ENTRYPOINT ["uv", "run", "python", "-m", "scripts.verify"]
CMD []
