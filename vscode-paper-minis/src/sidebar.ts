import * as vscode from "vscode";

export class PaperMinisSidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "paper-minis-sidebar";

  private _view?: vscode.WebviewView;

  resolveWebviewView(webviewView: vscode.WebviewView): void | Thenable<void> {
    this._view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
    };

    webviewView.webview.html = this._getHtml();

    webviewView.onDidDispose(() => {
      this._view = undefined;
    });

    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.type) {
        case "generate": {
          const text = (message.text ?? "").trim();
          const title = (message.title ?? "").trim();
          if (!text) {
            vscode.window.showWarningMessage("Enter a roster or natural-language request before generating.");
            return;
          }

          try {
            const result = (await vscode.commands.executeCommand("paper-minis.buildFromPrompt", text, title)) as any;
            if (result && result.error) {
              vscode.window.showErrorMessage(String(result.error));
            }
          } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            vscode.window.showErrorMessage(`Build failed: ${msg}`);
          }
          return;
        }
      }
    });
  }

  private _getHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      body {
        padding: 12px;
        font-family: var(--vscode-font-family);
        background: var(--vscode-sideBar-background);
        color: var(--vscode-foreground);
      }
      textarea, input, button {
        width: 100%;
        box-sizing: border-box;
        margin-top: 8px;
        border-radius: 6px;
        border: 1px solid var(--vscode-input-border, #3c3c3c);
        background: var(--vscode-input-background, #1e1e1e);
        color: var(--vscode-input-foreground, #ffffff);
        padding: 8px 10px;
      }
      textarea {
        min-height: 160px;
        resize: vertical;
      }
      button {
        cursor: pointer;
        background: var(--vscode-button-background, #0e639c);
        color: var(--vscode-button-foreground, #ffffff);
        border: none;
        font-weight: 600;
      }
      label {
        display: block;
        margin-top: 10px;
        font-size: 12px;
        opacity: 0.9;
      }
      .hint {
        font-size: 11px;
        opacity: 0.75;
        margin-top: 8px;
      }
    </style>
  </head>
  <body>
    <h3>Paper Minis</h3>
    <label>Roster or prompt</label>
    <textarea id="roster" placeholder="7 goblins\n3 wolves\n1 ogre\n\nOr: Build me a mini set for tonight's session..."></textarea>

    <label>Title (optional)</label>
    <input id="title" placeholder="Phandelver or Tonight's Encounter" />

    <button id="generateBtn">Build minis</button>
    
    <label style="margin-top: 14px;">Quick Encounter Presets</label>
    <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;">
      <button type="button" class="presetBtn" data-title="Sci-Fi Outpost Siege" data-roster="1 Officer ShreakAnth (Heavy Duty Officer) # size=medium\n1 Trisha (Medical Support) # size=medium\n1 Oscar (Loyal Dog) # size=small\n1 Prajwal (Heavy Gun Operator) # size=medium\n1 Pixelpebble (Combat Engineer) # size=medium\n10 Facehugger # size=small\n3 Alien Egg # size=tiny\n7 Mature Alien # size=medium\n4 Alien Creeper # size=medium\n1 Big Queen # size=huge" style="background: var(--vscode-button-secondaryBackground, #3a3d41); padding: 5px; font-size: 11px;">Sci-Fi Siege</button>
      <button type="button" class="presetBtn" data-title="Goblin Ambush" data-roster="7 Goblins\n3 Wolves\n1 Ogre" style="background: var(--vscode-button-secondaryBackground, #3a3d41); padding: 5px; font-size: 11px;">Goblin Ambush</button>
      <button type="button" class="presetBtn" data-title="Undead Crypt" data-roster="12 Skeletons\n4 Zombies\n1 Lich" style="background: var(--vscode-button-secondaryBackground, #3a3d41); padding: 5px; font-size: 11px;">Undead Crypt</button>
    </div>

    <div class="hint">Natural-language requests are optionally turned into a roster using Gemini.</div>

    <script>
      const vscode = acquireVsCodeApi();
      const generateBtn = document.getElementById('generateBtn');
      generateBtn.addEventListener('click', () => {
        const text = document.getElementById('roster').value;
        const title = document.getElementById('title').value;
        vscode.postMessage({ type: 'generate', text, title });
      });

      document.querySelectorAll('.presetBtn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.getElementById('roster').value = btn.getAttribute('data-roster');
          document.getElementById('title').value = btn.getAttribute('data-title');
        });
      });
    </script>
  </body>
</html>`;
  }
}
