/* OMNIBRIDGE — autonomous loop between an AI chat page and the local core (→ Roblox Studio).
 *
 * One click ("Démarrer") and the loop:
 *   1. asks the local core for the real tool list + protocol      GET  /api/webai/prompt
 *   2. writes that message into the AI chat and sends it          provider.sendMessage()
 *   3. waits for the answer to settle (no streaming, stable text)
 *   4. executes the tool calls found in the answer                POST /api/webai/run
 *   5. sends the real results back into the chat, then repeats
 *
 * Safety rails: explicit start only (no auto-run at load), hard cycle limit, per-cycle timeout,
 * anti-duplicate guard, stop button, and everything goes through 127.0.0.1 with the user token.
 * It never reads cookies, passwords or session tokens.
 */
'use strict';

if (!globalThis.__omniBridgeLoop) {
  const DEFAULT_MAX_CYCLES = 10;
  const REMINDER_EVERY = 3;
  // Tunable so the tests can run the real loop in milliseconds instead of minutes.
  const DEFAULT_TIMINGS = { replyTimeoutMs: 150000, stableMs: 2500, pollMs: 700 };

  function hash(text) {
    let value = 5381;
    for (let i = 0; i < text.length; i += 1) {
      value = ((value << 5) + value + text.charCodeAt(i)) | 0;
    }
    return String(value >>> 0);
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function providerApi() {
    return globalThis.__omniBridgeProvider || globalThis.__omniBridgeAdapters || null;
  }

  const loop = {
    running: false,
    stopping: false,
    cycles: 0,
    maxCycles: DEFAULT_MAX_CYCLES,
    executed: 0,
    errors: 0,
    provider: 'unknown',
    startedAt: 0,
    stopReason: '',
    finalReply: '',
    history: [],
    onEvent: null,
    _lastSeenReply: '',
    _lastCallsHash: '',
    timings: { ...DEFAULT_TIMINGS },
    _server: 'http://127.0.0.1:8765',
    _token: '',

    emit(event) {
      this.history.push({ ts: Date.now(), ...event });
      if (this.history.length > 200) this.history.shift();
      if (typeof this.onEvent === 'function') {
        try {
          this.onEvent(event);
        } catch {
          /* the UI must never break the loop */
        }
      }
    },

    status() {
      return {
        running: this.running,
        cycles: this.cycles,
        maxCycles: this.maxCycles,
        executed: this.executed,
        errors: this.errors,
        provider: this.provider,
        startedAt: this.startedAt,
        stopReason: this.stopReason,
        finalReply: this.finalReply,
      };
    },

    async api(path, options = {}) {
      const headers = { 'Content-Type': 'application/json' };
      if (this._token) headers.Authorization = `Bearer ${this._token}`;
      const response = await fetch(this._server + path, { ...options, headers });
      const text = await response.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }
      if (!response.ok) {
        const detail = (data && data.detail) || data || {};
        throw new Error(typeof detail === 'object' ? JSON.stringify(detail) : String(detail));
      }
      return data;
    },

    stop(reason) {
      if (!this.running) return false;
      this.stopping = true;
      this.stopReason = reason || 'demande_utilisateur';
      this.emit({ type: 'log', level: 'warn', text: `Arrêt demandé (${this.stopReason}).` });
      return true;
    },

    async _waitForReply() {
      const provider = providerApi();
      if (!provider) return { ok: false, reason: 'provider_absent' };
      const { replyTimeoutMs, stableMs, pollMs } = this.timings;
      const started = Date.now();
      let lastText = this._lastSeenReply;
      let lastChange = Date.now();
      while (Date.now() - started < replyTimeoutMs) {
        if (this.stopping) return { ok: false, reason: 'arrete' };
        const text = provider.getLatestAssistantResponse();
        if (text !== lastText) {
          lastText = text;
          lastChange = Date.now();
        }
        const generating = provider.isGenerating();
        if (generating) lastChange = Date.now();
        const fresh = text && text !== this._lastSeenReply;
        if (fresh && !generating && Date.now() - lastChange >= stableMs) {
          this._lastSeenReply = text;
          return { ok: true, text };
        }
        await sleep(pollMs);
      }
      return { ok: false, reason: 'timeout' };
    },

    /**
     * @param {{instruction?: string, token: string, server?: string, maxCycles?: number,
     *          onEvent?: (event: object) => void, dryRun?: boolean}} options
     */
    async start(options = {}) {
      const provider = providerApi();
      const emit = (event) => this.emit(event);
      if (this.running) return { ok: false, code: 'deja_en_cours' };
      if (!provider) return { ok: false, code: 'provider_absent' };

      const detected = provider.detectProvider();
      if (!detected || !detected.known) {
        return { ok: false, code: 'site_non_supporte', provider: detected };
      }
      const composer = provider.findComposer();
      if (!composer) {
        return { ok: false, code: 'composer_introuvable', provider: detected };
      }

      this._server = (options.server || 'http://127.0.0.1:8765').replace(/\/$/, '');
      this._token = options.token || '';
      this.maxCycles = Math.max(1, Math.min(30, options.maxCycles || DEFAULT_MAX_CYCLES));
      this.running = true;
      this.stopping = false;
      this.cycles = 0;
      this.executed = 0;
      this.errors = 0;
      this.startedAt = Date.now();
      this.stopReason = '';
      this.finalReply = '';
      this.provider = detected.id;
      this._lastCallsHash = '';
      this._lastSeenReply = provider.getLatestAssistantResponse();
      if (typeof options.onEvent === 'function') this.onEvent = options.onEvent;

      emit({ type: 'start', provider: detected.id, maxCycles: this.maxCycles });

      let bootstrap;
      try {
        await this.api('/api/health'); // the core must answer before we type anything
        bootstrap = await this.api('/api/webai/prompt?budgetChars=6000');
      } catch (error) {
        this.running = false;
        emit({ type: 'error', text: `Serveur local injoignable : ${error.message}` });
        return { ok: false, code: 'core_injoignable', error: String(error.message || error) };
      }

      const instruction = (options.instruction || '').trim()
        || 'Analyse l\'état de Roblox Studio avec les outils disponibles, puis propose une action '
         + 'concrète et exécute-la.';
      const message = `${bootstrap.prompt}\n\n# Demande de l'utilisateur\n\n${instruction}`;
      emit({ type: 'log', level: 'info', text: `Prompt envoyé (${bootstrap.tools.length} outils).` });

      if (options.dryRun) {
        this.running = false;
        return { ok: true, dryRun: true, chars: message.length, tools: bootstrap.tools.length };
      }

      let firstSend;
      try {
        firstSend = await provider.sendMessage(message);
      } catch (error) {
        this.running = false;
        emit({ type: 'error', text: `Envoi impossible : ${error.message}` });
        return { ok: false, code: 'envoi_impossible', error: String(error.message || error) };
      }
      if (!firstSend.sent) {
        this.running = false;
        emit({ type: 'error', text: `Envoi refusé (${firstSend.reason}).` });
        return { ok: false, code: firstSend.reason || 'envoi_refuse' };
      }
      if (!firstSend.cleared) {
        emit({ type: 'log', level: 'warn',
               text: 'Le champ de saisie ne s\'est pas vidé : vérifie que le message est parti.' });
      }

      for (let cycle = 1; cycle <= this.maxCycles; cycle += 1) {
        if (this.stopping) break;
        this.cycles = cycle;
        emit({ type: 'cycle', cycle, max: this.maxCycles });

        const reply = await this._waitForReply();
        if (!reply.ok) {
          this.errors += 1;
          emit({ type: 'error', text: `Pas de réponse exploitable (${reply.reason}).` });
          if (reply.reason === 'arrete') break;
          if (this.errors >= 2) {
            this.stopReason = 'deux_echecs';
            break;
          }
          continue;
        }
        emit({ type: 'reply', cycle, chars: reply.text.length });

        let run;
        try {
          run = await this.api('/api/webai/run', {
            method: 'POST',
            body: JSON.stringify({ reply: reply.text }),
          });
        } catch (error) {
          this.errors += 1;
          emit({ type: 'error', text: `Exécution impossible : ${error.message}` });
          continue;
        }

        if (!run || !run.executed) {
          this.finalReply = reply.text;
          emit({ type: 'done', reason: 'reponse_finale', chars: reply.text.length });
          break;
        }

        this.executed += run.executed;
        const callsHash = hash(JSON.stringify(run.details || []));
        if (this._lastCallsHash && callsHash === this._lastCallsHash) {
          this.stopReason = 'anti_doublon';
          emit({ type: 'log', level: 'warn',
                 text: 'Anti-doublon : les mêmes appels reviennent, boucle arrêtée.' });
          break;
        }
        this._lastCallsHash = callsHash;
        emit({ type: 'executed', executed: run.executed, failed: run.failed || 0 });

        let payload = String(run.block || '');
        if (cycle % REMINDER_EVERY === 0) {
          payload += '\n(Rappel : n\'utilise que les outils listés et réponds avec un bloc '
                   + 'JSON {"calls":[{"tool":"…","args":{…}}]} quand une action est nécessaire.)';
        }
        const sent = await provider.sendMessage(payload);
        if (!sent.sent) {
          this.errors += 1;
          emit({ type: 'error', text: `Résultats non renvoyés (${sent.reason}).` });
          break;
        }
        if (cycle === this.maxCycles) {
          this.stopReason = 'limite_de_cycles';
          emit({ type: 'log', level: 'warn', text: `Limite de ${this.maxCycles} cycles atteinte.` });
        }
      }

      this.running = false;
      this.stopping = false;
      emit({ type: 'stopped', ...this.status() });
      return { ok: true, ...this.status() };
    },
  };

  globalThis.__omniBridgeLoop = loop;
}
