// Agent EIP-1193 provider (from airdrop-hunter). Every request goes to Python (binding __agentWallet)
// in browser_session.py, which applies sign_guard / safe_send / approval gates before any signature. Placeholder __ADDRESS__ / __CHAIN_ID__ diganti saat inject.
(() => {
  if (window.__agentWalletInstalled) return;
  window.__agentWalletInstalled = true;
  const listeners = {};
  let chainId = "__CHAIN_ID__";
  const address = "__ADDRESS__";

  const emit = (ev, data) => (listeners[ev] || []).slice().forEach((fn) => { try { fn(data); } catch (e) {} });
  window.__agentEmit = (ev, data) => { if (ev === "chainChanged") chainId = data; emit(ev, data); };

  async function request({ method, params }) {
    if (method === "eth_chainId") return chainId;
    const raw = await window.__agentWallet(method, JSON.stringify(params || []));
    const res = JSON.parse(raw);
    if (res.error) {
      const err = new Error(res.error.message || "Rejected");
      err.code = res.error.code || 4001;
      throw err;
    }
    if (method === "wallet_switchEthereumChain" || method === "wallet_addEthereumChain") {
      chainId = res.chainId || chainId;
      emit("chainChanged", chainId);
      return null;
    }
    if (method === "eth_requestAccounts") emit("accountsChanged", res.result);
    return res.result;
  }

  const provider = {
    isMetaMask: true,
    isAgentWallet: true,
    get chainId() { return chainId; },
    get selectedAddress() { return address; },
    networkVersion: String(parseInt("__CHAIN_ID__", 16)),
    request,
    isConnected: () => true,
    enable: () => request({ method: "eth_requestAccounts" }),
    on(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); return provider; },
    once(ev, fn) { const w = (d) => { provider.removeListener(ev, w); fn(d); }; return provider.on(ev, w); },
    removeListener(ev, fn) { listeners[ev] = (listeners[ev] || []).filter((f) => f !== fn); return provider; },
    off(ev, fn) { return provider.removeListener(ev, fn); },
    removeAllListeners(ev) { if (ev) delete listeners[ev]; else Object.keys(listeners).forEach((k) => delete listeners[k]); },
    send(a, b) {
      if (typeof a === "string") return request({ method: a, params: b });
      if (typeof b === "function") return request(a).then((r) => b(null, { id: a.id, jsonrpc: "2.0", result: r }), (e) => b(e));
      return request(a);
    },
    sendAsync(payload, cb) {
      request(payload).then((r) => cb(null, { id: payload.id, jsonrpc: "2.0", result: r }), (e) => cb(e));
    },
  };

  try {
    Object.defineProperty(window, "ethereum", { value: provider, writable: false, configurable: false });
  } catch (e) { window.ethereum = provider; }

  // EIP-6963 (multi-wallet discovery)
  const info = {
    uuid: "6d0b8a6e-0000-4000-8000-a1rd0p000001".replace(/[^0-9a-f-]/g, "0"),
    name: "MetaMask",
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23f6851b'/%3E%3C/svg%3E",
    rdns: "io.metamask",
  };
  const announce = () =>
    window.dispatchEvent(new CustomEvent("eip6963:announceProvider", { detail: Object.freeze({ info, provider }) }));
  window.addEventListener("eip6963:requestProvider", announce);
  announce();
  setTimeout(() => emit("connect", { chainId }), 0);
})();
