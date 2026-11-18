# Pivoki on Linux

Pivoki opens local files and folders, previews the full target paths, and creates a package when you confirm the plan. The Library opens completed folders and keeps the latest 50 successful jobs. **Open Studio** opens the image and document tools and folder rules.

## Install

Use Python 3.11 or later with Tk and venv available. On Ubuntu these components are packaged as `python3-tk` and `python3-venv`. From the repository root, run:

```sh
linux/install.sh
~/.local/bin/pivoki-desktop
```

The installer creates a private virtual environment and installs a desktop entry under `~/.local/share/applications`. Use `--prefix` to select another user-owned directory. Use `--no-drop` for the chooser-only installation. The installer downloads Python dependencies. Image processing runs locally.

## Use

1. Choose **Files…** or **Folder…**, or drop local paths into the input list. **Include subfolders** starts off.
2. Select a saved package revision or a single output format. **Edit packages…** creates, revises, and deletes package definitions.
3. Choose a destination and conflict policy. **Preview plan** lists the source, original target, planned target and skipped items.
4. Select **Create approved outputs**. **Cancel** stops a job before publication. Use **Open output folder** or the Library to locate the finished files.

Ctrl+O opens the file chooser. Ctrl+Enter previews or confirms the displayed plan. Esc cancels a running job. The footer identifies the current session and available input method. On X11 the input list accepts Xdnd. On Wayland, an X11-backed Tk connects through XWayland and cross-application drops depend on the compositor’s integration. Keyboard commands work while Pivoki has focus.

Enabled folder rules run while the desktop or Studio is open. Set up rules in Studio.
