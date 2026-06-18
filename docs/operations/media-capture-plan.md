# Media Capture Plan

This page tracks every planned screenshot or video placeholder in the MkDocs site.

All placeholders are intentionally marked with `FUSE-MEDIA-TODO` so they are easy to find:

```bash
grep -R "FUSE-MEDIA-TODO" docs
```

Store screenshots under:

```text
docs/assets/screenshots/
```

Store videos or animated captures under:

```text
docs/assets/videos/
```

Prefer filenames that match this plan. If a capture shows local paths, usernames, hostnames, private repositories, tokens, or private simulator installations, retake or crop the capture before committing it.

## Required screenshots

| ID | Asset path | Target file | What to capture |
|---|---|---|---|
| `home-hero` | `docs/assets/screenshots/main-window-empty.png` | `docs/index.md` | Clean first launch with empty canvas, palette, properties panel, and validation/status areas visible. |
| `install-release-artifact` | `docs/assets/screenshots/release-artifact-download.png` | `docs/user/installation.md` | GitHub release page or artifact list showing where a user downloads FUSE. |
| `install-first-launch` | `docs/assets/screenshots/first-launch-after-install.png` | `docs/user/installation.md` | FUSE launched from an installed/release artifact. |
| `quickstart-main-window` | `docs/assets/screenshots/main-window-empty.png` | `docs/user/quickstart.md` | Same clean main-window capture as `home-hero`, reused in quickstart. |
| `quickstart-example-open` | `docs/assets/screenshots/example-project-open.png` | `docs/user/quickstart.md` | Example project opened successfully. |
| `user-main-window` | `docs/assets/screenshots/main-window-annotated.png` | `docs/user/user-guide.md` | Main window with major areas visible. Later annotate or caption palette/canvas/properties/status regions. |
| `user-project-settings` | `docs/assets/screenshots/project-settings.png` | `docs/user/user-guide.md` | Project Settings dialog with framework/plugin target controls visible. |
| `user-component-palette` | `docs/assets/screenshots/component-palette-sst.png` | `docs/user/user-guide.md` | Component palette with SST or gem5 components visible. |
| `workflow-project-settings` | `docs/assets/screenshots/project-settings-target-selection.png` | `docs/user/model-editor-workflow.md` | Project Settings focused on plugin enablement and target/catalog selection. |
| `workflow-component-on-canvas` | `docs/assets/screenshots/component-on-canvas.png` | `docs/user/model-editor-workflow.md` | One framework component placed on the canvas. |
| `workflow-connected-components` | `docs/assets/screenshots/connected-components.png` | `docs/user/model-editor-workflow.md` | Two or more compatible components connected by visible links. |
| `workflow-export-dialog` | `docs/assets/screenshots/export-dialog.png` | `docs/user/model-editor-workflow.md` | Export menu/dialog or export destination prompt. |
| `properties-selected-component` | `docs/assets/screenshots/properties-editor-component.png` | `docs/user/properties-and-validation.md` | Selected component with Object and Parameters sections visible. |
| `validation-error` | `docs/assets/screenshots/validation-panel-error.png` | `docs/user/properties-and-validation.md` | Validation panel showing at least one actionable error or warning. |
| `validation-success` | `docs/assets/screenshots/validation-panel-success.png` | `docs/user/properties-and-validation.md` | Validation panel after a model passes validation. |
| `composite-selection` | `docs/assets/screenshots/composite-selection.png` | `docs/user/composite-components.md` | Multiple selected components before creating a composite. |
| `composite-instance` | `docs/assets/screenshots/composite-instance.png` | `docs/user/composite-components.md` | Resulting composite component instance on the main canvas. |
| `composite-edit-tab` | `docs/assets/screenshots/composite-edit-tab.png` | `docs/user/composite-components.md` | Composite template/instance editor showing the internal mini-model. |
| `sst-export-dialog` | `docs/assets/screenshots/sst-json-export-dialog.png` | `docs/plugins/sst/sst-json-export-guide.md` | SST JSON export action, destination chooser, or export result panel. |
| `gem5-export-dialog` | `docs/assets/screenshots/gem5-python-export-dialog.png` | `docs/plugins/gem5/gem5-plugin.md` | gem5 Python export action, destination chooser, or export result panel. |
| `toolchain-config` | `docs/assets/screenshots/toolchain-configuration.png` | `docs/user/user-guide.md`, `docs/user/installation.md` | Local/SSH toolchain configuration controls, with private host/path values removed. |

## Recommended videos or animated captures

| ID | Asset path | Target file | What to capture |
|---|---|---|---|
| `video-first-model` | `docs/assets/videos/first-model-workflow.mp4` | `docs/user/quickstart.md` | Short end-to-end flow: launch FUSE, open/create project, add component, connect, validate, save. |
| `video-composite-workflow` | `docs/assets/videos/composite-workflow.mp4` | `docs/user/composite-components.md` | Select components, create composite, place instance, open composite editor, expose a port. |
| `video-validation-export` | `docs/assets/videos/validation-and-export.mp4` | `docs/user/model-editor-workflow.md` | Run validation, fix/acknowledge issue, export to SST JSON or gem5 Python. |

## Placeholder format

Use this format when adding a new placeholder:

```markdown
<!-- FUSE-MEDIA-TODO id=short-unique-id type=screenshot path=assets/screenshots/example.png -->
> **Media TODO (short-unique-id)**: Describe the exact screenshot or video to add.
> Planned asset: `assets/screenshots/example.png`
```

When replacing a placeholder with a real image, keep a short caption near the image and remove the `FUSE-MEDIA-TODO` comment.
