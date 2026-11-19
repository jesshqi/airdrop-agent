// Agent Solana provider (Phantom-compatible subset). All operations are forwarded to
// Python binding __aaSolana; the key never exists in the page.
(() => {
  const conf = window.__AA_CONF || {};
  if (!conf.solAddress || window.__aaSolanaInstalled) return;
  window.__aaSolanaInstalled = true;

  const listeners = {};
  const emit = (ev, d) => (listeners[ev] || []).slice().forEach((fn) => { try { fn(d); } catch (_) {} });
  const call = async (method, params) => {
    const res = JSON.parse(await window.__aaSolana(method, JSON.stringify(params || [])));
    if (res.error) { const e = new Error(res.error.message); e.code = res.error.code; throw e; }
    return res.result;
  };
  const toU8 = (v) => (typeof v === "string" ? Uint8Array.from(atob(v), (c) => c.charCodeAt(0)) : Uint8Array.from(v));

  const provider = {
    isPhantom: true,
    isAgentWallet: true,
    get publicKey() { return conf.solConnected ? { toString: () => conf.solAddress, toBase58: () => conf.solAddress, toBytes: () => new Uint8Array() } : null; },
    get isConnected() { return !!conf.solConnected; },
    async connect(opts) {
      if (opts && opts.onlyIfTrusted && conf.solConnected) return { publicKey: provider.publicKey };
      const r = await call("connect");
      conf.solConnected = true;
      emit("connect", { publicKey: conf.solAddress });
      return { publicKey: provider.publicKey, address: conf.solAddress };
    },
    async disconnect() { conf.solConnected = false; await call("disconnect"); emit("disconnect"); },
    async signMessage(msg, _display) {
      const r = await call("signMessage", [Array.from(toU8(msg))]);
      return { signature: toU8(Uint8Array.from(r.signature)), publicKey: provider.publicKey };
    },
    async signTransaction(tx) {
      const raw = tx.serialize ? btoa(String.fromCharCode(...tx.serialize({ requireAllSignatures: false }))) : tx;
      const signed = await call("signTransaction", [raw]);
      if (tx.constructor && tx.constructor.from) return tx.constructor.from(toU8(signed));
      return signed;
    },
    async signAndSendTransaction(tx) {
      const raw = tx.serialize ? btoa(String.fromCharCode(...tx.serialize({ requireAllSignatures: false }))) : tx;
      const sig = await call("signAndSendTransaction", [raw]);
      return { signature: sig, publicKey: provider.publicKey };
    },
    async signAllTransactions(list) {
      const out = [];
      for (const tx of list) out.push(await provider.signTransaction(tx));
      return out;
    },
    on(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); return provider; },
    off(ev, fn) { listeners[ev] = (listeners[ev] || []).filter((f) => f !== fn); },
    removeListener(ev, fn) { provider.off(ev, fn); },
    once(ev, fn) { const w = (d) => { provider.off(ev, w); fn(d); }; return provider.on(ev, w); },
    request({ method, params }) { return call(method, params); },
    connect_() {},
  };

  window.phantom = { solana: provider };
  window.solana = provider;
  window.solflare = provider;
  setTimeout(() => emit("connect", { publicKey: conf.solAddress }), 0);
})();
