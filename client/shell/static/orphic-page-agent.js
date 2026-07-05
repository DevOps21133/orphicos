/*
 * Orphic Page Agent — opt-in bridge to Alibaba page-agent (MIT).
 * ----------------------------------------------------------------
 * "Orphic Page Agent" is the OrphicOS feature name for an opt-in, browser-side
 * voice/text-driven web navigation mode. Under the hood it bridges to the
 * upstream open-source library `page-agent`, a JavaScript in-page GUI agent:
 * give it a natural-language instruction and it operates the DOM (clicks, types,
 * scrolls) to carry it out.
 *   Upstream Source:  https://github.com/alibaba/page-agent
 *   Upstream License: MIT (recorded in THIRD-PARTY-NOTICES.txt)
 *
 * WHY THIS IS OPT-IN ONLY
 *   The upstream page-agent runs its OWN LLM reasoning loop inside the browser —
 *   it needs a provider + key that live client-side. That clashes with OrphicOS's
 *   brain-less client rule (CLAUDE.md Rule 1: no LLM/provider/key on the client).
 *   So Orphic Page Agent is gated behind an explicit per-user toggle. The default
 *   command path (local STT -> command bar -> OrphicOS brain over /ws) is
 *   completely unchanged unless the user turns Orphic Page Agent on and supplies
 *   their own provider key. See CLAUDE.md "Accepted debt" for the full rationale.
 *
 * PAGE SCOPE — read this before promising anything
 *   page-agent can only drive the page it is loaded into (Same-Origin Policy:
 *   cross-origin iframes are opaque to it). Loaded into THIS shell, it can operate
 *   the shell itself — useful for accessibility ("scroll the log", "open memory",
 *   "press the run button"). To drive a third-party site the user must load the
 *   agent THERE (a bookmarklet / extension form), which is out of scope here.
 *   The config modal states this plainly; we do not overpromise.
 *
 * Everything the user enters (provider, baseURL, key, model) is stored in THIS
 * browser's localStorage and never sent to OrphicOS servers. The provider call
 * goes straight from the browser to the user's configured endpoint.
 */
