# Paper Minis VS Code Extension

A lightweight VS Code extension that wraps the `paper-minis` build pipeline.

## Features

- Build printable mini sheets from a roster in the active editor
- Build from a selected block of text
- Build from a prompt box
- Output to a local workspace folder such as `.paper-minis-output`

## Usage

1. Open a roster file or select a roster block.
2. Run `Paper Minis: Build from active file`, `Build from selection`, or `Build from prompt`.
3. The extension runs the Python generator in the project and writes output to the workspace.

## Local development

```bash
npm install
npm run compile
```

Then run the extension in VS Code with the Extension Development Host.
