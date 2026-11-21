"""Execute the real site adapters in Node with a minimal DOM stub.

Guards the logic that lets OMNIBRIDGE read a reply on ChatGPT / DeepSeek / Gemini /
Copilot / Grok without any copy-paste. Skipped when Node is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

HARNESS = r"""
import fs from 'node:fs';
import vm from 'node:vm';
const src = fs.readFileSync(process.argv[2], 'utf8');
function run(hostname, nodes) {
  const sandbox = {
    location: { hostname, href: `https://${hostname}/chat/1` },
    document: { title: 'chat', body: {}, querySelectorAll: (s) => nodes[s] || [],
                createTreeWalker: () => ({ currentNode: null, nextNode: () => null }) },
    window: { getSelection: () => ({ toString: () => '' }) },
    NodeFilter: { SHOW_ELEMENT: 1 },
    console,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return sandbox.__omniBridgeAdapters.lastAssistantMessage();
}
const el = (t) => ({ innerText: t, closest: () => null, id: '' });
const long = 'Réponse détaillée du modèle contenant les appels JSON à exécuter ensuite.';
const out = {
  deepseek: run('chat.deepseek.com', { '.ds-markdown': [el('court'), el(long)] }),
  gemini: run('gemini.google.com', { 'model-response': [el(long)] }),
  copilot: run('copilot.microsoft.com', { '.ac-textBlock': [el(long)] }),
  grok: run('grok.com', { '.prose': [el(long)] }),
  chatgpt: run('chatgpt.com', { '[data-message-author-role="assistant"]': [el(long)] }),
  other: run('example.com', {}),
};
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_adapters_detect_every_site(tmp_path: Path):
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    proc = subprocess.run([NODE, str(harness), str(ROOT / "extension" / "site-adapters.js")],
                          capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(proc.stdout)
    for site in ("deepseek", "gemini", "copilot", "grok", "chatgpt"):
        assert data[site]["site"] == site
        assert data[site]["found"] is True, site
        assert "JSON" in data[site]["text"] or len(data[site]["text"]) > 20
        assert data[site]["selector"]
    # the panel must not activate on arbitrary sites
    assert data["other"]["site"] == "unknown"
    assert data["other"]["found"] is False
    # the last (newest) message wins
    assert "détaillée" in data["deepseek"]["text"]


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("script", ["background.js", "content.js", "popup.js", "bridge-panel.js",
                                    "site-adapters.js"])
def test_extension_scripts_are_valid_javascript(script: str):
    proc = subprocess.run([NODE, "--check", str(ROOT / "extension" / script)],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_panel_never_automates_the_chat_ui():
    """Regression guard: the panel must not type into, or submit, the conversation."""
    src = (ROOT / "extension" / "bridge-panel.js").read_text(encoding="utf-8")
    forbidden = ["insertText(", "execCommand('insertText'", "execCommand(\"insertText\"",
                 "dispatchEvent(new KeyboardEvent", "submit()", "requestSubmit(",
                 "document.cookie", "localStorage.getItem('session"]
    for pattern in forbidden:
        assert pattern not in src, f"panel must not use {pattern}"
    assert "navigator.clipboard.writeText" in src
