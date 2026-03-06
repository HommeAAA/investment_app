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

async function fetchJson(url, timeoutMs = 5000) {
  if (typeof fetch === "function") {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP_${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }
  const raw = await httpRequest(url, timeoutMs);
  return JSON.parse(raw);
}

async function fetchAStockPrice(code) {
  const secid = (String(code).startsWith("6") || String(code).startsWith("5") || String(code).startsWith("9") ? "1." : "0.") + String(code);
  const url = `https://push2.eastmoney.com/api/qt/stock/get?secid=${encodeURIComponent(secid)}&fields=f43`;
  const data = await fetchJson(url, 4500);
  const val = Number(data?.data?.f43 || 0);
  return val > 0 ? val / 100 : 0;
}

async function fetchUSPrices(codes) {
  if (!codes.length) return {};
  const symbols = codes.map((x) => String(x).trim().toUpperCase()).join(",");
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`;
  const data = await fetchJson(url, 5000);
  const out = {};
  for (const row of data?.quoteResponse?.result || []) {
    const key = String(row.symbol || "").toUpperCase();
    const price = Number(row.regularMarketPrice || row.postMarketPrice || 0);
    if (key) out[key] = Number.isFinite(price) ? price : 0;
  }
  return out;
}

async function fetchCryptoPrice(code) {
  let symbol = String(code || "").toUpperCase();
  if (!symbol.endsWith("USDT")) symbol = `${symbol}USDT`;
  const data = await fetchJson(`https://api.binance.com/api/v3/ticker/price?symbol=${encodeURIComponent(symbol)}`, 5000);
  const price = Number(data?.price || 0);
  return Number.isFinite(price) ? price : 0;
}

async function fetchBatchQuotes(items) {
  const normalized = (items || []).map((x) => ({
    symbolCode: String(x.symbolCode || "").trim().toUpperCase(),
    market: x.market || identifyMarket(x.symbolCode),
  })).filter((x) => x.symbolCode);

  const out = {};
  const usCodes = normalized.filter((x) => x.market === "美股").map((x) => x.symbolCode);
  let usPriceMap = {};
  try {
    usPriceMap = await fetchUSPrices(usCodes);
  } catch (_err) {
    usPriceMap = {};
  }

  for (const item of normalized) {
    try {
      let price = 0;
      if (item.market === "A股") {
        // eslint-disable-next-line no-await-in-loop
        price = await fetchAStockPrice(item.symbolCode);
      } else if (item.market === "美股") {
        price = Number(usPriceMap[item.symbolCode] || 0);
      } else {
        // eslint-disable-next-line no-await-in-loop
        price = await fetchCryptoPrice(item.symbolCode);
      }
      out[item.symbolCode] = {
        symbolCode: item.symbolCode,
        market: item.market,
        price,
        currency: marketCurrency(item.market),
        stale: false,
      };
    } catch (_err) {
      out[item.symbolCode] = {
        symbolCode: item.symbolCode,
        market: item.market,
        price: 0,
        currency: marketCurrency(item.market),
        stale: true,
      };
    }
  }
  return out;
}

module.exports = {
  identifyMarket,
  marketCurrency,
  fetchBatchQuotes,
};
const https = require("https");

function httpRequest(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: timeoutMs }, (res) => {
      if (res.statusCode && res.statusCode >= 400) {
        reject(new Error(`HTTP_${res.statusCode}`));
        res.resume();
        return;
      }
      let raw = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        raw += chunk;
      });
      res.on("end", () => resolve(raw));
    });
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("REQUEST_TIMEOUT")));
  });
}
