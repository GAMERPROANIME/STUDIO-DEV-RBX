/* OMNIBRIDGE Dashboard — vanilla JS, talks to /api/* with the local token. */
const $ = (s) => document.querySelector(s);
let token = localStorage.getItem("omnibridge_token") || "";
let tools = [];
let activeCat = "all";

$("#token").value = token;
$("#saveToken").onclick = () => {
  token = $("#token").value.trim();
  localStorage.setItem("omnibridge_token", token);
  refresh();
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

document.querySelectorAll("#tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#tab-" + b.dataset.tab).classList.add("active");
  };
});

function card(label, value, cls = "") {
  return `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;
}

async function refresh() {
  try {
    const health = await api("/api/health");
    $("#footerStatus").textContent = "connecté";
    $("#healthCards").innerHTML =
      card("Outils MCP", health.toolCount) +
      card("Niveau permission", "L" + health.permissionLevel) +
      card("Roblox Studio", health.roblox.available ? "Connecté" : "Non connecté", health.roblox.available ? "ok" : "warn") +
      card("Extension navigateur", health.bridge.connected ? "Connectée" : "Absente", health.bridge.connected ? "ok" : "warn") +
      card("Chunks indexés", health.knowledge.chunks) +
      card("Sources", health.knowledge.sources);
    $("#healthDetail").textContent = JSON.stringify(health, null, 2);
    $("#robloxDetail").textContent = JSON.stringify(health.roblox, null, 2);
    $("#knowledgeDetail").textContent = JSON.stringify(health.knowledge, null, 2);

    tools = await api("/api/tools");
    $("#toolCount").textContent = tools.length;
    const cats = ["all", ...new Set(tools.map((t) => t.category))];
    $("#catFilters").innerHTML = cats.map((c) => `<button data-cat="${c}" class="${c === activeCat ? "active" : ""}">${c}</button>`).join("");
    $("#catFilters").querySelectorAll("button").forEach((b) => (b.onclick = () => { activeCat = b.dataset.cat; refresh(); }));
    const shown = tools.filter((t) => activeCat === "all" || t.category === activeCat);
    $("#toolList").innerHTML = shown.map((t) =>
      `<div class="tool"><div class="name">${t.name}</div><div class="meta">${t.category} · niveau ${t.level}${t.readOnly ? " · lecture seule" : ""}</div><div class="desc">${t.description}</div></div>`
    ).join("");

    const robloxTools = tools.filter((t) => t.category === "roblox");
    $("#robloxTool").innerHTML = robloxTools.map((t) => `<option value="${t.name}">${t.name}</option>`).join("");

    const tasks = await api("/api/tasks");
    $("#taskList").innerHTML = tasks.map((t) =>
      `<div class="tool"><div class="name">${t.id}</div><div class="meta">${t.status} · ${t.updated_at}</div><div class="desc">${t.goal}</div></div>`
    ).join("") || "<p>Aucune tâche.</p>";

    const audit = await api("/api/audit");
    $("#auditDetail").textContent = JSON.stringify(audit.slice(0, 50), null, 2);
  } catch (e) {
    $("#footerStatus").textContent = "non connecté — " + e.message;
    $("#healthDetail").textContent = "Erreur: " + e.message + "\n\nVérifiez que le serveur tourne (npm start) et que le token est correct.";
  }
}

$("#runRobloxTool").onclick = async () => {
  try {
    const args = $("#robloxArgs").value.trim() ? JSON.parse($("#robloxArgs").value) : {};
    const res = await api("/api/call", { method: "POST", body: JSON.stringify({ tool: $("#robloxTool").value, args }) });
    $("#robloxResult").textContent = JSON.stringify(res, null, 2);
  } catch (e) { $("#robloxResult").textContent = "Erreur: " + e.message; }
};

$("#startTask").onclick = async () => {
  try {
    const res = await api("/api/call", { method: "POST", body: JSON.stringify({ tool: "agent_start_task", args: { goal: $("#goal").value } }) });
    $("#taskResult").textContent = JSON.stringify(res, null, 2);
    setTimeout(refresh, 2000);
  } catch (e) { $("#taskResult").textContent = "Erreur: " + e.message; }
};

$("#kbSearch").onclick = async () => {
  try {
    const res = await api("/api/call", { method: "POST", body: JSON.stringify({ tool: "knowledge_retrieve", args: { query: $("#kbQuery").value, limit: 5 } }) });
    $("#kbResult").textContent = JSON.stringify(res, null, 2);
  } catch (e) { $("#kbResult").textContent = "Erreur: " + e.message; }
};

refresh();
setInterval(refresh, 15000);
