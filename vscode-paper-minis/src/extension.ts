import * as vscode from "vscode";
import { buildFromText, generateRosterFromPrompt } from "./minisService";
import { PaperMinisSidebarProvider } from "./sidebar";

export function activate(context: vscode.ExtensionContext) {
  const sidebarProvider = new PaperMinisSidebarProvider();

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(PaperMinisSidebarProvider.viewType, sidebarProvider),
    vscode.commands.registerCommand("paper-minis.build", async () => {
      await buildFromDocument();
    }),
    vscode.commands.registerCommand("paper-minis.buildFromSelection", async () => {
      await buildFromSelection();
    }),
    vscode.commands.registerCommand("paper-minis.buildFromPrompt", async (rawText?: string, rawTitle?: string) => {
      await buildFromPrompt(rawText, rawTitle);
    }),
    vscode.commands.registerCommand("paper-minis.openSidebar", () => {
      vscode.commands.executeCommand("workbench.view.extension.paper-minis");
    })
  );
}

export function deactivate() {
  // no-op
}

async function buildFromDocument() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a roster file to build minis.");
    return;
  }

  const text = editor.document.getText();
  if (!text.trim()) {
    vscode.window.showWarningMessage("The active document is empty.");
    return;
  }

  await buildRoster(text);
}

async function buildFromSelection() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a roster file and select some text first.");
    return;
  }

  const selection = editor.selection;
  const text = editor.document.getText(selection);
  if (!text.trim()) {
    vscode.window.showWarningMessage("The current selection is empty.");
    return;
  }

  await buildRoster(text);
}

async function buildFromPrompt(rawText?: string, rawTitle?: string) {
  let text = rawText?.trim();
  let title = rawTitle?.trim();

  if (!text) {
    const promptText = await vscode.window.showInputBox({
      prompt: "Describe the roster in plain English or paste a roster directly",
      placeHolder: "7 goblins, 3 wolves, 1 ogre",
      ignoreFocusOut: true,
    });

    if (!promptText || !promptText.trim()) {
      return;
    }

    text = promptText.trim();
  }

  if (!title) {
    title = await vscode.window.showInputBox({
      prompt: "Optional title for the generated sheet",
      placeHolder: "Phandelver or Tonight's Encounter",
      ignoreFocusOut: true,
    });
  }

  let rosterText = text;
  const isLikelyRoster = /\d+\s+\w+|\w+\s+\d+/.test(text) && !/[!?]/.test(text);
  if (!isLikelyRoster) {
    try {
      rosterText = await generateRosterFromPrompt(text);
      if (!rosterText || !rosterText.trim()) {
        throw new Error("Gemini returned empty roster text.");
      }
      vscode.window.showInformationMessage("Gemini converted your prompt into a roster.");
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      vscode.window.showWarningMessage(`Gemini conversion unavailable: ${msg}. Building from the raw input instead.`);
    }
  }

  await buildRoster(rosterText, title || undefined);
}

async function buildRoster(text: string, title?: string) {
  const result = await buildFromText(text, title || undefined);

  if (result.code === 0) {
    const output = result.stdout || result.stderr || "Build succeeded.";
    const outPath = result.outDir;
    vscode.window.showInformationMessage(`Paper Minis build succeeded. Output: ${outPath}`);
    const document = await vscode.workspace.openTextDocument({
      content: output,
      language: "plaintext",
    });
    await vscode.window.showTextDocument(document, { preview: false });
  } else {
    const details = [result.stderr, result.stdout].filter(Boolean).join("\n");
    vscode.window.showErrorMessage(`Paper Minis build failed. ${details || "No output returned."}`);
  }
}
