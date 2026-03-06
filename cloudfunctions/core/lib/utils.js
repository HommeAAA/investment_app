function nowIso() {
  return new Date().toISOString();
}

function randomInviteCode(length = 8) {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let out = "";
  for (let i = 0; i < length; i += 1) {
    out += chars[Math.floor(Math.random() * chars.length)];
  }
  return out;
}

function normalizePermission(permission) {
  return permission === "edit" ? "edit" : "read";
}

function identifyMarket(code) {
  const value = String(code || "").trim().toUpperCase();
  if (!value) return "美股";
  if (value.includes("USDT") || ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"].includes(value)) return "Crypto";
  if (/^\d{6}$/.test(value)) return "A股";
  return "美股";
}

function marketCurrency(market) {
  if (market === "A股") return "CNY";
  if (market === "美股" || market === "Crypto") return "USD";
  return "CNY";
}

function makeLegacyUid(username) {
  return `legacy:${String(username || "").trim()}`;
}

function isLegacyUid(uid) {
  return String(uid || "").startsWith("legacy:");
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

module.exports = {
  nowIso,
  randomInviteCode,
  normalizePermission,
  identifyMarket,
  marketCurrency,
  makeLegacyUid,
  isLegacyUid,
  safeNumber,
};
