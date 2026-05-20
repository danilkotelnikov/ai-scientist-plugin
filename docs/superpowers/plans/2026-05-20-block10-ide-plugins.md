# Block 10 — IDE Plugins (VS Code + JetBrains) Implementation Plan (§5.8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Ship two thin IDE clients that wrap the Vedix CLI / SaaS API: a **VS Code extension** (`vedix.vedix`) published to the VS Code Marketplace, and a **JetBrains plugin** (`vedix-jetbrains`) for IntelliJ / PyCharm / CLion / WebStorm published to the JetBrains Plugin Repository. Both share the same JSON-RPC surface from `orchestrator/hooks/ide_protocol.py` (Block 4).

**Architecture:** VS Code = TypeScript + the VS Code Extension API; JetBrains = Kotlin + the IntelliJ Platform SDK. Both speak HTTP to the Vedix.ai SaaS (for SaaS users) OR spawn the local `vedix` CLI as a subprocess (for plugin-only users). They expose: `Vedix: New Manuscript`, `Vedix: Switch Venue`, `Vedix: Run Reproducibility Audit`, a side-panel with job-progress view, a hover-on-citation provenance preview, and a status-bar cost-ledger.

**Tech Stack:**
- **VS Code:** TypeScript 5.4+, `@types/vscode`, `@vscode/test-cli`, `esbuild`, `vsce` (Marketplace publish)
- **JetBrains:** Kotlin 1.9+, IntelliJ Platform Gradle Plugin 2.0+, JUnit 5

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §5.8.

---

## File structure

```
plugins/vedix/ide/
├── vscode/
│   ├── package.json
│   ├── tsconfig.json
│   ├── esbuild.js
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── src/
│   │   ├── extension.ts        # activate / deactivate
│   │   ├── commands.ts         # Vedix: New Manuscript, Switch Venue, etc.
│   │   ├── progressPanel.ts    # WebView with job-progress view
│   │   ├── citationHover.ts    # HoverProvider for [@cite-key]
│   │   ├── statusBar.ts        # cost ledger month-to-date
│   │   ├── api.ts              # HTTP client to vedix.ai
│   │   └── cliRunner.ts        # spawn local `vedix` CLI when SaaS not configured
│   └── tests/
│       └── extension.test.ts
└── jetbrains/
    ├── build.gradle.kts
    ├── settings.gradle.kts
    ├── src/main/
    │   ├── kotlin/ai/vedix/jetbrains/
    │   │   ├── VedixToolWindowFactory.kt
    │   │   ├── NewManuscriptAction.kt
    │   │   ├── SwitchVenueAction.kt
    │   │   ├── ApiClient.kt
    │   │   └── CliRunner.kt
    │   └── resources/META-INF/
    │       └── plugin.xml
    └── src/test/
        └── kotlin/VedixPluginTest.kt
```

## Task 1: VS Code extension scaffolding

**Files:**
- Create: `plugins/vedix/ide/vscode/package.json`
- Create: `plugins/vedix/ide/vscode/src/extension.ts`
- Create: `plugins/vedix/ide/vscode/src/commands.ts`

- [ ] **Step 1: Initialize**

```bash
cd plugins/vedix/ide/vscode
npm init -y
npm install -D @types/vscode @types/node esbuild typescript @vscode/test-cli vsce
```

- [ ] **Step 2: package.json**

```json
{
  "name": "vedix",
  "displayName": "Vedix Research Workbench",
  "publisher": "vedix",
  "version": "3.0.0",
  "engines": { "vscode": "^1.95.0" },
  "main": "./dist/extension.js",
  "activationEvents": ["onStartupFinished"],
  "contributes": {
    "commands": [
      { "command": "vedix.newManuscript", "title": "Vedix: New Manuscript" },
      { "command": "vedix.switchVenue", "title": "Vedix: Switch Venue" },
      { "command": "vedix.reproducibilityAudit", "title": "Vedix: Run Reproducibility Audit" },
      { "command": "vedix.openPanel", "title": "Vedix: Open Progress Panel" }
    ],
    "configuration": {
      "title": "Vedix",
      "properties": {
        "vedix.saasBaseUrl": { "type": "string", "default": "https://api.vedix.ai", "description": "Vedix.ai SaaS API base URL" },
        "vedix.saasToken":   { "type": "string", "default": "",                       "description": "Vedix.ai JWT (leave empty to use local CLI)" },
        "vedix.useSaas":     { "type": "boolean","default": false,                    "description": "Route via Vedix.ai SaaS instead of local CLI" }
      }
    }
  },
  "scripts": {
    "compile": "node esbuild.js",
    "watch":   "node esbuild.js --watch",
    "package": "vsce package"
  }
}
```

