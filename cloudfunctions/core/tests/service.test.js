const test = require("node:test");
const assert = require("node:assert/strict");
const bcrypt = require("bcryptjs");

const { createCoreService } = require("../lib/service");
const { makeLegacyUid } = require("../lib/utils");

function createMemoryRepo() {
  let seq = 1;
  const id = () => `id_${seq++}`;

  const users = [];
  const legacyUsers = [];
  const investments = [];
  const shares = [];
  const logs = [];
  const symbols = [];
  const prices = [];

  const repo = {
    makePriceKey: (market, symbolCode) => `${market}:${String(symbolCode || "").toUpperCase()}`,
    async getOrCreateUserByOpenId({ openid, nickname }) {
      let u = users.find((x) => x.openid === openid);
      if (!u) {
        u = {
          _id: id(),
          openid,
          nickname: nickname || "u",
          inviteCode: `INV${users.length + 1}`,
          boundLegacy: false,
          legacyUsername: "",
          createdAt: new Date().toISOString(),
        };
        users.push(u);
      }
      return { ...u };
    },
    async getUserById(uid) {
      return users.find((x) => x._id === uid) || null;
    },
    async getUserByInviteCode(code) {
      return users.find((x) => x.inviteCode === code) || null;
    },
    async getUsersByIds(ids) {
      return users.filter((x) => ids.includes(x._id));
    },
    async getLegacyUser(username) {
      return legacyUsers.find((x) => x.username === username) || null;
    },
    async bindLegacyAccount({ uid, legacyUsername, legacyUid }) {
      const user = users.find((x) => x._id === uid);
      if (user) {
        user.boundLegacy = true;
        user.legacyUsername = legacyUsername;
      }
      const legacy = legacyUsers.find((x) => x.username === legacyUsername);
      if (legacy) legacy.boundUid = uid;

      for (const inv of investments) {
        if (inv.ownerUid === legacyUid) inv.ownerUid = uid;
      }
      for (const s of shares) {
        if (s.ownerUid === legacyUid) s.ownerUid = uid;
        if (s.sharedWithUid === legacyUid) s.sharedWithUid = uid;
      }
      for (const l of logs) {
        if (l.ownerUid === legacyUid) l.ownerUid = uid;
        if (l.operatorUid === legacyUid) l.operatorUid = uid;
      }
    },
    async listSharesBySharedWith(uid) {
      return shares.filter((x) => x.sharedWithUid === uid);
    },
    async listSharesByOwner(uid) {
      return shares.filter((x) => x.ownerUid === uid);
    },
    async getShare(ownerUid, sharedWithUid) {
      return shares.find((x) => x.ownerUid === ownerUid && x.sharedWithUid === sharedWithUid) || null;
    },
    async upsertShare(data) {
      const found = shares.find((x) => x.ownerUid === data.ownerUid && x.sharedWithUid === data.sharedWithUid);
      if (found) {
        Object.assign(found, data);
        return { ...found };
      }
      const row = { _id: id(), ...data };
      shares.push(row);
      return { ...row };
    },
    async deleteShare(ownerUid, sharedWithUid) {
      const idx = shares.findIndex((x) => x.ownerUid === ownerUid && x.sharedWithUid === sharedWithUid);
      if (idx < 0) return false;
      shares.splice(idx, 1);
      return true;
    },
    async listAccessibleOwnerIds(uid) {
      const owners = [uid, ...shares.filter((x) => x.sharedWithUid === uid).map((x) => x.ownerUid)];
      return [...new Set(owners)];
    },
    async listInvestmentsByOwners(ownerIds) {
      return investments.filter((x) => ownerIds.includes(x.ownerUid));
    },
    async getInvestmentById(docId) {
      return investments.find((x) => x._id === docId) || null;
    },
    async addInvestment(data) {
      const row = { _id: id(), ...data };
      investments.push(row);
      return { ...row };
    },
    async updateInvestment(docId, patch) {
      const row = investments.find((x) => x._id === docId);
      Object.assign(row, patch);
      return { ...row };
    },
    async deleteInvestment(docId) {
      const idx = investments.findIndex((x) => x._id === docId);
      if (idx >= 0) investments.splice(idx, 1);
    },
    async reassignInvestor(ownerUid, fromInvestor, toInvestor) {
      let c = 0;
      for (const row of investments) {
        if (row.ownerUid === ownerUid && row.investor === fromInvestor) {
          row.investor = toInvestor;
          c += 1;
        }
      }
      return c;
    },
    async addOperationLog(log) {
      logs.push({ _id: id(), ...log });
    },
    async listOperationLogsByOwners(ownerIds) {
      return logs.filter((x) => ownerIds.includes(x.ownerUid));
    },
    async upsertSymbols(items) {
      for (const it of items) {
        const f = symbols.find((x) => x.market === it.market && x.symbolCode === it.symbolCode);
        if (f) Object.assign(f, it);
        else symbols.push({ ...it });
      }
    },
    async searchSymbols(keyword) {
      return symbols.filter((x) => x.symbolCode.includes(keyword) || x.symbolName.includes(keyword));
    },
    async getPriceCache(items) {
      const keys = items.map((x) => repo.makePriceKey(x.market, x.symbolCode));
      return prices.filter((x) => keys.includes(x.cacheKey));
    },
    async upsertPriceCache(rows, ttl) {
      const now = Date.now();
      for (const row of rows) {
        const cacheKey = repo.makePriceKey(row.market, row.symbolCode);
        const found = prices.find((x) => x.cacheKey === cacheKey);
        const next = {
          cacheKey,
          ...row,
          expireAt: new Date(now + ttl * 1000).toISOString(),
        };
        if (found) Object.assign(found, next);
        else prices.push(next);
      }
    },
    __seedLegacy(username, plainPassword) {
      legacyUsers.push({ username, passwordHash: bcrypt.hashSync(plainPassword, 10), boundUid: "" });
    },
    __seedInvestment(inv) {
      investments.push({ _id: id(), ...inv });
    },
    __state() {
      return { users, legacyUsers, investments, shares, logs, symbols, prices };
    },
  };

  return repo;
}

