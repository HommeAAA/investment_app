const cloud = require("wx-server-sdk");
const { fetchBatchQuotes, identifyMarket, marketCurrency } = require("./lib/quote");

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const _ = db.command;

function cacheKey(market, symbolCode) {
  return `${String(market || "")}:${String(symbolCode || "").toUpperCase()}`;
}

exports.main = async (_event, _context) => {
  try {
    const invRes = await db.collection("investments").limit(1000).get();
    const rows = invRes.data || [];

    const symbols = [];
    const seen = new Set();
    for (const row of rows) {
      const symbolCode = String(row.symbolCode || "").trim().toUpperCase();
      if (!symbolCode) continue;
      const market = row.market || identifyMarket(symbolCode);
      const k = cacheKey(market, symbolCode);
      if (seen.has(k)) continue;
      seen.add(k);
      symbols.push({ market, symbolCode });
    }

    if (!symbols.length) {
      return { ok: true, data: { synced: 0 } };
    }

    const quotes = await fetchBatchQuotes(symbols);
    const upserts = [];

    for (const item of symbols) {
      const q = quotes[item.symbolCode] || {
        symbolCode: item.symbolCode,
        market: item.market,
        price: 0,
        currency: marketCurrency(item.market),
        stale: true,
      };
      upserts.push({
        cacheKey: cacheKey(item.market, item.symbolCode),
        market: item.market,
        symbolCode: item.symbolCode,
        price: Number(q.price || 0),
        currency: q.currency || marketCurrency(item.market),
        stale: !!q.stale,
        updatedAt: new Date().toISOString(),
        expireAt: new Date(Date.now() + 60 * 1000).toISOString(),
      });
    }

    for (const row of upserts) {
      // eslint-disable-next-line no-await-in-loop
      const existing = await db.collection("price_cache").where({ cacheKey: row.cacheKey }).limit(1).get();
      if ((existing.data || []).length) {
        // eslint-disable-next-line no-await-in-loop
        await db.collection("price_cache").doc(existing.data[0]._id).update({ data: row });
      } else {
        // eslint-disable-next-line no-await-in-loop
        await db.collection("price_cache").add({ data: row });
      }
    }

    return { ok: true, data: { synced: upserts.length } };
  } catch (error) {
    return { ok: false, code: "QUOTE_SYNC_FAILED", message: error?.message || "quote sync failed" };
  }
};