window.OrphicPageAgent = (function () {
  // The published IIFE bundle of the upstream page-agent library. Pinned to a
  // known version for reproducibility; bump deliberately. If offline / blocked,
  // ensureLoaded() rejects and the UI tells the user exactly why — it never
  // silently falls back to a guess.
  var BUNDLE_URL = "https://cdn.jsdelivr.net/npm/page-agent@1.10.0/dist/iife/page-agent.demo.js";

  var STORAGE_KEY = "orphic.pageagent.config.v1";
  // The fields that persist across sessions. The API key is sensitive, so it lives
  // in localStorage (browser-local, never transmitted to OrphicOS) and the modal
  // warns the user before they paste it.
  var DEFAULTS = { provider: "openai", baseURL: "", apiKey: "", model: "gpt-4o", language: "en" };

  var scriptTag = null;
  var agent = null;       // the live page-agent instance once started
  var enabled = false;    // is Orphic Page Agent mode on? (toggle, persisted)
  var busy = false;       // is a page-agent run in flight?

  // ---- config persistence (browser-local only) ---------------------------------

  function getConfig() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return Object.assign({}, DEFAULTS);
      var parsed = JSON.parse(raw);
      return Object.assign({}, DEFAULTS, parsed && typeof parsed === "object" ? parsed : {});
    } catch (_) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function saveConfig(cfg) {
    var merged = Object.assign({}, DEFAULTS, cfg || {});
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(merged)); } catch (_) {}
    return merged;
  }

  function isEnabled() { return enabled; }

  function setEnabled(on) {
    enabled = !!on;
    try { localStorage.setItem("orphic.pageagent.enabled", enabled ? "1" : "0"); } catch (_) {}
  }

  // Restore the toggle on shell load. Default OFF — the feature must be chosen,
  // never imposed (this is the whole point of opt-in vs Rule 1).
  try { enabled = localStorage.getItem("orphic.pageagent.enabled") === "1"; } catch (_) {}

  // ---- loading the library on demand ------------------------------------------

  /*
   * Inject the page-agent IIFE script and resolve once window.PageAgent exists.
   * The same script tag is reused for the lifetime of the page, so toggling the
   * feature off and on again doesn't pile up <script> tags.
   */
  function ensureLoaded() {
    if (window.PageAgent) return Promise.resolve();
    if (scriptTag) return scriptTag._promise;  // already loading
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = BUNDLE_URL;
      s.async = true;
      s._promise = new Promise(function (res, rej) {
        s.onload = function () {
          if (window.PageAgent) res();
          else rej(new Error("page-agent loaded but window.PageAgent is missing " +
                             "(the bundle may have changed). Check the version pin."));
        };
        s.onerror = function () {
          rej(new Error("Couldn't load page-agent from the CDN. " +
                        "Check your connection and try again."));
        };
      }).then(resolve, reject);
      document.head.appendChild(s);
      scriptTag = s;
    });
  }

  /*
   * Construct the agent. The constructor signature follows page-agent's published
   * docs (model / baseURL / apiKey / language). baseURL lets the user point at a
   * provider-compatible endpoint (OpenAI, Azure, a local proxy…). If page-agent's
   * API has shifted, start() surfaces the failure verbatim rather than guessing.
   */
  function start(cfg) {
    return ensureLoaded().then(function () {
      var opts = {
        model: cfg.model || DEFAULTS.model,
        apiKey: cfg.apiKey,
        language: cfg.language || DEFAULTS.language,
      };
      if (cfg.baseURL) opts.baseURL = cfg.baseURL;
      // Some builds use `provider`, others infer from baseURL; pass it through.
      if (cfg.provider) opts.provider = cfg.provider;
      try {
        agent = new window.PageAgent(opts);
      } catch (e) {
        agent = null;
        throw new Error("page-agent rejected the config: " + (e && e.message ? e.message : e));
      }
      return agent;
    });
  }

  function isReady() { return !!agent; }

  /*
   * Run one natural-language instruction. `onEvent` receives step-style callbacks
   * shaped to fit the shell's existing feed renderer:
   *   onEvent({ type: "step", step, reasoning, actions, done })
   *   onEvent({ type: "error", message })
   * page-agent's own step API varies by version, so we wrap defensively: any step
   * callback it does expose is mapped onto the shell's shape, and a run that
   * completes without any step callbacks still yields one synthetic "done" step.
   */
  function execute(text, onEvent) {
    if (!agent) {
      onEvent && onEvent({ type: "error", message: "Orphic Page Agent isn't started. Open 🕸 Orphic Page Agent and configure it." });
      return Promise.resolve();
    }
    if (busy) {
      onEvent && onEvent({ type: "error", message: "Orphic Page Agent is already running a command." });
      return Promise.resolve();
    }
    if (!text || !text.trim()) {
      onEvent && onEvent({ type: "error", message: "Type an instruction first." });
      return Promise.resolve();
    }
    busy = true;
    var stepNo = 0;
    // If page-agent exposes an observation hook, surface each step as a card so the
    // user sees progress (mirroring the OrphicOS brain's step events). Best-effort:
    // missing hooks just mean fewer cards, not a failure.
    try {
      if (agent.on && typeof agent.on === "function") {
        agent.on("action", function (info) {
          stepNo += 1;
          onEvent && onEvent({
            type: "step", step: stepNo,
            reasoning: (info && info.reasoning) || "",
            actions: (info && info.action) ? [_formatAction(info.action, info)] : [],
            done: false, pageagent: true,
          });
        });
      }
    } catch (_) { /* hook attachment is best-effort */ }

    return Promise.resolve()
      .then(function () { return agent.execute(text); })
      .then(function (result) {
        stepNo += 1;
        onEvent && onEvent({
          type: "step", step: stepNo, reasoning: "Orphic Page Agent finished.",
          actions: [], done: true, pageagent: true,
          answer: (result && typeof result === "string") ? result : "",
        });
      })
      .catch(function (e) {
        onEvent && onEvent({ type: "error",
          message: "Orphic Page Agent failed: " + (e && e.message ? e.message : e) });
      })
      .then(function () { busy = false; });
  }

  function _formatAction(action, info) {
    // page-agent action objects vary; pull the most useful fields defensively.
    var type = (action && action.type) || (info && info.type) || "act";
    var target = (action && (action.targetSelector || action.target || action.selector)) || "";
    var value = (action && (action.value || action.text)) || "";
    var result = (info && info.result) || (info && info.status) || "done";
    return { type: type, target: target, value: value, result: String(result) };
  }

  /*
   * Best-effort halt. page-agent's run is async; if it exposes an abort we call it,
   * otherwise we mark the run not-busy so the next command is accepted. The shell's
   * big red STOP always also reaches the OrphicOS kill switch — this only covers
   * the in-browser agent.
   */
  function stop() {
    busy = false;
    try { if (agent && typeof agent.abort === "function") agent.abort(); } catch (_) {}
    try { if (agent && typeof agent.stop === "function") agent.stop(); } catch (_) {}
  }

  return {
    getConfig: getConfig,
    saveConfig: saveConfig,
    isEnabled: isEnabled,
    setEnabled: setEnabled,
    isReady: isReady,
    start: start,
    execute: execute,
    stop: stop,
    isBusy: function () { return busy; },
    BUNDLE_URL: BUNDLE_URL,
  };
})();
