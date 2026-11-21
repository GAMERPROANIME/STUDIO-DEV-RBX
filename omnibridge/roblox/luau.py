"""Luau static analysis + embedded knowledge base."""
from __future__ import annotations

import re
from dataclasses import dataclass

ROBLOX_SERVICES = {
    # Core / world
    "Workspace", "Lighting", "Terrain", "MaterialService", "PhysicsService", "Teams",
    "Players", "StarterPlayer", "StarterGui", "StarterPack", "StarterCharacterScripts",
    "ReplicatedFirst", "ReplicatedStorage", "ServerStorage", "ServerScriptService",
    "SoundService", "Debris", "CollectionService", "TweenService", "RunService",
    "PathfindingService", "ProximityPromptService", "ContextActionService",
    "UserInputService", "GuiService", "HapticService", "VRService", "ContentProvider",
    # Networking / data
    "HttpService", "DataStoreService", "MemoryStoreService", "MessagingService",
    "NetworkClient", "NetworkServer", "ScriptContext", "RemoteEvent", "RemoteFunction",
    "BindableEvent", "BindableFunction", "TeleportService",
    # Economy / social
    "MarketplaceService", "PurchaseService", "BadgeService", "GroupService",
    "FriendService", "SocialService", "PolicyService", "LocalizationService",
    "TextService", "TextChatService", "Chat", "VoiceChatService", "AnalyticsService",
    # Assets / tooling
    "AssetService", "InsertService", "KeyframeSequenceProvider", "AvatarEditorService",
    "Selection", "StudioService", "ChangeHistoryService", "ScriptEditorService",
    "PluginManager", "PluginDebugService", "TestService", "VirtualInputManager",
    "VirtualUser", "Stats", "UserService", "CoreGui", "LogService", "Selection",
}

ROBLOX_CLASSES = {
    "Part", "MeshPart", "Model", "Folder", "Script", "LocalScript", "ModuleScript", "RemoteEvent",
    "RemoteFunction", "BindableEvent", "BindableFunction", "ScreenGui", "Frame", "TextLabel",
    "TextButton", "TextBox", "ImageLabel", "ImageButton", "ScrollingFrame", "UIListLayout",
    "UIPadding", "UICorner", "UIStroke", "Humanoid", "Animator", "Animation", "AnimationTrack",
    "Sound", "PointLight", "SpotLight", "SurfaceLight", "Attachment", "ParticleEmitter", "Fire",
    "Smoke", "Sparkles", "Decal", "Texture", "Highlight", "BillboardGui", "SurfaceGui", "ViewportFrame",
    "Camera", "Tool", "Accessory", "Shirt", "Pants", "BodyColors", "IntValue", "StringValue",
    "BoolValue", "NumberValue", "Color3Value", "ObjectValue", "Vector3Value", "CFrameValue",
    "BrickColorValue", "Configuration", "ProximityPrompt", "ClickDetector", "TouchTransmitter",
    "Seat", "VehicleSeat", "WeldConstraint", "Motor6D", "AnimationController", "AlignPosition",
    "AlignOrientation", "LinearVelocity", "AngularVelocity", "VectorForce", "Torque", "RopeConstraint",
    "RodConstraint", "SpringConstraint", "HingeConstraint", "PrismatricConstraint", "BallSocketConstraint",
    "CylindricalConstraint", "Weld", "BodyVelocity", "BodyGyro", "BodyPosition", "BodyThrust",
    "BodyAngularVelocity", "BodyForce", "Sky", "SunRaysEffect", "BloomEffect", "BlurEffect",
    "ColorCorrectionEffect", "DepthOfFieldEffect", "Atmosphere", "Clouds", "Terrain",
    "SpawnLocation", "FlagStand", "Flag", "Team", "Player",
    "SpecialMesh", "Beam", "Trail", "UIGradient", "UIGridLayout", "UITableLayout",
    "UIScale", "UIAspectRatioConstraint", "UISizeConstraint", "CanvasGroup",
    "SurfaceAppearance", "MaterialVariant", "DragDetector", "HumanoidDescription",
    "PlayerGui", "Backpack", "UnionOperation", "NegateOperation", "WedgePart",
    "CornerWedgePart", "TrussPart", "Tool", "RemoteEvent", "RemoteFunction",
}

