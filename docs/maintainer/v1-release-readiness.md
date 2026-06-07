# v1.0 release readiness

The v0.9.x release line prepares FUSE for the first stable v1.0 release. It should be intentionally focused on hardening, documentation, packaging, and release operations rather than major new modeling features.

## Deferred major capability

In-app creation of new SST and gem5 component definitions is deferred to a future major release, likely v2.0.0 or later.

## v0.9.x definition of done

- CI passes on the protected release branch.
- Documentation link checks pass.
- Doxygen/API docs build in CI.
- Release workflow can create source archives.
- Packaging workflow can produce at least Linux and Windows artifacts.
- Installation from source is documented and tested.
- Installation from release artifacts is documented.
- GitHub issue forms are present.
- Pull request template is present.
- GitHub-to-Jira workflow is documented.
- Public roadmap/project workflow is documented.
- Known limitations are documented.

## v1.0 definition of done

- A fresh user can install FUSE from a release artifact.
- A developer can set up from source using the docs.
- Example project opens successfully.
- Validation and export workflows are documented.
- SST path is documented and tested.
- gem5 path is documented and tested or clearly marked experimental.
- Release artifacts have checksums.
- Release notes are complete.
