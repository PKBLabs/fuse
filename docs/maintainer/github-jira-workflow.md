# GitHub and Jira workflow

GitHub issues are the public intake and discussion layer. Jira is the maintainer planning and execution layer.

## When a GitHub issue becomes Jira work

Create a Jira work item when a GitHub issue is accepted for implementation, scheduled for a release, or needs internal decomposition.

## Labels

- `needs-triage`: issue has not been reviewed.
- `accepted`: maintainers agree the issue is valid and should be addressed.
- `tracked-in-jira`: a corresponding Jira work item exists.
- `needs-info`: maintainers need more information.
- `blocked`: work cannot proceed yet.

Recommended area labels:

- `area: ui`
- `area: composites`
- `area: sst`
- `area: gem5`
- `area: packaging`
- `area: docs`
- `area: ci`

## Linking Jira and GitHub work

Use the Jira issue key in branch names, commit messages, and pull request titles.

```bash
git checkout -b FUSE-123-add-docs-build-check
git commit -m "FUSE-123 Add documentation build workflow"
```

PR title:

```text
FUSE-123 Add documentation build workflow
```

Maintainer comment on the GitHub issue:

```text
Accepted and tracked internally as FUSE-123.
```

## Closing public issues

Close GitHub issues only when the fix is available in a public tagged release, unless the issue is a duplicate, invalid, or superseded.

Suggested closing comment:

```text
Fixed in FUSE v0.9.0.
```

## Automation recommendation

Start with manual triage plus passive Jira/GitHub linking. Do not automatically mirror every GitHub issue into Jira.

A later automation can use this rule:

```text
GitHub issue labeled accepted -> create Jira work item -> add tracked-in-jira -> comment with Jira key.
```
