"""Shared MCP Apps / OpenAI host bridge for static widget HTML (Python-owned)."""

from __future__ import annotations

from typing import Any

# Injected into every widget page before route-specific render logic.
HOST_BRIDGE_JS = """
window.openai = window.openai || {};
var __nitrostack_rpcId = 1;
var __nitrostack_initId = null;
var __nitrostack_pending = {};
function __nitrostack_postToHost(msg) {
  if (window.parent && window.parent !== window) {
    window.parent.postMessage(msg, "*");
  }
}
function __nitrostack_rpc(method, params) {
  var id = __nitrostack_rpcId++;
  return new Promise(function(resolve, reject) {
    __nitrostack_pending[id] = { resolve: resolve, reject: reject, method: method };
    __nitrostack_postToHost({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
    setTimeout(function() {
      if (__nitrostack_pending[id]) {
        delete __nitrostack_pending[id];
        reject(new Error(method + " timed out"));
      }
    }, 20000);
  });
}
function __nitrostack_applyTheme(ctx) {
  ctx = ctx || {};
  var theme = ctx.theme || (window.openai && window.openai.theme) || "";
  if (theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
    if (document.body) document.body.setAttribute("data-theme", theme);
  }
  var styles = ctx.styles || {};
  var vars = styles.variables || styles;
  if (vars && typeof vars === "object") {
    Object.keys(vars).forEach(function(key) {
      if (key.indexOf("--") === 0 && vars[key] != null) {
        document.documentElement.style.setProperty(key, String(vars[key]));
      }
    });
  }
}
function __nitrostack_callTool(name, args) {
  args = args || {};
  if (window.openai && typeof window.openai.callTool === "function") {
    return window.openai.callTool(name, args);
  }
  return __nitrostack_rpc("tools/call", { name: name, arguments: args }).then(function(result) {
    if (result) __nitrostack_acceptToolResult(result);
    return result;
  });
}
function __nitrostack_isSafeUrl(url) {
  if (!url || typeof url !== "string") return false;
  return /^(https?|mailto|tel):/i.test(url.trim());
}
function __nitrostack_openLink(url) {
  if (!__nitrostack_isSafeUrl(url)) return;
  if (window.openai && typeof window.openai.openExternal === "function") {
    window.openai.openExternal({ href: url });
    return;
  }
  __nitrostack_rpc("ui/open-link", { url: url }).catch(function() {
    try { window.open(url, "_blank", "noopener"); } catch (e) {}
  });
}
function __nitrostack_requestDisplayMode(mode) {
  mode = mode || "fullscreen";
  if (window.openai && typeof window.openai.requestDisplayMode === "function") {
    return window.openai.requestDisplayMode({ mode: mode });
  }
  return __nitrostack_rpc("ui/request-display-mode", { mode: mode });
}
function __nitrostack_setWidgetState(state) {
  window.openai = window.openai || {};
  window.openai.widgetState = state;
  if (typeof window.openai.setWidgetState === "function") {
    window.openai.setWidgetState(state);
    return;
  }
  __nitrostack_rpc("ui/update-model-context", { structuredContent: { widgetState: state } }).catch(function() {});
}
function __nitrostack_readEmbeddedData() {
  const el = document.getElementById("nitrostack-tool-data");
  if (!el) return null;
  const raw = (el.textContent || "").trim();
  if (!raw || raw === "null") return null;
  try { return JSON.parse(raw); } catch (e) { return null; }
}
function __nitrostack_readHostData() {
  const o = window.openai || {};
  const out = o.toolOutput || o.toolResult || null;
  if (!out) return __nitrostack_readEmbeddedData();
  if (out.structuredContent && typeof out.structuredContent === "object") {
    return out.structuredContent;
  }
  const contents = out.content || out.contents;
  if (Array.isArray(contents)) {
    const jsonBlock = contents.find(
      (c) => c && typeof c === "object" && (c.mimeType === "application/json" || c.type === "json")
    );
    if (jsonBlock && jsonBlock.text != null) {
      try {
        return typeof jsonBlock.text === "string" ? JSON.parse(jsonBlock.text) : jsonBlock.text;
      } catch (e) {}
    }
    const textBlock = contents.find(
      (c) => c && typeof c === "object" && (c.mimeType === "text/plain" || c.type === "text")
    );
    if (textBlock && typeof textBlock.text === "string") {
      const t = textBlock.text.trim();
      if (t.startsWith("{") || t.startsWith("[")) {
        try { return JSON.parse(t); } catch (e) {}
      }
    }
  }
  if (out && typeof out === "object" && !Array.isArray(out)) return out;
  return __nitrostack_readEmbeddedData();
}
function __nitrostack_applyWidget(force) {
  if (typeof window.__nitroWidgetRender !== "function") return;
  const data = __nitrostack_readHostData();
  if (data == null) return;
  const ssr = document.body && document.body.getAttribute("data-nitro-ssr") === "1";
  const needsClient = document.querySelector("[data-nitro-needs-client]");
  if (ssr && !force && !needsClient) return;
  if (!force && needsClient && window.__nitroClientReady) return;
  window.__nitroWidgetRender(data);
  if (needsClient) window.__nitroClientReady = true;
}
function __nitrostack_acceptToolResult(params) {
  window.openai = window.openai || {};
  if (params && params.structuredContent != null) {
    window.openai.toolOutput = { structuredContent: params.structuredContent, content: params.content };
  } else if (params && params.result && params.result.structuredContent != null) {
    window.openai.toolOutput = params.result;
  } else {
    window.openai.toolOutput = params;
  }
  __nitrostack_applyWidget(true);
}
function __nitrostack_startMcpAppsHandshake() {
  __nitrostack_initId = __nitrostack_rpcId++;
  __nitrostack_postToHost({
    jsonrpc: "2.0",
    id: __nitrostack_initId,
    method: "ui/initialize",
    params: {
      protocolVersion: "2026-01-26",
      appInfo: { name: "nitrostack-widget", version: "1.0.0" },
      appCapabilities: {
        availableDisplayModes: ["inline", "fullscreen", "pip"]
      }
    }
  });
}
function __nitrostack_bindChrome() {
  document.addEventListener("click", function(ev) {
    var callEl = ev.target.closest("[data-call-tool]");
    if (callEl) {
      ev.preventDefault();
      var name = callEl.getAttribute("data-call-tool");
      var args = {};
      try { args = JSON.parse(callEl.getAttribute("data-args") || "{}"); } catch (e) {}
      callEl.classList.add("is-busy");
      Promise.resolve(__nitrostack_callTool(name, args)).catch(function() {}).finally(function() {
        callEl.classList.remove("is-busy");
      });
      return;
    }
    var linkEl = ev.target.closest("[data-open-link]");
    if (linkEl) {
      ev.preventDefault();
      __nitrostack_openLink(linkEl.getAttribute("data-open-link") || linkEl.getAttribute("href"));
      return;
    }
    var modeEl = ev.target.closest("[data-display-mode]");
    if (modeEl) {
      ev.preventDefault();
      __nitrostack_requestDisplayMode(modeEl.getAttribute("data-display-mode") || "fullscreen");
    }
  });
  document.addEventListener("keydown", function(ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var el = ev.target.closest("[data-call-tool]");
    if (!el) return;
    ev.preventDefault();
    el.click();
  });
}
window.nitrostack = {
  callTool: __nitrostack_callTool,
  openLink: __nitrostack_openLink,
  requestDisplayMode: __nitrostack_requestDisplayMode,
  setWidgetState: __nitrostack_setWidgetState,
  readHostData: __nitrostack_readHostData
};
function __nitrostack_installHostBridge() {
  window.addEventListener("openai:set_globals", function(event) {
    const globals = (event && event.detail && event.detail.globals) || {};
    window.openai = Object.assign(window.openai || {}, globals);
    __nitrostack_applyTheme(globals);
    __nitrostack_applyWidget(true);
  });
  window.addEventListener("openai:ready", function() { __nitrostack_applyWidget(true); });
  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.jsonrpc === "2.0" && msg.id != null && __nitrostack_pending[msg.id]) {
      const pending = __nitrostack_pending[msg.id];
      delete __nitrostack_pending[msg.id];
      if (msg.error) pending.reject(msg.error);
      else pending.resolve(msg.result);
    }
    if (msg.jsonrpc === "2.0" && msg.id === __nitrostack_initId && msg.result) {
      const ctx = msg.result.hostContext || {};
      window.openai = Object.assign(window.openai || {}, {
        theme: ctx.theme || window.openai.theme,
        displayMode: ctx.displayMode || window.openai.displayMode
      });
      __nitrostack_applyTheme(ctx);
      __nitrostack_postToHost({ jsonrpc: "2.0", method: "ui/notifications/initialized" });
      return;
    }
    if (msg.jsonrpc === "2.0" && msg.method === "ui/notifications/host-context-changed") {
      const ctx = msg.params || {};
      if (ctx.theme) {
        window.openai = Object.assign(window.openai || {}, { theme: ctx.theme });
      }
      __nitrostack_applyTheme(ctx);
      return;
    }
    if (msg.type === "setGlobals" && msg.globals) {
      window.openai = Object.assign(window.openai || {}, msg.globals);
      __nitrostack_applyTheme(msg.globals);
      __nitrostack_applyWidget(true);
      return;
    }
    if (msg.type === "NITRO_INJECT_OPENAI" && msg.openai) {
      window.openai = Object.assign(window.openai || {}, msg.openai);
      __nitrostack_applyTheme(msg.openai);
      __nitrostack_applyWidget(true);
      return;
    }
    if ((msg.type === "toolOutput" || msg.type === "TOOL_OUTPUT") && msg.data) {
      window.openai = window.openai || {};
      window.openai.toolOutput = msg.data;
      __nitrostack_applyWidget(true);
      return;
    }
    if (msg.jsonrpc === "2.0" && (
      msg.method === "ui/notifications/tool-result" ||
      msg.method === "notifications/tool-result"
    )) {
      __nitrostack_acceptToolResult(msg.params || {});
    }
    if (msg.jsonrpc === "2.0" && msg.method === "ui/notifications/tool-input") {
      window.openai = window.openai || {};
      window.openai.toolInput = msg.params;
    }
  });
  __nitrostack_bindChrome();
  __nitrostack_startMcpAppsHandshake();
  if (window.openai && window.openai.theme) __nitrostack_applyTheme(window.openai);
  __nitrostack_applyWidget(false);
  let n = 0;
  const poll = setInterval(() => {
    __nitrostack_applyWidget(false);
    if (++n > 40) clearInterval(poll);
  }, 250);
}
""".strip()


def wrap_widget_page(
    *,
    title: str,
    styles: str,
    body: str,
    render_js: str,
    data: Any | None = None,
    extra_head: str = "",
    flush: bool = False,
    chrome: bool = True,
) -> str:
    """Build a self-contained widget HTML document with the shared host bridge."""
    from nitrostack.widgets.html_util import esc, json_script
    from nitrostack.widgets.ui import SHARED_CSS

    ssr_attr = ' data-nitro-ssr="1"' if data is not None else ""
    body_class = ' class="ns-flush"' if flush else ""
    head_extra = f"\n{extra_head}" if extra_head else ""
    chrome_html = ""
    if chrome:
        chrome_html = (
            '<div class="ns-chrome">'
            '<button type="button" class="ns-icon-btn" data-display-mode="fullscreen" '
            'title="Expand" aria-label="Expand widget">⤢</button>'
            "</div>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>{esc(title)}</title>
  <style>
{SHARED_CSS}
{styles}
  </style>{head_extra}
</head>
<body{body_class}{ssr_attr}>
  {json_script(data)}
  {chrome_html}
{body}
  <script>
{HOST_BRIDGE_JS}
{render_js}
__nitrostack_installHostBridge();
  </script>
</body>
</html>
"""
