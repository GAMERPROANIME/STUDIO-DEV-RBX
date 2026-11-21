--!strict
-- ArenaManager: spawns players, manages rounds and progression (XP/levels).
local Players = game:GetService("Players")
local ServerStorage = game:GetService("ServerStorage")
local Workspace = game:GetService("Workspace")

local XP_PER_KILL = 25
local LEVEL_XP = 100

local playerData: { [Player]: { XP: number, Level: number, Kills: number } } = {}

local function getSpawn(): BasePart?
	local arena = Workspace:FindFirstChild("Arena")
	if arena then
		local spawn = arena:FindFirstChild("SpawnLocation") :: BasePart?
		if spawn then return spawn end
	end
	return nil
end

Players.PlayerAdded:Connect(function(player: Player)
	playerData[player] = { XP = 0, Level = 1, Kills = 0 }
	player.CharacterAdded:Connect(function(character: Model)
		local humanoid = character:WaitForChild("Humanoid") :: Humanoid
		humanoid.Died:Connect(function()
			-- Award XP to the last attacker (tracked via Humanoid attribute set by CombatServer extensions).
			task.wait(2)
			local spawn = getSpawn()
			if spawn then
				character:PivotTo(spawn.CFrame + Vector3.new(0, 5, 0))
			end
		end)
	end)
end)

Players.PlayerRemoving:Connect(function(player: Player)
	playerData[player] = nil
end)

-- Example progression API (called by other server systems).
local ArenaManager = {}
function ArenaManager.awardXP(player: Player, amount: number)
	local data = playerData[player]
	if not data then return end
	data.XP += amount
	while data.XP >= LEVEL_XP do
		data.XP -= LEVEL_XP
		data.Level += 1
	end
end
function ArenaManager.getData(player: Player)
	return playerData[player]
end

print("[ArenaManager] ready")
return ArenaManager