function makeCtx(openid = "o_test") {
  return { OPENID: openid };
}

test("system.ping works without login state", async () => {
  const repo = createMemoryRepo();
  const svc = createCoreService({
    repo,
    quoteProvider: {
      getSymbolName: async (_m, c) => c,
      fetchBatchQuotes: async () => ({}),
    },
  });

  const res = await svc.dispatch({ action: "system.ping", payload: {}, wxContext: {} });
  assert.equal(res.ok, true);
  assert.equal(res.data.status, "ok");
});

test("auth.login creates and returns user", async () => {
  const repo = createMemoryRepo();
  const svc = createCoreService({
    repo,
    quoteProvider: {
      getSymbolName: async (_m, c) => c,
      fetchBatchQuotes: async () => ({}),
    },
  });

  const res = await svc.dispatch({ action: "auth.login", payload: { nickname: "A" }, wxContext: makeCtx("openid_1") });
  assert.equal(res.ok, true);
  assert.equal(res.data.user.nickname, "A");
  assert.equal(res.data.user.boundLegacy, false);
});

test("auth.bindLegacy migrates legacy investments", async () => {
  const repo = createMemoryRepo();
  repo.__seedLegacy("legacy_user", "123456");
  repo.__seedInvestment({ ownerUid: makeLegacyUid("legacy_user"), investor: "legacy", symbolCode: "AAPL", market: "美股" });

  const svc = createCoreService({
    repo,
    quoteProvider: {
      getSymbolName: async (_m, c) => c,
      fetchBatchQuotes: async () => ({}),
    },
  });

  const login = await svc.dispatch({ action: "auth.login", payload: {}, wxContext: makeCtx("openid_2") });
  assert.equal(login.ok, true);

  const bind = await svc.dispatch({
    action: "auth.bindLegacy",
    payload: { username: "legacy_user", password: "123456" },
    wxContext: makeCtx("openid_2"),
  });
  assert.equal(bind.ok, true);
  assert.equal(bind.data.user.boundLegacy, true);

  const list = await svc.dispatch({ action: "portfolio.list", payload: {}, wxContext: makeCtx("openid_2") });
  assert.equal(list.data.rows.length, 1);
  assert.equal(list.data.rows[0].ownerUid, bind.data.user.uid);
});

test("share.inviteByCode and portfolio edit permission", async () => {
  const repo = createMemoryRepo();
  const quoteProvider = {
    getSymbolName: async (_m, c) => c,
    fetchBatchQuotes: async () => ({ AAPL: { symbolCode: "AAPL", market: "美股", price: 100, currency: "USD", stale: false } }),
  };
  const svc = createCoreService({ repo, quoteProvider });

  const owner = await svc.dispatch({ action: "auth.login", payload: { nickname: "owner" }, wxContext: makeCtx("openid_owner") });
  const editor = await svc.dispatch({ action: "auth.login", payload: { nickname: "editor" }, wxContext: makeCtx("openid_editor") });

  const added = await svc.dispatch({
    action: "portfolio.add",
    payload: { investor: "owner", symbolCode: "AAPL", quantity: 1, costPrice: 90 },
    wxContext: makeCtx("openid_owner"),
  });

  await svc.dispatch({
    action: "share.inviteByCode",
    payload: { inviteCode: editor.data.user.inviteCode, permission: "edit" },
    wxContext: makeCtx("openid_owner"),
  });

  const updated = await svc.dispatch({
    action: "portfolio.update",
    payload: { id: added.data.row._id, investor: "owner", quantity: 2, costPrice: 95 },
    wxContext: makeCtx("openid_editor"),
  });
  assert.equal(updated.ok, true);

  const logs = await svc.dispatch({ action: "log.list", payload: { limit: 50 }, wxContext: makeCtx("openid_owner") });
  assert.ok(logs.data.rows.length >= 1);
});

test("quote.batch uses realtime then cache fallback", async () => {
  const repo = createMemoryRepo();
  const svc = createCoreService({
    repo,
    quoteProvider: {
      getSymbolName: async (_m, c) => c,
      fetchBatchQuotes: async () => ({
        AAPL: { symbolCode: "AAPL", market: "美股", price: 123.45, currency: "USD", stale: false },
      }),
    },
  });

  await svc.dispatch({ action: "auth.login", payload: {}, wxContext: makeCtx("openid_quote") });
  const first = await svc.dispatch({
    action: "quote.batch",
    payload: { symbols: [{ symbolCode: "AAPL", market: "美股" }] },
    wxContext: makeCtx("openid_quote"),
  });
  assert.equal(first.ok, true);
  assert.equal(first.data.quotes.AAPL.price, 123.45);

  const svcFailing = createCoreService({
    repo,
    quoteProvider: {
      getSymbolName: async (_m, c) => c,
      fetchBatchQuotes: async () => {
        throw new Error("network down");
      },
    },
  });
  const second = await svcFailing.dispatch({
    action: "quote.batch",
    payload: { symbols: [{ symbolCode: "AAPL", market: "美股" }] },
    wxContext: makeCtx("openid_quote"),
  });
  assert.equal(second.ok, true);
  assert.equal(Number(second.data.quotes.AAPL.price) > 0, true);
});
