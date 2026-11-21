/**
 * Luau static analysis + embedded knowledge base.
 * The analyzer is a real (if lightweight) checker: it catches the most common
 * mistakes an LLM makes with Roblox APIs — nonexistent services, wrong
 * property names, deprecated patterns — by validating against known tables.
 */

export interface LuauIssue {
  line: number;
  severity: "error" | "warning";
  code: string;
  message: string;
  suggestion?: string;
}

/** Services that exist in Roblox (Game:GetService whitelist). */
export const ROBLOX_SERVICES = new Set([
  "Players","ReplicatedStorage","ServerStorage","ServerScriptService","StarterPlayer",
  "StarterGui","StarterPack","Workspace","Lighting","SoundService","TweenService",
  "RunService","ContextActionService","UserInputService","HttpService","DataStoreService",
  "MarketplaceService","TeleportService","Debris","CollectionService","PathfindingService",
  "ProximityPromptService","ReplicatedFirst","StarterCharacterScripts","Chat","LocalizationService",
  "PolicyService","InsertService","BadgeService","FriendService","GroupService",
  "TestService","VirtualInputManager","GuiService","HapticsService","MemoryStoreService",
  "MessagingService","RemoteEvent","RemoteFunction","BindableEvent","BindableFunction",
]);

/** Common Instance classes (subset used for validation). */
export const ROBLOX_CLASSES = new Set([
  "Part","MeshPart","Model","Folder","Script","LocalScript","ModuleScript","RemoteEvent",
  "RemoteFunction","BindableEvent","BindableFunction","ScreenGui","Frame","TextLabel",
  "TextButton","TextBox","ImageLabel","ImageButton","ScrollingFrame","UIListLayout",
  "UIPadding","UICorner","UIStroke","Humanoid","Animator","Animation","AnimationTrack",
  "Sound","PointLight","SpotLight","SurfaceLight","Attachment","ParticleEmitter","Fire",
  "Smoke","Sparkles","Decal","Texture","Highlight","BillboardGui","SurfaceGui","ViewportFrame",
  "Camera","Tool","Accessory","Shirt","Pants","BodyColors","IntValue","StringValue",
  "BoolValue","NumberValue","Color3Value","ObjectValue","Vector3Value","CFrameValue",
  "BrickColorValue","Configuration","ProximityPrompt","ClickDetector","TouchTransmitter",
  "Seat","VehicleSeat","WeldConstraint","Motor6D","AnimationController","AlignPosition",
  "AlignOrientation","LinearVelocity","AngularVelocity","VectorForce","Torque","RopeConstraint",
  "RodConstraint","SpringConstraint","HingeConstraint","PrismatricConstraint","BallSocketConstraint",
  "CylindricalConstraint","Weld","WeldConstraint","MoverConstraint","BodyVelocity","BodyGyro",
  "BodyPosition","BodyThrust","BodyAngularVelocity","BodyForce","BodyMover","Sky","SunRaysEffect",
  "BloomEffect","BlurEffect","ColorCorrectionEffect","DepthOfFieldEffect","SunRaysEffect",
  "Atmosphere","Clouds","Terrain","SpawnLocation","FlagStand","Flag","Team","Player","Character",
]);

