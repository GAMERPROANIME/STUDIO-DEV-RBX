--!strict
-- OMNIBRIDGE Studio Plugin (complementary to the official Studio MCP server).
-- Communicates with the local OMNIBRIDGE server over HTTP (localhost only,
-- token-authenticated). Use this when the official MCP server is unavailable
-- or when you need plugin-only capabilities (selection, ChangeHistoryService).
-- Install: save as a Plugin in Studio (Plugins → Manage Plugins → +), or
-- drop into the Plugins folder. Configure the token in the plugin toolbar.
local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local SERVER_URL = "http://127.0.0.1:8765"
local TOKEN_ATTRIBUTE = "OmniBridgeToken"

local toolbar = plugin:CreateToolbar("OMNIBRIDGE")
local button = toolbar:CreateButton("Connect", "Connect to OMNIBRIDGE", "rbxassetid://0")
button.ClickableWhenViewportHidden = true

local function getToken(): string
	return plugin:GetSetting(TOKEN_ATTRIBUTE) or ""
end

local function post(path: string, body: { [string]: any }): any
	local ok, result = pcall(function()
		return HttpService:RequestAsync({
			Url = SERVER_URL .. path,
			Method = "POST",
			Headers = { ["Authorization"] = "Bearer " .. getToken(), ["Content-Type"] = "application/json" },
			Body = HttpService:JSONEncode(body),
		})
	end)
	if not ok then
		warn("[OMNIBRIDGE Plugin] Request failed: " .. tostring(result))
		return nil
	end
	return result
end

button.Click:Connect(function()
	ChangeHistoryService:SetWaypoint("OMNIBRIDGE Connect")
	local selection = game:GetService("Selection"):Get()
	local info = {
		placeId = game.PlaceId,
		selectionCount = #selection,
		selection = table.create(#selection),
	}
	for i, instance in ipairs(selection) do
		info.selection[i] = instance:GetFullName()
	end
	post("/bridge/register", { clientId = "studio-plugin", info = info })
	print("[OMNIBRIDGE Plugin] Connected. Selection: " .. #selection .. " instance(s).")
end)

print("[OMNIBRIDGE Plugin] loaded. Set the token via plugin settings, then click Connect.")
