/* OMNIBRIDGE content script — extracts user-authorized page context.
 * Only runs on user action / explicit tool request. Never exfiltrates
 * cookies, passwords or form data. */
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  try {
    if (msg.type === "get_page_content") {
      const text = document.body ? document.body.innerText : "";
      sendResponse({ url: location.href, title: document.title, text: text.slice(0, msg.maxChars || 30000) });
    } else if (msg.type === "get_selected_text") {
      sendResponse({ selected: window.getSelection().toString() });
    } else if (msg.type === "get_links") {
      const links = [...document.querySelectorAll("a[href]")]
        .slice(0, msg.limit || 100)
        .map((a) => ({ href: a.href, text: a.innerText.trim().slice(0, 120) }));
      sendResponse({ links });
    } else if (msg.type === "search_page") {
      const q = (msg.query || "").toLowerCase();
      const text = document.body ? document.body.innerText : "";
      const hits = [];
      let idx = 0;
      while (hits.length < 20 && (idx = text.toLowerCase().indexOf(q, idx)) >= 0) {
        hits.push(text.slice(Math.max(0, idx - 80), idx + q.length + 80).replace(/\s+/g, " "));
        idx += q.length;
      }
      sendResponse({ query: msg.query, hits });
    }
  } catch (e) {
    sendResponse({ error: String(e) });
  }
  return true;
});
