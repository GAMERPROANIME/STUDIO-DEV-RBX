--!strict
-- OMNIBRIDGE Studio Plugin — complementary to the official Studio MCP server.
--
-- It does NOT reimplement Studio MCP capabilities. It only bridges Studio UI
-- events to the OMNIBRIDGE Python core over HTTP (localhost, token-authenticated):
--   • register  → /bridge/register (identity + current selection)
--   • diagnose  → core tool error_diagnose for real LogService errors
--   • export    → core tool file_update, writing selected scripts into the Rojo project
--
-- Install: Plugins → Manage Plugins → "Save as Local Plugin", or copy to the
-- Plugins folder. HTTP requests to localhost must be allowed
-- (Game Settings → Security → Allow HTTP Requests).
local HttpService = game:GetService("HttpService")
local LogService = game:GetService("LogService")
local Selection = game:GetService("Selection")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local SERVER_URL = "http://127.0.0.1:8765"
local TOKEN_ATTRIBUTE = "OmniBridgeToken"
local EXPORT_ROOT = "src/studio" -- relative to the OMNIBRIDGE workspace (Rojo project)

---------------------------------------------------------------------------
-- transport
---------------------------------------------------------------------------

local function getToken(): string
	return plugin:GetSetting(TOKEN_ATTRIBUTE) or ""
end

type Response = { ok: boolean, status: number?, body: any }

local function request(method: string, path: string, payload: { [string]: any }?): Response
	local ok, result = pcall(function()
		return HttpService:RequestAsync({
			Url = SERVER_URL .. path,
			Method = method,
			Headers = {
				["Authorization"] = "Bearer " .. getToken(),
				["Content-Type"] = "application/json",
			},
			Body = if payload then HttpService:JSONEncode(payload) else nil,
		})
	end)
	if not ok then
		return { ok = false, body = tostring(result) }
	end
	local decoded: any = nil
	local decodeOk = pcall(function()
		decoded = HttpService:JSONDecode(result.Body)
	end)
	return {
		ok = result.Success,
		status = result.StatusCode,
		body = if decodeOk then decoded else result.Body,
	}
end

local function callTool(name: string, args: { [string]: any }): Response
	return request("POST", "/api/tools/call", { name = name, args = args })
end

local function describe(res: Response): string
	if res.body == nil then
		return if res.ok then "OK" else `HTTP {res.status or "?"}`
	end
	local ok, encoded = pcall(function()
		return HttpService:JSONEncode(res.body)
	end)
	return if ok then encoded else tostring(res.body)
end

---------------------------------------------------------------------------
-- actions
---------------------------------------------------------------------------

