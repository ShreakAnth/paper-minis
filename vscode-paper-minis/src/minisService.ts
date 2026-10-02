import * as fs from "fs/promises";
import * as path from "path";
import * as vscode from "vscode";
import { spawn } from "child_process";
import { GoogleGenerativeAI } from "@google/generative-ai";

export async function buildFromText(rosterText: string, title?: string): Promise<{ code: number; stdout: string; stderr: string; outDir: string }> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
  const repoRoot = path.resolve(__dirname, "..", "..");
  const scriptPath = path.join(repoRoot, "paper-minis", "scripts", "build_minis.py");
  const userOutputFolder = vscode.workspace.getConfiguration("paperMinis").get<string>("outputFolder") ?? ".paper-minis-output";
  const outDir = path.isAbsolute(userOutputFolder)
    ? userOutputFolder
    : path.join(workspaceFolder, userOutputFolder);
  const rosterPath = path.join(workspaceFolder, ".paper-minis-roster.txt");

  await fs.mkdir(path.dirname(rosterPath), { recursive: true });
  await fs.writeFile(rosterPath, rosterText, "utf8");

  const pythonCommand = process.platform === "win32" ? "python" : "python3";
  const args = [
    scriptPath,
    rosterPath,
    "--out",
    outDir,
    ...(title ? ["--title", title] : [])
  ];

  const result = await spawnProcess(pythonCommand, args, workspaceFolder);

  return {
    ...result,
    outDir,
  };
}

export async function generateRosterFromPrompt(prompt: string): Promise<string> {
  const key = vscode.workspace.getConfiguration("paperMinis").get<string>("geminiApiKey");
  if (!key || !key.trim()) {
    throw new Error("Set paperMinis.geminiApiKey in VS Code settings before using Gemini generation.");
  }

  const genAI = new GoogleGenerativeAI(key);
  const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

  const instructedPrompt = `Convert this natural-language roster request into a clean roster text that matches the project's expected format. Output only plain roster text like:\n\n7 Goblins\n3 Wolves\n1 Ogre\n\nRules:\n- One line per creature or a count plus name\n- Do not add commentary\n- Preserve names exactly as asked\n- If the request is vague, infer a reasonable roster but keep it simple\n- Prefer monster names in the same style as D&D roster files\n\nRequest:\n${prompt}`;

  const res = await model.generateContent(instructedPrompt);
  const text = await res.response.text();

  return text.trim();
}

function spawnProcess(command: string, args: string[], cwd: string): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd,
      shell: false,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      resolve({
        code: code ?? 1,
        stdout,
        stderr,
      });
    });
  });
}
