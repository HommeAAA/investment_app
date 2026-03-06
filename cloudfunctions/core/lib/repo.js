const { nowIso, randomInviteCode } = require("./utils");

const COL = {
  users: "users",
  legacyUsers: "legacy_users",
  investments: "investments",
  shares: "shares",
  logs: "operation_logs",
  symbols: "symbol_cache",
  prices: "price_cache",
};

function createRepo({ db }) {
  const _ = db.command;

  async function findOne(collection, where) {
    const res = await db.collection(collection).where(where).limit(1).get();
    return (res.data && res.data[0]) || null;
  }

  async function ensureInviteCode() {
    for (let i = 0; i < 8; i += 1) {
      const code = randomInviteCode(8);
      // eslint-disable-next-line no-await-in-loop
      const exists = await findOne(COL.users, { inviteCode: code });
      if (!exists) return code;
    }
    return `${randomInviteCode(6)}${Date.now().toString(36).toUpperCase()}`;
  }

  async function getOrCreateUserByOpenId({ openid, unionid = "", nickname = "" }) {
    let user = await findOne(COL.users, { openid });
    if (user) {
      return user;
    }

    const inviteCode = await ensureInviteCode();
    const createdAt = nowIso();
    const payload = {
      openid,
      unionid,
      nickname: nickname || `用户${inviteCode.slice(-4)}`,
      inviteCode,
      createdAt,
      boundLegacy: false,
      legacyUsername: "",
    };
    const addRes = await db.collection(COL.users).add({ data: payload });
    user = { ...payload, _id: addRes._id };
    return user;
  }

  async function getUserByOpenId(openid) {
    return findOne(COL.users, { openid });
  }

  async function getUserById(uid) {
    if (!uid) return null;
    try {
      const res = await db.collection(COL.users).doc(uid).get();
      return res.data || null;
    } catch (_err) {
      return null;
    }
  }

  async function getUserByInviteCode(inviteCode) {
    return findOne(COL.users, { inviteCode: String(inviteCode || "").trim().toUpperCase() });
  }

  async function getUsersByIds(ids) {
    if (!ids || !ids.length) return [];
    const uniq = [...new Set(ids.filter(Boolean))];
    const res = await db.collection(COL.users).where({ _id: _.in(uniq) }).get();
    return res.data || [];
  }

  async function getLegacyUser(username) {
    return findOne(COL.legacyUsers, { username: String(username || "").trim() });
  }

  async function bindLegacyAccount({ uid, legacyUsername, legacyUid }) {
    const now = nowIso();
    await db.collection(COL.users).doc(uid).update({
      data: {
        boundLegacy: true,
        legacyUsername,
        updatedAt: now,
      },
    });

    await db.collection(COL.legacyUsers).where({ username: legacyUsername }).update({
      data: {
        boundUid: uid,
        boundAt: now,
      },
    });

    await db.collection(COL.investments).where({ ownerUid: legacyUid }).update({
      data: {
        ownerUid: uid,
        ownerLegacyUsername: _.remove(),
        updatedAt: now,
      },
    });

    await db.collection(COL.shares).where({ ownerUid: legacyUid }).update({
      data: {
        ownerUid: uid,
        ownerLegacyUsername: _.remove(),
      },
    });

    await db.collection(COL.shares).where({ sharedWithUid: legacyUid }).update({
      data: {
        sharedWithUid: uid,
        sharedWithLegacyUsername: _.remove(),
      },
    });

    await db.collection(COL.logs).where({ ownerUid: legacyUid }).update({
      data: {
        ownerUid: uid,
      },
    });

    await db.collection(COL.logs).where({ operatorUid: legacyUid }).update({
      data: {
        operatorUid: uid,
      },
    });
  }

  async function listSharesBySharedWith(uid) {
    const res = await db.collection(COL.shares).where({ sharedWithUid: uid }).get();
    return res.data || [];
  }

  async function listSharesByOwner(uid) {
    const res = await db.collection(COL.shares).where({ ownerUid: uid }).get();
    return res.data || [];
  }

  async function getShare(ownerUid, sharedWithUid) {
    return findOne(COL.shares, { ownerUid, sharedWithUid });
  }

  async function upsertShare({ ownerUid, sharedWithUid, permission }) {
    const existing = await getShare(ownerUid, sharedWithUid);
    const data = {
      ownerUid,
      sharedWithUid,
      permission,
      createdAt: nowIso(),
    };
    if (!existing) {
      const res = await db.collection(COL.shares).add({ data });
      return { ...data, _id: res._id };
    }
    await db.collection(COL.shares).doc(existing._id).update({ data });
    return { ...existing, ...data };
  }

  async function deleteShare(ownerUid, sharedWithUid) {
    const existing = await getShare(ownerUid, sharedWithUid);
    if (!existing) return false;
    await db.collection(COL.shares).doc(existing._id).remove();
    return true;
  }

  async function listAccessibleOwnerIds(uid) {
    const shared = await listSharesBySharedWith(uid);
    const ownerIds = shared.map((x) => x.ownerUid).filter(Boolean);
    return [...new Set([uid, ...ownerIds])];
  }

  async function listInvestmentsByOwners(ownerIds) {
    if (!ownerIds.length) return [];
    const res = await db.collection(COL.investments).where({ ownerUid: _.in(ownerIds) }).orderBy("updatedAt", "desc").get();
    return res.data || [];
  }

  async function getInvestmentById(id) {
    try {
      const res = await db.collection(COL.investments).doc(String(id)).get();
      return res.data || null;
    } catch (_err) {
      return null;
    }
  }

  async function addInvestment(data) {
    const payload = { ...data, updatedAt: nowIso() };
    const res = await db.collection(COL.investments).add({ data: payload });
    return { ...payload, _id: res._id };
  }

  async function updateInvestment(id, patch) {
    const payload = { ...patch, updatedAt: nowIso() };
    await db.collection(COL.investments).doc(String(id)).update({ data: payload });
    return getInvestmentById(String(id));
  }

  async function deleteInvestment(id) {
    await db.collection(COL.investments).doc(String(id)).remove();
  }

  async function reassignInvestor(ownerUid, fromInvestor, toInvestor) {
    const rows = await db.collection(COL.investments).where({ ownerUid, investor: fromInvestor }).get();
    const data = rows.data || [];
    for (const row of data) {
      // eslint-disable-next-line no-await-in-loop
      await db.collection(COL.investments).doc(row._id).update({
        data: { investor: toInvestor, updatedAt: nowIso() },
      });
    }
    return data.length;
  }

  async function addOperationLog(log) {
    const payload = { ...log, actionTime: log.actionTime || nowIso() };
    const res = await db.collection(COL.logs).add({ data: payload });
    return { ...payload, _id: res._id };
  }

  async function listOperationLogsByOwners(ownerIds, { limit = 100, offset = 0 } = {}) {
    if (!ownerIds.length) return [];
    const res = await db.collection(COL.logs)
      .where({ ownerUid: _.in(ownerIds) })
      .orderBy("actionTime", "desc")
      .skip(Number(offset) || 0)
      .limit(Number(limit) || 100)
      .get();
    return res.data || [];
  }

  async function upsertSymbols(items, source = "manual") {
    if (!items || !items.length) return;
    for (const item of items) {
      const market = String(item.market || "");
      const symbolCode = String(item.symbolCode || "").toUpperCase();
      if (!symbolCode) continue;
      const existing = await findOne(COL.symbols, { market, symbolCode });
      const payload = {
        market,
        symbolCode,
        symbolName: item.symbolName || symbolCode,
        source,
        updatedAt: nowIso(),
      };
      if (existing) {
        // eslint-disable-next-line no-await-in-loop
        await db.collection(COL.symbols).doc(existing._id).update({ data: payload });
      } else {
        // eslint-disable-next-line no-await-in-loop
        await db.collection(COL.symbols).add({ data: payload });
      }
    }
  }

  async function searchSymbols(keyword, limit = 20) {
    const q = String(keyword || "").trim();
    if (!q) return [];
    const reg = db.RegExp({ regexp: q, options: "i" });
    const res = await db.collection(COL.symbols)
      .where(_.or([{ symbolCode: reg }, { symbolName: reg }]))
      .limit(Number(limit) || 20)
      .get();
    return res.data || [];
  }

  function makePriceKey(market, symbolCode) {
    return `${String(market || "")}:${String(symbolCode || "").toUpperCase()}`;
  }

  async function getPriceCache(items) {
    if (!items || !items.length) return [];
    const keys = items.map((x) => makePriceKey(x.market, x.symbolCode));
    const res = await db.collection(COL.prices).where({ cacheKey: _.in(keys) }).get();
    return res.data || [];
  }

  async function upsertPriceCache(rows, ttlSeconds = 60) {
    const now = Date.now();
    for (const row of rows) {
      const market = String(row.market || "");
      const symbolCode = String(row.symbolCode || "").toUpperCase();
      if (!symbolCode) continue;
      const cacheKey = makePriceKey(market, symbolCode);
      const existing = await findOne(COL.prices, { cacheKey });
      const payload = {
        cacheKey,
        market,
        symbolCode,
        price: Number(row.price || 0),
        currency: row.currency || "USD",
        stale: !!row.stale,
        updatedAt: nowIso(),
        expireAt: new Date(now + ttlSeconds * 1000).toISOString(),
      };
      if (existing) {
        // eslint-disable-next-line no-await-in-loop
        await db.collection(COL.prices).doc(existing._id).update({ data: payload });
      } else {
        // eslint-disable-next-line no-await-in-loop
        await db.collection(COL.prices).add({ data: payload });
      }
    }
  }

  return {
    collections: COL,
    getOrCreateUserByOpenId,
    getUserByOpenId,
    getUserById,
    getUserByInviteCode,
    getUsersByIds,
    getLegacyUser,
    bindLegacyAccount,
    listSharesBySharedWith,
    listSharesByOwner,
    getShare,
    upsertShare,
    deleteShare,
    listAccessibleOwnerIds,
    listInvestmentsByOwners,
    getInvestmentById,
    addInvestment,
    updateInvestment,
    deleteInvestment,
    reassignInvestor,
    addOperationLog,
    listOperationLogsByOwners,
    upsertSymbols,
    searchSymbols,
    getPriceCache,
    upsertPriceCache,
    makePriceKey,
    command: _,
  };
}

module.exports = {
  createRepo,
  COL,
};
