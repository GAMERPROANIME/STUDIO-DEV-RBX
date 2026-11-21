/* OMNIBRIDGE — per-site providers (adapters) for AI chat pages.
 *
 * One object per platform, no shared selector soup: each provider declares
 *   reply[]     → where the assistant messages live
 *   composer[]  → the input box
 *   send[]      → the send button
 *   stop[]      → the "stop generating" button (used to detect streaming)
 *
 * Common interface exposed as `globalThis.__omniBridgeProvider`:
 *   detectProvider, findComposer, findSendButton, readAssistantMessages,
 *   getLatestAssistantResponse, isGenerating, sendMessage, setComposerText,
 *   observeConversation, getConversationId, getProviderStatus
 *
 * `globalThis.__omniBridgeAdapters.lastAssistantMessage()` is kept for content.js and for the
 * manual panel mode (backwards compatible).
 *
 * The extension acts ONLY after the user clicks a button. It never reads cookies, passwords or
 * session tokens, and never contacts a remote server: only 127.0.0.1 / localhost.
 */
'use strict';

if (!globalThis.__omniBridgeAdapters) {
  const SITES = [
    {
      id: 'chatgpt',
      label: 'ChatGPT',
      match: /(^|\.)(chatgpt\.com|chat\.openai\.com)$/,
      reply: ['[data-message-author-role="assistant"]', 'div[data-message-id] .markdown', '.markdown'],
      composer: ['#prompt-textarea', 'div.ProseMirror[contenteditable="true"]',
                 'textarea[data-id]', 'form textarea', 'div[contenteditable="true"]'],
      send: ['button[data-testid="send-button"]', 'button[data-testid="composer-send-button"]',
             'button[aria-label*="Send" i]', 'button[aria-label*="Envoyer" i]'],
      stop: ['button[data-testid="stop-button"]', 'button[aria-label*="Stop" i]'],
    },
    {
      id: 'deepseek',
      label: 'DeepSeek',
      match: /(^|\.)chat\.deepseek\.com$/,
      reply: ['.ds-markdown', 'div[class*="ds-markdown"]', '[class*="markdown"]'],
      composer: ['textarea#chat-input', 'textarea[placeholder]', 'form textarea',
                 'div[contenteditable="true"]'],
      send: ['div[role="button"][aria-label*="Send" i]', 'div[role="button"][aria-label*="Envoyer" i]',
             'button[aria-label*="Send" i]', 'button[type="submit"]',
             'div[class*="send"]', '[class*="send-btn"]'],
      stop: ['div[role="button"][aria-label*="Stop" i]', 'button[aria-label*="Stop" i]',
             '[class*="stop"]'],
    },
    {
      id: 'gemini',
      label: 'Gemini',
      match: /(^|\.)gemini\.google\.com$/,
      reply: ['model-response', '.model-response-text', 'message-content'],
      composer: ['rich-textarea div[contenteditable="true"]', 'div[contenteditable="true"]',
                 'textarea'],
      send: ['button[aria-label*="Send" i]', 'button[aria-label*="Envoyer" i]',
             'button.send-button'],
      stop: ['button[aria-label*="Stop" i]', 'button[aria-label*="Arrêter" i]'],
    },
    {
      id: 'copilot',
      label: 'Copilot',
      match: /(^|\.)copilot\.microsoft\.com$/,
      reply: ['[data-content="ai-message"]', '.ac-textBlock', '[class*="ai-message"]'],
      composer: ['textarea#userInput', 'textarea', 'div[contenteditable="true"]'],
      send: ['button[aria-label*="Submit" i]', 'button[aria-label*="Envoyer" i]',
             'button[title*="Send" i]'],
      stop: ['button[aria-label*="Stop" i]', '[class*="stop"]'],
    },
    {
      id: 'grok',
      label: 'Grok',
      match: /(^|\.)grok\.com$/,
      reply: ['[class*="message-bubble"] .prose', '.prose', 'article'],
      composer: ['textarea[aria-label*="Grok" i]', 'textarea', 'div[contenteditable="true"]'],
      send: ['button[aria-label*="Submit" i]', 'button[aria-label*="Send" i]',
             'button[type="submit"]'],
      stop: ['button[aria-label*="Stop" i]', '[class*="stop"]'],
    },
  ];

  const PANEL_ID = 'omnibridge-panel';

  function site() {
    const host = location.hostname;
    return SITES.find((s) => s.match.test(host)) || null;
  }

  function inPanel(el) {
    if (!el) return true;
    if (el.id === PANEL_ID) return true;
    return Boolean(el.closest && el.closest('#' + PANEL_ID));
  }

  function visible(el) {
    if (!el) return false;
    const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null;
    if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
    if (typeof el.getBoundingClientRect === 'function') {
      const rect = el.getBoundingClientRect();
      if (rect && (rect.width || rect.height)) return true;
    }
    return el.offsetParent !== undefined ? Boolean(el.offsetParent) || !style : true;
  }

  /** Newest visible element matching one of the selectors, never our own panel. */
  function pick(selectors) {
    for (const selector of selectors) {
      let nodes = [];
      try {
        nodes = [...document.querySelectorAll(selector)];
      } catch {
        continue;
      }
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const el = nodes[i];
        if (inPanel(el)) continue;
        if (visible(el)) return el;
      }
    }
    return null;
  }

  function detectProvider() {
    const current = site();
    if (!current) return { id: 'unknown', label: location.hostname, known: false };
    return { id: current.id, label: current.label, known: true };
  }

  function findComposer() {
    const current = site();
    if (!current) return null;
    return pick(current.composer);
  }

  function findSendButton() {
    const current = site();
    if (current) {
      const direct = pick(current.send);
      if (direct) return direct;
    }
    const composer = findComposer();
    const scope = (composer && (composer.closest('form')
      || (composer.parentElement && composer.parentElement.parentElement))) || null;
    if (!scope || typeof scope.querySelectorAll !== 'function') return null;
    const candidates = [...scope.querySelectorAll('button,[role="button"]')];
    return candidates.find((el) => visible(el) && !inPanel(el)
      && /send|envoyer|submit|envoi/i.test(
        `${el.getAttribute ? el.getAttribute('aria-label') || '' : ''} ${el.textContent || ''} `
        + `${el.getAttribute ? el.getAttribute('title') || '' : ''}`)) || null;
  }

  function readAssistantMessages() {
    const current = site();
    if (!current) return [];
    for (const selector of current.reply) {
      let nodes = [];
      try {
        nodes = [...document.querySelectorAll(selector)];
      } catch {
        continue;
      }
      const texts = nodes.map((el) => (el.innerText || '').trim()).filter((t) => t.length > 0);
      if (texts.length) return texts.slice(-20).map((text) => ({ text }));
    }
    return [];
  }

  function getLatestAssistantResponse() {
    const messages = readAssistantMessages();
    if (!messages.length) return '';
    return messages[messages.length - 1].text.slice(-16000);
  }

  function isGenerating() {
    const current = site();
    if (current && pick(current.stop)) return true;
    try {
      if (document.querySelector('[aria-busy="true"]')) return true;
    } catch {
      /* ignore */
    }
    return false;
  }

  /** Type into the composer the way a human does (native setter + input event). */
  function setComposerText(element, text) {
    if (!element) return false;
    try {
      if (element.focus) element.focus();
    } catch {
      /* ignore */
    }
    const tag = (element.tagName || '').toUpperCase();
    if (tag === 'TEXTAREA' || tag === 'INPUT') {
      const proto = Object.getPrototypeOf(element);
      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
      if (descriptor && descriptor.set) descriptor.set.call(element, text);
      else element.value = text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
      return Boolean(element.value && element.value.length);
    }
    // contenteditable host (ProseMirror / Lexical / Slate)
    try {
      element.dispatchEvent(new InputEvent('beforeinput', {
        bubbles: true, cancelable: true, inputType: 'insertText', data: text,
      }));
    } catch {
      /* older engines */
    }
    let inserted = false;
    try {
      if (typeof document.execCommand === 'function') {
        document.execCommand('selectAll', false, null);
        inserted = document.execCommand('insertText', false, text);
      }
    } catch {
      inserted = false;
    }
    if (!inserted) {
      element.textContent = text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return true;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /** Send one message. Returns {sent, via, reason} — never pretends it worked. */
  async function sendMessage(text, options = {}) {
    const composer = findComposer();
    if (!composer) return { sent: false, via: 'none', reason: 'composer_introuvable' };
    if (!setComposerText(composer, text)) {
      return { sent: false, via: 'none', reason: 'champ_non_rempli' };
    }
    await sleep(options.graceMs || 250);
    const button = findSendButton();
    if (button && button.disabled !== true) {
      button.click();
      await sleep(400);
      const cleared = composer.value !== undefined
        ? String(composer.value).trim().length === 0
        : (composer.innerText || '').trim().length === 0;
      return { sent: true, via: 'bouton', cleared };
    }
    const event = new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true,
    });
    composer.dispatchEvent(event);
    await sleep(400);
    const cleared = composer.value !== undefined
      ? String(composer.value).trim().length === 0
      : (composer.innerText || '').trim().length === 0;
    return { sent: true, via: 'entree', cleared };
  }

  function observeConversation(callback) {
    if (typeof MutationObserver !== 'function') return () => {};
    const observer = new MutationObserver(() => callback(getLatestAssistantResponse()));
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }

  function getConversationId() {
    return location.pathname || '/';
  }

  function getProviderStatus() {
    const provider = detectProvider();
    const composer = findComposer();
    return {
      provider: provider.id,
      label: provider.label,
      known: provider.known,
      composer: Boolean(composer),
      sendButton: Boolean(findSendButton()),
      generating: isGenerating(),
      replyChars: getLatestAssistantResponse().length,
      conversation: getConversationId(),
    };
  }

  /** Last non-empty visible text among the given selectors (legacy helper). */
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
    if (!document.body || typeof document.createTreeWalker !== 'function') return null;
    let best = null;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let node = walker.currentNode;
    while (node) {
      if (!inPanel(node)) {
        const text = (node.innerText || '').trim();
        if (text.length > 200 && (!best || text.length > best.text.length)) {
          const childCount = [...node.children]
            .filter((c) => (c.innerText || '').trim().length > 120).length;
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

  globalThis.__omniBridgeAdapters = {
    SITES, site, lastAssistantMessage,
    detectProvider, findComposer, findSendButton, readAssistantMessages,
    getLatestAssistantResponse, isGenerating, sendMessage, setComposerText,
    observeConversation, getConversationId, getProviderStatus,
  };
  globalThis.__omniBridgeProvider = globalThis.__omniBridgeAdapters;
}