/** Deprecated / removed APIs that must not be generated. */
const DEPRECATED: Array<{ pattern: RegExp; code: string; message: string; suggestion: string }> = [
  { pattern: /\bwait\s*\(/, code: "LUAU_DEPRECATED_WAIT", message: "wait() is deprecated and yields imprecisely.", suggestion: "Use task.wait() instead." },
  { pattern: /\bspawn\s*\(/, code: "LUAU_DEPRECATED_SPAWN", message: "spawn() is deprecated.", suggestion: "Use task.spawn() / task.defer() instead." },
  { pattern: /\bdelay\s*\(/, code: "LUAU_DEPRECATED_DELAY", message: "delay() is deprecated.", suggestion: "Use task.delay() instead." },
  { pattern: /game\.Workspace\b/, code: "LUAU_WORKSPACE_ACCESS", message: "Prefer game:GetService('Workspace') or workspace global.", suggestion: "local Workspace = game:GetService('Workspace')" },
  { pattern: /\.CharacterAppearance\b/, code: "LUAU_REMOVED_PROPERTY", message: "CharacterAppearance was removed from Player.", suggestion: "Use StarterPlayer character appearance settings." },
  { pattern: /Humanoid:LoadAnimation\b/, code: "LUAU_DEPRECATED_ANIM", message: "Humanoid:LoadAnimation is deprecated.", suggestion: "Use Animator:LoadAnimation()." },
  { pattern: /Instance\.new\(\s*["']HumanoidDescription["']\s*\)/, code: "LUAU_BAD_CLASS", message: "HumanoidDescription cannot be created with Instance.new.", suggestion: "Use Players:GetHumanoidDescriptionFromUserId()." },
];

const LUAU_KEYWORDS = new Set([
  "and","break","continue","do","else","elseif","end","export","false","for","function","if","in",
  "local","nil","not","or","repeat","return","then","true","type","until","while","self","typeof",
]);

export function analyzeLuau(source: string, filename = "script.luau"): LuauIssue[] {
  const issues: LuauIssue[] = [];
  const lines = source.split("\n");

  // Balanced delimiters (rough but catches truncated generations).
  const pairs: Record<string, string> = { "(": ")", "[": "]", "{": "}" };
  const stack: Array<{ ch: string; line: number }> = [];
  lines.forEach((line, i) => {
    const noStr = line.replace(/"(?:\\.|[^"\\])*"/g, '""').replace(/'(?:\\.|[^'\\])*'/g, "''");
    for (const ch of noStr) {
      if (pairs[ch]) stack.push({ ch, line: i + 1 });
      else if (Object.values(pairs).includes(ch)) {
        const top = stack.pop();
        if (!top || pairs[top.ch] !== ch) {
          issues.push({ line: i + 1, severity: "error", code: "LUAU_UNBALANCED", message: `Unbalanced delimiter '${ch}' in ${filename}.` });
        }
      }
    }
  });
  for (const open of stack) {
    issues.push({ line: open.line, severity: "error", code: "LUAU_UNCLOSED", message: `Unclosed '${open.ch}' opened at line ${open.line} in ${filename}.` });
  }

  lines.forEach((line, i) => {
    const n = i + 1;
    // GetService("X") validation
    const gs = line.match(/GetService\(\s*["']([A-Za-z]+)["']\s*\)/);
    if (gs && !ROBLOX_SERVICES.has(gs[1])) {
      issues.push({ line: n, severity: "error", code: "LUAU_UNKNOWN_SERVICE", message: `Unknown service '${gs[1]}'.`, suggestion: `Valid services include: ${[...ROBLOX_SERVICES].slice(0, 12).join(", ")}…` });
    }
    // Instance.new("X") validation
    const inst = line.match(/Instance\.new\(\s*["']([A-Za-z]+)["']\s*\)/);
    if (inst && !ROBLOX_CLASSES.has(inst[1])) {
      issues.push({ line: n, severity: "warning", code: "LUAU_UNKNOWN_CLASS", message: `Class '${inst[1]}' is not in the known Roblox class list — verify it exists.`, suggestion: "Check the Creator Docs class reference." });
    }
    // Deprecated patterns
    for (const d of DEPRECATED) {
      if (d.pattern.test(line)) issues.push({ line: n, severity: "warning", code: d.code, message: d.message, suggestion: d.suggestion });
    }
    // RemoteEvent misuse: server scripts must not use RemoteEvent for client→server data without validation note
    if (/OnServerEvent/.test(line) && !/typeof|table\.find|typeof\(/.test(source)) {
      issues.push({ line: n, severity: "warning", code: "LUAU_REMOTE_VALIDATION", message: "RemoteEvent handler without visible argument validation.", suggestion: "Validate all client-sent arguments on the server (never trust the client)." });
    }
    // print/warn left in production code
    if (/\b(print|warn)\s*\(/.test(line) && !/--/.test(line.slice(0, line.indexOf("print") > 0 ? line.indexOf("print") : line.indexOf("warn")))) {
      // only flag, low severity
      issues.push({ line: n, severity: "warning", code: "LUAU_DEBUG_PRINT", message: "print/warn call — remove or gate behind a debug flag in production." });
    }
    // while true do without task.wait inside the block (heuristic, same-line)
    if (/while\s+true\s+do/.test(line) && !/task\.wait|task\.yield/.test(line)) {
      issues.push({ line: n, severity: "warning", code: "LUAU_BUSY_LOOP", message: "'while true do' without task.wait() in the same line — ensure the loop yields.", suggestion: "Add task.wait() inside the loop body." });
    }
  });

  // Missing strict mode is a warning, not an error.
  if (!/--!strict|--!nonstrict|--!nolint/.test(source)) {
    issues.push({ line: 1, severity: "warning", code: "LUAU_NO_STRICT", message: "No --!strict header. Typed Luau catches many errors.", suggestion: "Add --!strict at the top of the file." });
  }
  void LUAU_KEYWORDS;
  return issues;
}

/** Embedded Luau/Roblox knowledge base indexed into the Knowledge Engine. */
export const LUAU_KNOWLEDGE = `# Luau & Roblox — Agent Knowledge Base
## Core rules
- Luau is Lua 5.1 + types, generics, string interpolation, compound assignment (+=, -=), continue, if-expressions.
- Add --!strict at the top of every script. Use type annotations on module boundaries.
- Never use deprecated globals: wait(), spawn(), delay(). Use task.wait(), task.spawn(), task.delay(), task.defer().
- Access services via game:GetService("Name") — never assume a service exists; GetService errors if it does not.
- workspace is a global alias for game.Workspace. Prefer local Workspace = game:GetService("Workspace").

## Architecture
- ServerScriptService: server Scripts (authoritative logic, DataStores, RemoteEvent handlers).
- ReplicatedStorage: shared ModuleScripts, RemoteEvents/Functions, assets both sides need.
- StarterPlayerScripts: LocalScripts that run once per player. StarterCharacterScripts: per character respawn.
- StarterGui: GUIs cloned into PlayerGui. ServerStorage: server-only assets.
- Never trust client data: validate every RemoteEvent/RemoteFunction argument on the server.
- DataStores: use UpdateAsync with retry + pcall; never yield indefinitely; handle throttling (BudgetForRequestAsync).

## Instances
- Create with Instance.new("ClassName"), set Parent last (after properties) to avoid replication cost.
- Classes include: Part, MeshPart, Model, Folder, Script, LocalScript, ModuleScript, RemoteEvent, RemoteFunction,
  ScreenGui, Frame, TextLabel, TextButton, ImageLabel, Humanoid, Animator, Animation, Sound, Tool, ProximityPrompt.
- Humanoid:LoadAnimation is deprecated — use Animator:LoadAnimation().

## Networking
- RemoteEvent: FireServer/FireClient/FireAllClients + OnServerEvent/OnClientEvent.
- RemoteFunction: InvokeServer/InvokeClient — avoid; prefer RemoteEvents + timeouts.
- BindableEvent/BindableFunction: same-machine communication only.

## Performance
- Cache services and instances in locals. Avoid table.create in hot loops; reuse tables.
- Use task.defer/spawn for concurrency. Profile with microprofiler (Ctrl+F6) and os.clock().
- StreamingEnabled: stream in/out via Player:RequestStreamAroundAsync; handle missing descendants.

## Testing in Studio
- Use the built-in MCP server (Assistant → Settings → MCP Servers → Enable Studio as MCP server) for live inspection.
- Playtest via Studio test tab; read console output; iterate on errors before re-running.
`;