- [ ] **Step 3: extension.ts**

```typescript
// src/extension.ts
import * as vscode from "vscode";
import { registerCommands } from "./commands";
import { registerStatusBar } from "./statusBar";
import { registerCitationHover } from "./citationHover";

export function activate(ctx: vscode.ExtensionContext) {
  console.log("Vedix activated");
  registerCommands(ctx);
  registerStatusBar(ctx);
  registerCitationHover(ctx);
}

export function deactivate() {}
```

- [ ] **Step 4: commands.ts**

```typescript
// src/commands.ts
import * as vscode from "vscode";
import { newJob, switchVenue, runReproAudit } from "./api";
import { openProgressPanel } from "./progressPanel";

export function registerCommands(ctx: vscode.ExtensionContext) {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("vedix.newManuscript", async () => {
      const topic = await vscode.window.showInputBox({ prompt: "Research topic", placeHolder: "e.g. solvent polarity on Diels-Alder kinetics" });
      if (!topic) return;
      const discipline = await vscode.window.showQuickPick(
        ["chemistry","biology","medicine","physics","mathematics","geology","computer_science","humanities"],
        { placeHolder: "Discipline" }
      );
      if (!discipline) return;
      const language = await vscode.window.showQuickPick(
        ["en","ru","es","de","fr","zh","ja"], { placeHolder: "Language" }
      );
      if (!language) return;
      const venue = await vscode.window.showInputBox({ prompt: "Venue", value: "preprint" });
      if (!venue) return;
      const r = await newJob({ topic, discipline, language, venue,
                                hypothesis_style: "exploratory", experiment_type: "computational",
                                primary_metric: "TBD", expected_direction: "increase", tolerance: 0.05 });
      vscode.window.showInformationMessage(`Vedix job ${r.job_id} queued`);
      openProgressPanel(ctx, r.job_id);
    }),

    vscode.commands.registerCommand("vedix.switchVenue", async () => {
      const venue = await vscode.window.showInputBox({ prompt: "Switch to venue (e.g. elsevier:cell-reports-medicine)" });
      if (!venue) return;
      const jobId = await vscode.window.showInputBox({ prompt: "Job ID" });
      if (!jobId) return;
      await switchVenue(jobId, venue);
      vscode.window.showInformationMessage(`Vedix venue switch: ${venue}`);
    }),

    vscode.commands.registerCommand("vedix.reproducibilityAudit", async () => {
      const jobId = await vscode.window.showInputBox({ prompt: "Job ID" });
      if (!jobId) return;
      const r = await runReproAudit(jobId);
      vscode.window.showInformationMessage(`Vedix audit ${r.status}: ${r.mismatches?.length ?? 0} mismatches`);
    }),

    vscode.commands.registerCommand("vedix.openPanel", async () => {
      const jobId = await vscode.window.showInputBox({ prompt: "Job ID" });
      if (jobId) openProgressPanel(ctx, jobId);
    }),
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/ide/vscode/package.json plugins/vedix/ide/vscode/src/extension.ts plugins/vedix/ide/vscode/src/commands.ts
git commit -m "feat(B10): VS Code extension scaffolding + commands"
```

## Task 2: VS Code — API client + CLI fallback

**Files:**
- Create: `plugins/vedix/ide/vscode/src/api.ts`
- Create: `plugins/vedix/ide/vscode/src/cliRunner.ts`

- [ ] **Step 1: api.ts**