local function registerSelection(): string
	local instances = Selection:Get()
	local names = table.create(#instances)
	for index, instance in ipairs(instances) do
		names[index] = instance:GetFullName()
	end
	local res = request("POST", "/bridge/register", {
		clientId = "studio-plugin",
		info = {
			mode = "studio",
			placeId = game.PlaceId,
			placeName = game.Name,
			selection = names,
		},
	})
	if not res.ok then
		return `Connexion échouée ({res.status or "réseau"}) — token ou serveur OMNIBRIDGE à vérifier.`
	end
	return `Connecté · {#names} instance(s) sélectionnée(s)`
end

local function diagnoseErrors(): string
	local history = LogService:GetLogHistory()
	local errors: { string } = {}
	for _, entry in ipairs(history) do
		if entry.messageType == Enum.MessageType.MessageError then
			table.insert(errors, entry.message)
		end
	end
	if #errors == 0 then
		return "Aucune erreur dans la console."
	end
	local report = { `{#errors} erreur(s) analysée(s) par le core Python:` }
	for index = math.max(1, #errors - 4), #errors do
		local message = errors[index]
		local res = callTool("error_diagnose", { message = message })
		local analysis = res.body
		local category = "?"
		local firstFix = "—"
		if typeof(analysis) == "table" then
			local result = analysis.result
			if typeof(result) == "table" then
				category = tostring(result.category)
				local fixes = result.suggestedFixes
				if typeof(fixes) == "table" and #fixes > 0 then
					firstFix = tostring(fixes[1])
				end
			end
		end
		table.insert(report, `• [{category}] {message}\n    → {firstFix}`)
	end
	return table.concat(report, "\n")
end

local function exportSelection(): string
	local instances = Selection:Get()
	local scripts: { (Script | ModuleScript | LocalScript) } = {}
	for _, instance in ipairs(instances) do
		if instance:IsA("Script") or instance:IsA("ModuleScript") or instance:IsA("LocalScript") then
			table.insert(scripts, instance)
		end
	end
	if #scripts == 0 then
		return "Sélectionnez au moins un Script, LocalScript ou ModuleScript."
	end
	local exportOk, exportError = pcall(function()
		ChangeHistoryService:SetWaypoint("OMNIBRIDGE Export selection")
	end)
	local written, failed = 0, 0
	for _, script in ipairs(scripts) do
		local relative = string.gsub(script:GetFullName(), "%.", "/")
		local res = callTool("file_update", {
			path = `{EXPORT_ROOT}/{relative}.luau`,
			content = script.Source,
		})
		if res.ok then
			written += 1
		else
			failed += 1
		end
	end
	local note = if exportOk then "" else ` (waypoint: {tostring(exportError)})`
	return `{written} script(s) exporté(s) vers {EXPORT_ROOT}/, {failed} échec(s){note}`
end

---------------------------------------------------------------------------
-- UI
---------------------------------------------------------------------------

local toolbar = plugin:CreateToolbar("OMNIBRIDGE")
local mainButton = toolbar:CreateButton("OMNIBRIDGE", "Panneau OMNIBRIDGE", "rbxassetid://0")
mainButton.ClickableWhenViewportHidden = true

local widgetInfo = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, false, false, 360, 320, 280, 240)
local widget = plugin:CreateDockWidgetPluginGui("OmniBridgePanel", widgetInfo)
widget.Title = "OMNIBRIDGE"

local panel = Instance.new("Frame")
panel.Size = UDim2.fromScale(1, 1)
panel.BackgroundColor3 = Color3.fromRGB(12, 16, 24)
panel.Parent = widget

local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 6)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = panel

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 8)
padding.PaddingLeft = UDim.new(0, 8)
padding.PaddingRight = UDim.new(0, 8)
padding.Parent = panel

local function makeLabel(text: string, height: number): TextLabel
	local label = Instance.new("TextLabel")
	label.Size = UDim2.new(1, 0, 0, height)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.Code
	label.TextSize = 12
	label.TextColor3 = Color3.fromRGB(230, 237, 247)
	label.TextXAlignment = Enum.TextXAlignment.Left
	label.TextYAlignment = Enum.TextYAlignment.Top
	label.TextWrapped = true
	label.Text = text
	label.Parent = panel
	return label
end

local function makeButton(text: string, onClick: () -> string): TextButton
	local button = Instance.new("TextButton")
	button.Size = UDim2.new(1, 0, 0, 30)
	button.BackgroundColor3 = Color3.fromRGB(79, 140, 255)
	button.TextColor3 = Color3.fromRGB(255, 255, 255)
	button.Font = Enum.Font.GothamMedium
	button.TextSize = 13
	button.Text = text
	button.Parent = panel
	button.Activated:Connect(function()
		local ok, message = pcall(onClick)
		status.Text = if ok then message else `Erreur: {tostring(message)}`
		print(`[OMNIBRIDGE] {status.Text}`)
	end)
	return button
end

local tokenLabel = makeLabel("Token (~/.omnibridge/token.txt)", 16)

local tokenBox = Instance.new("TextBox")
tokenBox.Size = UDim2.new(1, 0, 0, 28)
tokenBox.BackgroundColor3 = Color3.fromRGB(18, 26, 41)
tokenBox.TextColor3 = Color3.fromRGB(230, 237, 247)
tokenBox.Font = Enum.Font.Code
tokenBox.TextSize = 12
tokenBox.PlaceholderText = "collez le token"
tokenBox.Text = getToken()
tokenBox.Parent = panel
tokenBox.FocusLost:Connect(function()
	plugin:SetSetting(TOKEN_ATTRIBUTE, tokenBox.Text)
	status.Text = "Token enregistré."
end)

makeButton("Connecter / envoyer la sélection", registerSelection)
makeButton("Diagnostiquer la console", diagnoseErrors)
makeButton("Exporter la sélection vers Rojo", exportSelection)

local status = makeLabel("Prêt.", 80)

mainButton.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

widget.Enabled = true
print("[OMNIBRIDGE] Plugin chargé : token, puis « Connecter ».")
