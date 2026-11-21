"""Browser side of the one-click flow, executed for real in Node.

`tests/harness_provider_loop.mjs` loads the *real* `extension/site-adapters.js` and
`extension/agent-loop.js` in a DOM stub and checks:

  * page detection (DeepSeek known, unknown site refused);
  * typing into the composer + clicking the send button;
  * the agent loop: prompt (+ user instruction) is sent, the answer is read when it settles,
    tool calls are executed through the local API with the Bearer token, the results are sent
    back, and the loop stops on the final answer.

Roblox itself is NOT simulated: the API is stubbed, only the extension logic is under test.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HARNESS = ROOT / "tests" / "harness_provider_loop.mjs"


def run_harness() -> dict:
    proc = subprocess.run(
        [NODE, str(HARNESS), str(ROOT / "extension" / "site-adapters.js"),
         str(ROOT / "extension" / "agent-loop.js")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def harness() -> dict:
    if NODE is None:
        pytest.skip("node not installed")
    return run_harness()


def test_provider_detects_the_page_and_reports_readiness(harness):
    provider = harness["provider"]
    assert provider["detected"] == {"id": "deepseek", "label": "DeepSeek", "known": True}
    assert provider["status"]["composer"] is True
    assert provider["status"]["sendButton"] is True
    assert provider["status"]["generating"] is False
    assert provider["status"]["conversation"] == "/a/chat/1"
    assert provider["unknownSite"] is False, "unknown sites must not be driven"


def test_provider_types_and_clicks_send(harness):
    provider = harness["provider"]
    assert provider["send"]["sent"] is True
    assert provider["send"]["via"] == "bouton"
    assert provider["composerValue"] == "Bonjour OMNIBRIDGE"
    assert provider["inputDispatched"] in ("input", "change")
    assert provider["sendButtonClicks"] == 1


def test_loop_bootstraps_executes_and_sends_results_back(harness):
    loop = harness["loop"]
    outcome = loop["outcome"]
    assert outcome["ok"] is True
    assert loop["messagesSent"] == 2, "prompt+instruction, then the results"
    assert loop["firstMessageStartsWithPrompt"] is True
    assert loop["firstMessageHasInstruction"] is True
    assert loop["secondMessageIsResults"] is True
    assert loop["runCalls"] == 2
    assert loop["executed"] == 1
    assert loop["running"] is False, "the loop must always release the panel"
    assert outcome["finalReply"].startswith("C'est fait")
    assert loop["authOnRequests"] is True, "every local API call carries the token"


def test_loop_reports_its_lifecycle(harness):
    events = harness["loop"]["events"]
    for expected in ("start", "cycle", "reply", "executed", "done", "stopped"):
        assert expected in events, expected
    assert events.index("executed") < events.index("done")


def test_panel_and_loop_are_valid_javascript():
    if NODE is None:
        pytest.skip("node not installed")
    for script in ("site-adapters.js", "agent-loop.js", "bridge-panel.js", "content.js",
                   "popup.js", "background.js"):
        proc = subprocess.run([NODE, "--check", str(ROOT / "extension" / script)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{script}: {proc.stderr}"


def test_manifests_load_the_loop_before_the_panel():
    for name in ("manifest.json", "manifest.firefox.json"):
        manifest = json.loads((ROOT / "extension" / name).read_text(encoding="utf-8"))
        panel_groups = [group for group in manifest["content_scripts"]
                        if "bridge-panel.js" in group["js"]]
        assert panel_groups, name
        for group in panel_groups:
            assert group["js"].index("agent-loop.js") < group["js"].index("bridge-panel.js"), name
            assert group["js"].index("site-adapters.js") < group["js"].index("agent-loop.js"), name