```typescript
// src/api.ts
import * as vscode from "vscode";
import { runCli } from "./cliRunner";

function cfg() {
  const c = vscode.workspace.getConfiguration("vedix");
  return {
    base: c.get<string>("saasBaseUrl")!,
    token: c.get<string>("saasToken")!,
    useSaas: c.get<boolean>("useSaas")!,
  };
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const c = cfg();
  if (!c.useSaas) throw new Error("call() requires SaaS mode; use runCli() for CLI mode");
  const r = await fetch(`${c.base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${c.token}`, ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function newJob(setup: any): Promise<{ job_id: string }> {
  if (!cfg().useSaas) {
    return runCli(["new", "--topic", setup.topic, "--discipline", setup.discipline,
                   "--language", setup.language, "--venue", setup.venue]);
  }
  return call("/v1/api/jobs", { method: "POST", body: JSON.stringify(setup) });
}

export async function switchVenue(jobId: string, venue: string) {
  if (!cfg().useSaas) {
    return runCli(["switch", "venue", "--job", jobId, "--venue", venue]);
  }
  return call(`/v1/api/jobs/${jobId}/switch-venue`, { method: "POST", body: JSON.stringify({ venue }) });
}

export async function runReproAudit(jobId: string): Promise<{ status: string; mismatches: any[] }> {
  if (!cfg().useSaas) {
    return runCli(["audit-reproducibility", "--job", jobId]);
  }
  return call(`/v1/api/jobs/${jobId}/audit-reproducibility`, { method: "POST" });
}
```

- [ ] **Step 2: cliRunner.ts**

```typescript
// src/cliRunner.ts
import { spawn } from "node:child_process";

export function runCli<T = any>(args: string[]): Promise<T> {
  return new Promise((resolve, reject) => {
    const proc = spawn("vedix", args);
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", d => stdout += d.toString());
    proc.stderr.on("data", d => stderr += d.toString());
    proc.on("close", code => {
      if (code !== 0) return reject(new Error(`vedix exited ${code}: ${stderr}`));
      try {
        resolve(JSON.parse(stdout) as T);
      } catch {
        resolve({ raw: stdout } as T);
      }
    });
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/ide/vscode/src/api.ts plugins/vedix/ide/vscode/src/cliRunner.ts
git commit -m "feat(B10): VS Code — API client + CLI fallback"
```

## Task 3: VS Code — ProgressPanel, StatusBar, CitationHover

**Files:**
- Create: `plugins/vedix/ide/vscode/src/progressPanel.ts`
- Create: `plugins/vedix/ide/vscode/src/statusBar.ts`
- Create: `plugins/vedix/ide/vscode/src/citationHover.ts`

- [ ] **Step 1: progressPanel.ts**

```typescript
// src/progressPanel.ts
import * as vscode from "vscode";

export function openProgressPanel(ctx: vscode.ExtensionContext, jobId: string) {
  const panel = vscode.window.createWebviewPanel("vedixProgress", `Vedix job ${jobId.slice(0,8)}`, vscode.ViewColumn.Beside, { enableScripts: true });
  const c = vscode.workspace.getConfiguration("vedix");
  const base = c.get<string>("saasBaseUrl")!;
  const token = c.get<string>("saasToken")!;
  panel.webview.html = `
    <html><body style="font-family:monospace">
      <h3>Job ${jobId}</h3>
      <pre id="log"></pre>
      <script>
        const es = new EventSource("${base}/v1/api/jobs/${jobId}/events?token=${token}");
        const log = document.getElementById("log");
        es.onmessage = (e) => { log.innerText += "\\n" + e.data; window.scrollTo(0, document.body.scrollHeight); };
      </script>
    </body></html>`;
}
```

- [ ] **Step 2: statusBar.ts**

```typescript
// src/statusBar.ts
import * as vscode from "vscode";

export function registerStatusBar(ctx: vscode.ExtensionContext) {
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  item.text = "$(beaker) Vedix";
  item.command = "vedix.openPanel";
  item.show();
  ctx.subscriptions.push(item);

  // Optional: poll cost ledger every 5 minutes
  const c = vscode.workspace.getConfiguration("vedix");
  if (c.get<boolean>("useSaas")) {
    const update = async () => {
      try {
        const r = await fetch(`${c.get<string>("saasBaseUrl")}/v1/api/cost?since=30d`, {
          headers: { Authorization: `Bearer ${c.get<string>("saasToken")}` }
        });
        const d = await r.json() as { total_usd: number };
        item.text = `$(beaker) Vedix · $${d.total_usd.toFixed(2)}`;
      } catch {}
    };
    update();
    const interval = setInterval(update, 5 * 60 * 1000);
    ctx.subscriptions.push({ dispose: () => clearInterval(interval) });
  }
}
```

- [ ] **Step 3: citationHover.ts**

```typescript
// src/citationHover.ts
import * as vscode from "vscode";

export function registerCitationHover(ctx: vscode.ExtensionContext) {
  ctx.subscriptions.push(vscode.languages.registerHoverProvider(
    [{ language: "latex" }, { language: "markdown" }],
    {
      async provideHover(doc, pos) {
        const range = doc.getWordRangeAtPosition(pos, /\[@[\w:-]+\]|\\cite\{[\w:,-]+\}/);
        if (!range) return;
        const word = doc.getText(range);
        return new vscode.Hover(new vscode.MarkdownString(
          `**Vedix citation:** \`${word}\`\n\n- Click "Vedix: Open Provenance" to inspect this citation's load-bearing verdict (counterfactual probe).`
        ));
      }
    }
  ));
}
```

- [ ] **Step 4: Commit**

```bash
git add plugins/vedix/ide/vscode/src/progressPanel.ts plugins/vedix/ide/vscode/src/statusBar.ts plugins/vedix/ide/vscode/src/citationHover.ts
git commit -m "feat(B10): VS Code — ProgressPanel + StatusBar + CitationHover"
```

## Task 4: JetBrains plugin scaffolding

**Files:**
- Create: `plugins/vedix/ide/jetbrains/build.gradle.kts`
- Create: `plugins/vedix/ide/jetbrains/src/main/resources/META-INF/plugin.xml`
- Create: `plugins/vedix/ide/jetbrains/src/main/kotlin/ai/vedix/jetbrains/VedixToolWindowFactory.kt`

- [ ] **Step 1: build.gradle.kts**

```kotlin
// build.gradle.kts
plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.25"
    id("org.jetbrains.intellij.platform") version "2.0.1"
}

