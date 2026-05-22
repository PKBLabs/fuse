# Governance

Flexible User-extensible Simulation Editor (FUSE) is a maintainer-led
open-source project owned and maintained by PKB Research Labs, LLC.

## Maintainer authority

PKB Research Labs, LLC has final authority over:

- Project roadmap.
- Architecture and technical direction.
- Release planning.
- Branch strategy.
- Coding standards.
- Review requirements.
- Acceptance or rejection of contributions.
- Licensing strategy.
- Commercial licensing.
- Plugin API stability.
- Use of the FUSE name, logo, and branding.

## Community participation

Community members are encouraged to:

- Report bugs.
- Suggest features.
- Discuss design ideas.
- Submit pull requests.
- Improve documentation.
- Share modeling and simulation use cases.
- Test FUSE with supported frameworks.

Community participation does not grant merge rights, release authority, trademark
rights, or decision-making authority over the official project.

## Branches

`main` is the stable release branch.

`develop` is the integration branch for upcoming releases.

Feature branches may be used for individual changes.

Release branches may be used for release candidates.

Hotfix branches may be used for urgent fixes.

## Merge policy

All changes to protected branches must be reviewed and approved by the
maintainer or by maintainers explicitly authorized by PKB Research Labs, LLC.

Direct pushes to protected branches are not permitted except by authorized
maintainers.

## Plugin API governance

The FUSE Plugin API is a protected compatibility surface.

Changes to the public plugin API require maintainer approval and must include:

- A compatibility assessment.
- Updated plugin API documentation.
- Updated plugin API version, if required.
- Updated compatibility tests.
- Migration notes for plugin authors, if behavior changes.

Breaking changes to the public plugin API should only occur in a new major plugin
API version unless required for security, correctness, or legal reasons.