_DEPRECATED = [
    (re.compile(r"(?<![\w.:])wait\s*\("), "LUAU_DEPRECATED_WAIT", "wait() is deprecated and yields imprecisely.", "Use task.wait() instead."),
    (re.compile(r"(?<![\w.:])spawn\s*\("), "LUAU_DEPRECATED_SPAWN", "spawn() is deprecated.", "Use task.spawn() / task.defer() instead."),
    (re.compile(r"(?<![\w.:])delay\s*\("), "LUAU_DEPRECATED_DELAY", "delay() is deprecated.", "Use task.delay() instead."),
    (re.compile(r"game\.Workspace\b"), "LUAU_WORKSPACE_ACCESS", "Prefer game:GetService('Workspace') or workspace global.", "local Workspace = game:GetService('Workspace')"),
    (re.compile(r"\.CharacterAppearance\b"), "LUAU_REMOVED_PROPERTY", "CharacterAppearance was removed from Player.", "Use StarterPlayer character appearance settings."),
    (re.compile(r"Humanoid:LoadAnimation\b"), "LUAU_DEPRECATED_ANIM", "Humanoid:LoadAnimation is deprecated.", "Use Animator:LoadAnimation()."),
    (re.compile(r"Instance\.new\(\s*[\"']HumanoidDescription[\"']\s*\)"), "LUAU_BAD_CLASS", "HumanoidDescription cannot be created with Instance.new.", "Use Players:GetHumanoidDescriptionFromUserId()."),
]

_PAIRS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = set(_PAIRS.values())


@dataclass
class LuauIssue:
    line: int
    severity: str  # error | warning
    code: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {"line": self.line, "severity": self.severity, "code": self.code,
                "message": self.message, "suggestion": self.suggestion}


def analyze_luau(source: str, filename: str = "script.luau") -> list[LuauIssue]:
    issues: list[LuauIssue] = []
    lines = source.split("\n")

    stack: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        no_str = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        no_str = re.sub(r"'(?:\\.|[^'\\])*'", "''", no_str)
        for ch in no_str:
            if ch in _PAIRS:
                stack.append((ch, i + 1))
            elif ch in _CLOSERS:
                if not stack or _PAIRS[stack[-1][0]] != ch:
                    issues.append(LuauIssue(i + 1, "error", "LUAU_UNBALANCED", f"Unbalanced delimiter '{ch}' in {filename}."))
                else:
                    stack.pop()
    for ch, ln in stack:
        issues.append(LuauIssue(ln, "error", "LUAU_UNCLOSED", f"Unclosed '{ch}' opened at line {ln} in {filename}."))

    for i, line in enumerate(lines):
        n = i + 1
        gs = re.search(r'GetService\(\s*["\']([A-Za-z]+)["\']\s*\)', line)
        if gs and gs.group(1) not in ROBLOX_SERVICES:
            issues.append(LuauIssue(n, "error", "LUAU_UNKNOWN_SERVICE", f"Unknown service '{gs.group(1)}'.",
                                    "Valid services include: " + ", ".join(sorted(ROBLOX_SERVICES)[:12]) + "…"))
        inst = re.search(r'Instance\.new\(\s*["\']([A-Za-z]+)["\']\s*\)', line)
        if inst and inst.group(1) not in ROBLOX_CLASSES:
            issues.append(LuauIssue(n, "warning", "LUAU_UNKNOWN_CLASS",
                                    f"Class '{inst.group(1)}' is not in the known Roblox class list — verify it exists.",
                                    "Check the Creator Docs class reference."))
        for pat, code, msg, sugg in _DEPRECATED:
            if pat.search(line):
                issues.append(LuauIssue(n, "warning", code, msg, sugg))
        if "OnServerEvent" in line and not re.search(r"typeof|table\.find", source):
            issues.append(LuauIssue(n, "warning", "LUAU_REMOTE_VALIDATION",
                                    "RemoteEvent handler without visible argument validation.",
                                    "Validate all client-sent arguments on the server (never trust the client)."))
        if re.search(r"\b(print|warn)\s*\(", line):
            issues.append(LuauIssue(n, "warning", "LUAU_DEBUG_PRINT",
                                    "print/warn call — remove or gate behind a debug flag in production."))
        if re.search(r"while\s+true\s+do", line) and not re.search(r"task\.wait|task\.yield", line):
            issues.append(LuauIssue(n, "warning", "LUAU_BUSY_LOOP",
                                    "'while true do' without task.wait() in the same line — ensure the loop yields.",
                                    "Add task.wait() inside the loop body."))

    if not re.search(r"--!strict|--!nonstrict|--!nolint", source):
        issues.append(LuauIssue(1, "warning", "LUAU_NO_STRICT", "No --!strict header. Typed Luau catches many errors.",
                                "Add --!strict at the top of the file."))
    return issues


LUAU_KNOWLEDGE = """# Luau & Roblox — Agent Knowledge Base
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
"""
