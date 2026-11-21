--!strict
-- CombatServer: authoritative combat logic. Validates every client request.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local CombatConfig = require(ReplicatedStorage.Shared.CombatConfig)

local remotes = ReplicatedStorage:WaitForChild("Remotes")
local combatHit = remotes:WaitForChild("CombatHit") :: RemoteEvent

local cooldowns: { [Player]: number } = {}

local function getCharacter(player: Player): Model?
	return player.Character
end

local function validateHit(player: Player, target: Instance?, weaponName: unknown): boolean
	if typeof(weaponName) ~= "string" then return false end
	local weapon = CombatConfig.Weapons[weaponName]
	if not weapon then return false end
	local character = getCharacter(player)
	if not character then return false end
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	local root = character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not humanoid or not root or humanoid.Health <= 0 then return false end
	if typeof(target) ~= "Instance" then return false end
	local targetModel = target:FindFirstAncestorOfClass("Model")
	if not targetModel then return false end
	local targetHumanoid = targetModel:FindFirstChildOfClass("Humanoid")
	local targetRoot = targetModel:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not targetHumanoid or not targetRoot or targetHumanoid.Health <= 0 then return false end
	if (targetRoot.Position - root.Position).Magnitude > weapon.Range then return false end
	local now = os.clock()
	if cooldowns[player] and now - cooldowns[player] < weapon.Cooldown then return false end
	cooldowns[player] = now
	return true
end

combatHit.OnServerEvent:Connect(function(player: Player, target: Instance?, weaponName: unknown)
	if not validateHit(player, target, weaponName) then return end
	local weapon = CombatConfig.Weapons[weaponName :: string]
	local targetModel = (target :: Instance):FindFirstAncestorOfClass("Model") :: Model
	local humanoid = targetModel:FindFirstChildOfClass("Humanoid") :: Humanoid
	local root = targetModel:FindFirstChild("HumanoidRootPart") :: BasePart
	humanoid:TakeDamage(weapon.Damage)
	local character = getCharacter(player)
	local attackerRoot = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if attackerRoot then
		local direction = (root.Position - attackerRoot.Position).Unit
		root.AssemblyLinearVelocity = direction * weapon.Knockback + Vector3.new(0, 8, 0)
	end
end)

Players.PlayerRemoving:Connect(function(player)
	cooldowns[player] = nil
end)

print("[CombatServer] ready")
