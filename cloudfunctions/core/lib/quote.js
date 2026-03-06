const { identifyMarket, marketCurrency } = require("./utils");
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
    req.on("timeout", () => {
      req.destroy(new Error("REQUEST_TIMEOUT"));
    });
  });
}

async function fetchJson(url, options = {}) {
  const timeoutMs = options.timeoutMs || 5000;
  if (typeof fetch === "function") {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal, headers: options.headers || {} });
      if (!res.ok) {
        throw new Error(`HTTP_${res.status}`);
      }
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }
  const raw = await httpRequest(url, timeoutMs);
  return JSON.parse(raw);
}

async function fetchText(url, options = {}) {
  const timeoutMs = options.timeoutMs || 5000;
  if (typeof fetch === "function") {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal, headers: options.headers || {} });
      if (!res.ok) {
        throw new Error(`HTTP_${res.status}`);
      }
      return await res.text();
    } finally {
      clearTimeout(timer);
    }
  }
  return httpRequest(url, timeoutMs);
}

async function fetchAStockPrice(code) {
  const secid = (String(code).startsWith("6") || String(code).startsWith("5") || String(code).startsWith("9") ? "1." : "0.") + String(code);
  const url = `https://push2.eastmoney.com/api/qt/stock/get?secid=${encodeURIComponent(secid)}&fields=f43`;
  const data = await fetchJson(url, { timeoutMs: 4500 });
  const val = Number(data?.data?.f43 || 0);
  return val > 0 ? val / 100 : 0;
}

async function fetchAStockName(code) {
  const secid = (String(code).startsWith("6") || String(code).startsWith("5") || String(code).startsWith("9") ? "1." : "0.") + String(code);
  const url = `https://push2.eastmoney.com/api/qt/stock/get?secid=${encodeURIComponent(secid)}&fields=f58`;
  const data = await fetchJson(url, { timeoutMs: 4500 });
  return data?.data?.f58 || String(code);
}

async function fetchFundName(code) {
  const text = await fetchText(`https://fundgz.1234567.com.cn/js/${code}.js`, { timeoutMs: 4500 });
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) {
    const data = JSON.parse(text.slice(start, end + 1));
    return data?.name || String(code);
  }
  return String(code);
}

async function fetchUSPrices(codes) {
  if (!codes.length) return {};
  const symbols = codes.map((x) => String(x).trim().toUpperCase()).join(",");
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`;
  const data = await fetchJson(url, { timeoutMs: 5000 });
  const out = {};
  const rows = data?.quoteResponse?.result || [];
  for (const row of rows) {
    const key = String(row.symbol || "").toUpperCase();
    const price = Number(row.regularMarketPrice || row.postMarketPrice || 0);
    if (key) out[key] = Number.isFinite(price) ? price : 0;
  }
  return out;
}

async function fetchUSNames(codes) {
  if (!codes.length) return {};
  const symbols = codes.map((x) => String(x).trim().toUpperCase()).join(",");
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`;
  const data = await fetchJson(url, { timeoutMs: 5000 });
  const out = {};
  const rows = data?.quoteResponse?.result || [];
  for (const row of rows) {
    const key = String(row.symbol || "").toUpperCase();
    const name = row.longName || row.shortName || key;
    if (key) out[key] = name;
  }
  return out;
}

async function fetchCryptoPrice(code) {
  let symbol = String(code || "").toUpperCase();
  if (!symbol.endsWith("USDT")) symbol = `${symbol}USDT`;
  const data = await fetchJson(`https://api.binance.com/api/v3/ticker/price?symbol=${encodeURIComponent(symbol)}`, { timeoutMs: 5000 });
  const price = Number(data?.price || 0);
  return Number.isFinite(price) ? price : 0;
}

async function getSymbolName(market, code) {
  try {
    if (market === "A股") {
      const name = await fetchAStockName(code);
      if (name && name !== code) return name;
      return await fetchFundName(code);
    }
    if (market === "美股") {
      const map = await fetchUSNames([code]);
      return map[String(code).toUpperCase()] || String(code);
    }
    return String(code).toUpperCase();
  } catch (_err) {
    return String(code);
  }
}

async function fetchBatchQuotes(items) {
  const normalized = (items || []).map((x) => ({
    symbolCode: String(x.symbolCode || "").trim().toUpperCase(),
    market: x.market || identifyMarket(x.symbolCode),
  })).filter((x) => x.symbolCode);

  const result = {};
  const usCodes = normalized.filter((x) => x.market === "美股").map((x) => x.symbolCode);

  let usMap = {};
  try {
    usMap = await fetchUSPrices(usCodes);
  } catch (_err) {
    usMap = {};
  }

  for (const item of normalized) {
    const key = item.symbolCode;
    const currency = marketCurrency(item.market);
    try {
      let price = 0;
      if (item.market === "A股") {
        price = await fetchAStockPrice(key);
      } else if (item.market === "美股") {
        price = Number(usMap[key] || 0);
      } else {
        price = await fetchCryptoPrice(key);
      }

      result[key] = {
        symbolCode: key,
        market: item.market,
        price: Number.isFinite(price) ? price : 0,
        currency,
        stale: false,
      };
    } catch (_err) {
      result[key] = {
        symbolCode: key,
        market: item.market,
        price: 0,
        currency,
        stale: true,
      };
    }
  }

  return result;
}

module.exports = {
  fetchBatchQuotes,
  getSymbolName,
  identifyMarket,
  marketCurrency,
};