group = "ai.vedix"
version = "3.0.0"

repositories {
    mavenCentral()
    intellijPlatform { defaultRepositories() }
}

dependencies {
    intellijPlatform {
        intellijIdeaCommunity("2024.2.1")
        bundledPlugin("com.intellij.java")
        instrumentationTools()
    }
    testImplementation("junit:junit:4.13.2")
}

kotlin { jvmToolchain(17) }
```

- [ ] **Step 2: plugin.xml**

```xml
<idea-plugin>
  <id>ai.vedix.jetbrains</id>
  <name>Vedix Research Workbench</name>
  <vendor email="hello@vedix.ai" url="https://vedix.ai">Vedix</vendor>
  <description><![CDATA[
    Vedix turns a topic into a venue-ready manuscript via cross-host CLI orchestration.
    This plugin wraps the Vedix CLI / SaaS API. Bring your own API key.
  ]]></description>

  <depends>com.intellij.modules.platform</depends>

  <extensions defaultExtensionNs="com.intellij">
    <toolWindow id="Vedix" anchor="right" factoryClass="ai.vedix.jetbrains.VedixToolWindowFactory"/>
  </extensions>

  <actions>
    <action id="Vedix.NewManuscript" class="ai.vedix.jetbrains.NewManuscriptAction" text="Vedix: New Manuscript" description="Start a new Vedix research pipeline"/>
    <action id="Vedix.SwitchVenue" class="ai.vedix.jetbrains.SwitchVenueAction" text="Vedix: Switch Venue"/>
  </actions>
</idea-plugin>
```

- [ ] **Step 3: VedixToolWindowFactory.kt**

```kotlin
// src/main/kotlin/ai/vedix/jetbrains/VedixToolWindowFactory.kt
package ai.vedix.jetbrains

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import javax.swing.BoxLayout

