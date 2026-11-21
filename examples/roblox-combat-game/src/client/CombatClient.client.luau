--!strict
-- CombatClient: sends validated combat requests, plays effects.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local CombatConfig = require(ReplicatedStorage.Shared.CombatConfig)

local remotes = ReplicatedStorage:WaitForChild("Remotes")
local combatHit = remotes:WaitForChild("CombatHit") :: RemoteEvent

local currentWeapon = "Sword"

UserInputService.InputBegan:Connect(function(input: InputObject, processed: boolean)
	if processed then return end
	if input.UserInputType ~= Enum.UserInputType.MouseButton1 then return end
	local player = game:GetService("Players").LocalPlayer
	local character = player.Character
	if not character then return end
	local root = character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then return end
	-- Find the closest valid target in range (client-side hint; server re-validates).
	local best: Model? = nil
	local bestDist = CombatConfig.Weapons[currentWeapon].Range
	for _, other in ipairs(workspace:GetChildren()) do
		if other:IsA("Model") and other ~= character then
			local otherRoot = other:FindFirstChild("HumanoidRootPart") :: BasePart?
			local humanoid = other:FindFirstChildOfClass("Humanoid")
			if otherRoot and humanoid and humanoid.Health > 0 then
				local dist = (otherRoot.Position - root.Position).Magnitude
				if dist < bestDist then
					bestDist = dist
					best = other
				end
			end
		end
	end
	if best then
		combatHit:FireServer(best:FindFirstChild("HumanoidRootPart"), currentWeapon)
	end
end)

print("[CombatClient] ready")
