# Changelog

## Unreleased

- Require BONDI `>=0.4.0,<0.5.0`; the starter needs no connection API changes.

## 0.2.0 — 2026-11-19

- Return greeting strings from `hello_world()` and update the CLI, experiment, notebook, and tests.
- Plot greeting lengths in the example notebook.

- Refresh the lockfile, align the experiment test with its metric, and fix documentation links and references.

- Add pytest and Ruff descriptions and documentation links to Dependencies.

- Move tool explanations into a Dependencies page and include Zensical.

- Add a Getting started guide for feature branches, checks, pull requests, and reviews.

- Add uv and pip tabs for reinstalling the renamed project.

- Explain how to preview documentation, view saved changes, and stop the local server.

- Group installation, dependencies, renaming, Git workflow, functionality, documentation,
  and progress instructions under User guide. Add an API reference and presentation examples.

- Upgrade relcon-docs to 0.1.7 and apply shared Markdown defaults, including SmartSymbols arrows.

- Document the hello module's arguments and return values with Google-style
  docstrings and explain API reference sections.

- Upgrade relcon-docs to 0.1.2 and replace Results and standalone slide tooling
  with a final Progress tab, a presentation-mode template and an empty Week 1 page.

- Inherit shared image lightboxes and allow relcon-docs updates within
  `>=0.1.0,<1.0.0`, retaining the lockfile for reproducible documentation builds.

- Install relcon-docs 0.1.0 from PyPI and enable shared heading permalinks.

- Update relcon-docs to inherit alphabetical API members and exclude private members.

- Update relcon-docs defaults and deployment workflow; inherit equation rendering,
  diagram accent colours and dark-mode Markdown copy controls.

- Use shared light/dark diagram colours from relcon-docs.

- Inherit callouts, collapsible notes and Mermaid support from relcon-docs.

- Inherit Markdown exports and llms.txt directly from relcon-docs, removing
  duplicate project-level export configuration.

- Adopt relcon-docs through a dedicated docs dependency group and inherited YAML
  configuration, retaining Mermaid styling and project-specific API headings.
- Enable Markdown exports and llms.txt, and reuse the shared Pages workflow
  while preserving push-to-main and manual deployment after CI succeeds.

- Add a Zensical documentation scaffold, API reference and GitHub workflows.
- Upgrade to BONDI 0.3.1 and Yanex 0.7.0.
- Update BONDI deployment commands to the current CLI.
