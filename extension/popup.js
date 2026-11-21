const $ = (s) => document.querySelector(s);
async function refresh() {
  const { token, mode } = await chrome.storage.local.get(["token", "mode"]);
  $("#token").value = token || "";
  $("#mode").value = mode || "manual";
  const status = await chrome.runtime.sendMessage({ type: "status" });
  $("#status").textContent = status.connected ? `Connecté (client ${status.clientId}) · mode ${status.mode}` : "Non connecté — le serveur OMNIBRIDGE doit tourner (npm start).";
}
$("#connect").onclick = async () => {
  await chrome.storage.local.set({ token: $("#token").value.trim(), mode: $("#mode").value });
  await chrome.runtime.sendMessage({ type: "set_mode", mode: $("#mode").value });
  const res = await chrome.runtime.sendMessage({ type: "connect" });
  $("#status").textContent = res.ok ? "Connecté." : "Échec: " + res.error;
  refresh();
};
refresh();