class VedixToolWindowFactory : ToolWindowFactory {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = JBPanel<Nothing>().apply { layout = BoxLayout(this, BoxLayout.Y_AXIS) }
        panel.add(JBLabel("Vedix — research workbench"))
        panel.add(JBLabel("Use Actions menu: Vedix: New Manuscript"))
        toolWindow.component.add(JBScrollPane(panel))
    }
}
```

- [ ] **Step 4: NewManuscriptAction.kt**

```kotlin
// src/main/kotlin/ai/vedix/jetbrains/NewManuscriptAction.kt
package ai.vedix.jetbrains

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages

class NewManuscriptAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val topic = Messages.showInputDialog(e.project, "Research topic", "Vedix — New Manuscript", null) ?: return
        val discipline = Messages.showEditableChooseDialog("Discipline", "Vedix",
            null, arrayOf("chemistry","biology","medicine","physics","mathematics","geology","computer_science","humanities"),
            "chemistry", null) ?: return
        val r = ApiClient.newJob(topic = topic, discipline = discipline, language = "en", venue = "preprint")
        Messages.showInfoMessage(e.project, "Job ${r.jobId} queued", "Vedix")
    }
}
```

- [ ] **Step 5: ApiClient.kt + CliRunner.kt**

```kotlin
// src/main/kotlin/ai/vedix/jetbrains/ApiClient.kt
package ai.vedix.jetbrains

import com.intellij.openapi.application.PathManager
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import com.google.gson.Gson

data class NewJobResult(val jobId: String, val state: String)

object ApiClient {
    private val gson = Gson()
    private val http = HttpClient.newHttpClient()
    private val base = System.getenv("VEDIX_SAAS_URL") ?: "https://api.vedix.ai"
    private val token = System.getenv("VEDIX_TOKEN") ?: ""

    fun newJob(topic: String, discipline: String, language: String, venue: String): NewJobResult {
        if (token.isBlank()) return CliRunner.newJob(topic, discipline, language, venue)
        val payload = mapOf("topic" to topic, "discipline" to discipline, "language" to language,
                            "venue" to venue, "hypothesis_style" to "exploratory", "experiment_type" to "computational",
                            "primary_metric" to "TBD", "expected_direction" to "increase", "tolerance" to 0.05)
        val req = HttpRequest.newBuilder(URI.create("$base/v1/api/jobs"))
            .header("Authorization", "Bearer $token")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(payload)))
            .build()
        val resp = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (resp.statusCode() !in 200..299) throw RuntimeException("HTTP ${resp.statusCode()}: ${resp.body()}")
        return gson.fromJson(resp.body(), NewJobResult::class.java)
    }
}
```

```kotlin
// src/main/kotlin/ai/vedix/jetbrains/CliRunner.kt
package ai.vedix.jetbrains

import com.google.gson.Gson
import java.io.BufferedReader
import java.io.InputStreamReader

object CliRunner {
    private val gson = Gson()
    fun newJob(topic: String, discipline: String, language: String, venue: String): NewJobResult {
        val pb = ProcessBuilder("vedix", "new", "--topic", topic, "--discipline", discipline,
                                 "--language", language, "--venue", venue, "--json")
        val proc = pb.start()
        val out = BufferedReader(InputStreamReader(proc.inputStream)).readText()
        proc.waitFor()
        return gson.fromJson(out, NewJobResult::class.java)
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/ide/jetbrains/
git commit -m "feat(B10): JetBrains plugin — Kotlin scaffolding + tool window + new-manuscript action"
```

## Block 10 acceptance criteria

- [ ] `npm run package` in `vscode/` produces `.vsix` installable in VS Code
- [ ] `gradle buildPlugin` in `jetbrains/` produces `.jar` installable in IntelliJ family
- [ ] VS Code: `Vedix: New Manuscript` opens input prompts and creates a job
- [ ] JetBrains: tool window opens; New Manuscript action creates a job
- [ ] Citation hover in `.tex` / `.md` files shows the Vedix tooltip
- [ ] StatusBar shows month-to-date cost when SaaS is configured
- [ ] CLI fallback works when SaaS not configured (`useSaas: false`)
- [ ] Git tag `v3.0.0-block10` pushed
