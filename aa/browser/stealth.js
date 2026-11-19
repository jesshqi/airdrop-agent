// Small, honest stealth shim: remove the obvious automation tells without faking
// a full browser fingerprint (patchright-class patching would break scripts).
(() => {
  try {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
  } catch (_) {}
  try {
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) window.chrome.runtime = {};
  } catch (_) {}
  try {
    Object.defineProperty(navigator, "languages", { get: () => ["en-US", "en"] });
    Object.defineProperty(navigator, "plugins", { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, "hardwareConcurrency", { get: () => 8 });
    Object.defineProperty(navigator, "deviceMemory", { get: () => 8 });
  } catch (_) {}
  const origQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (origQuery) {
    window.navigator.permissions.query = (p) =>
      p && p.name === "notifications" ? Promise.resolve({ state: Notification.permission }) : origQuery(p);
  }
  try {
    const el = document.createElement("div");
    Object.defineProperty(el, "getContext", { value: () => null });
  } catch (_) {}
})();
