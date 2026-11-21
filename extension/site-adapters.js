/* OMNIBRIDGE — adapters for AI chat sites without MCP.
 *
 * Pure DOM reading of the *last assistant message*, used by:
 *   • content.js        → command `get_last_assistant_message` (invoked by browser tools)
 *   • bridge-panel.js   → floating panel on ChatGPT / DeepSeek / Gemini / Copilot / Grok
 *
 * It never types into the page, never sends a message and never reads cookies or
 * credentials: the user decides when a reply is read and pasted back.
 */
'use strict';

if (!globalThis.__omniBridgeAdapters) {
  const SITES = [
    {
      id: 'chatgpt',
      label: 'ChatGPT',
      match: /(^|\.)(chatgpt\.com|chat\.openai\.com)$/,
      reply: ['[data-message-author-role="assistant"]', 'div[data-message-id] .markdown', '.markdown'],
    },
    {
      id: 'deepseek',
      label: 'DeepSeek',
      match: /(^|\.)chat\.deepseek\.com$/,
      reply: ['.ds-markdown', 'div[class*="ds-markdown"]', '[class*="markdown"]'],
    },
    {
      id: 'gemini',
      label: 'Gemini',
      match: /(^|\.)gemini\.google\.com$/,
      reply: ['model-response', '.model-response-text', 'message-content'],
    },
    {
      id: 'copilot',
      label: 'Copilot',
      match: /(^|\.)copilot\.microsoft\.com$/,
      reply: ['[data-content="ai-message"]', '.ac-textBlock', '[class*="ai-message"]'],
    },
    {
      id: 'grok',
      label: 'Grok',
      match: /(^|\.)grok\.com$/,
      reply: ['[class*="message-bubble"] .prose', '.prose', 'article'],
    },
  ];

  function site() {
    const host = location.hostname;
    return SITES.find((s) => s.match.test(host)) || null;
  }

  /** Last non-empty visible text among the given selectors. */
  function fromSelectors(selectors) {
    for (const selector of selectors) {
      let nodes;
      try {
        nodes = [...document.querySelectorAll(selector)];
      } catch {
        continue;
      }
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const el = nodes[i];
        const text = (el.innerText || '').trim();
        if (text.length > 40) return { text, selector };
      }
    }
    return null;
  }

  /** Fallback: the largest visible text container, excluding our own panel. */
  function fromHeuristic() {
    let best = null;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let node = walker.currentNode;
    while (node) {
      if (node.id !== 'omnibridge-panel' && !node.closest('#omnibridge-panel')) {
        const text = (node.innerText || '').trim();
        if (text.length > 200 && (!best || text.length > best.text.length)) {
          const childCount = [...node.children].filter((c) => (c.innerText || '').trim().length > 120).length;
          if (childCount <= 2) best = { text, selector: 'heuristic' };
        }
      }
      node = walker.nextNode();
    }
    return best;
  }

  function lastAssistantMessage() {
    const current = site();
    const found = (current && fromSelectors(current.reply)) || fromHeuristic();
    const selected = (window.getSelection && window.getSelection().toString().trim()) || '';
    return {
      site: current ? current.id : 'unknown',
      label: current ? current.label : location.hostname,
      found: Boolean(found),
      text: found ? found.text.slice(-16000) : '',
      selector: found ? found.selector : '',
      selectedText: selected.slice(0, 16000),
      url: location.href,
      title: document.title,
    };
  }

  globalThis.__omniBridgeAdapters = { SITES, site, lastAssistantMessage };
}
