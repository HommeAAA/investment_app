const bcrypt = require("bcryptjs");
const crypto = require("crypto");
const { AppError } = require("./errors");
const {
  identifyMarket,
  marketCurrency,
  normalizePermission,
  makeLegacyUid,
  isLegacyUid,
  safeNumber,
  nowIso,
} = require("./utils");

function userView(user) {
  if (!user) return null;
  return {
    uid: user._id,
    openid: user.openid,
    nickname: user.nickname || "",
    inviteCode: user.inviteCode || "",
    boundLegacy: !!user.boundLegacy,
    legacyUsername: user.legacyUsername || "",
    createdAt: user.createdAt || "",
  };
}

function createCoreService({ repo, quoteProvider }) {
  function verifyLegacyPassword(plain, hashed) {
    const hash = String(hashed || "");
    if (!hash) return false;
    const isHex64 = /^[0-9a-fA-F]{64}$/.test(hash);
    if (isHex64) {
      const legacy = crypto.createHash("sha256").update(String(plain || ""), "utf-8").digest("hex");
      return legacy === hash;
    }
    return bcrypt.compareSync(String(plain || ""), hash);
  }

  async function requireUser(wxContext, payload = {}) {
    const openid = wxContext?.OPENID || wxContext?.openid;
    if (!openid) throw new AppError("UNAUTHORIZED", "未获取到微信身份", 401);
    const nickname = payload.nickname || payload.userInfo?.nickName || "";
    const unionid = wxContext?.UNIONID || wxContext?.unionid || "";
    const user = await repo.getOrCreateUserByOpenId({ openid, unionid, nickname });
    if (!user) throw new AppError("UNAUTHORIZED", "登录失败", 401);
    return user;
  }

  async function canEdit(ownerUid, actorUid) {
    if (!ownerUid || !actorUid) return false;
    if (ownerUid === actorUid) return true;
    const share = await repo.getShare(ownerUid, actorUid);
    return !!share && share.permission === "edit";
  }

  async function authLogin(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    return { user: userView(user) };
  }

  async function authBindLegacy(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const username = String(payload.username || "").trim();
    const password = String(payload.password || "");

    if (!username || !password) {
      throw new AppError("INVALID_PARAMS", "请填写旧账号用户名和密码");
    }
    if (user.boundLegacy) {
      throw new AppError("ALREADY_BOUND", "当前微信账号已绑定旧账号");
    }

    const legacy = await repo.getLegacyUser(username);
    if (!legacy) {
      throw new AppError("LEGACY_NOT_FOUND", "旧账号不存在");
    }
    if (legacy.boundUid && legacy.boundUid !== user._id) {
      throw new AppError("LEGACY_BOUND", "该旧账号已被其他微信账号绑定");
    }

    const ok = verifyLegacyPassword(password, legacy.passwordHash || "");
    if (!ok) {
      throw new AppError("INVALID_CREDENTIALS", "旧账号密码错误");
    }

    await repo.bindLegacyAccount({ uid: user._id, legacyUsername: username, legacyUid: makeLegacyUid(username) });
    const refreshed = await repo.getUserById(user._id);
    return { user: userView(refreshed) };
  }

  async function portfolioList(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const owners = await repo.listAccessibleOwnerIds(user._id);
    const rows = await repo.listInvestmentsByOwners(owners);
    const shareRows = await repo.listSharesBySharedWith(user._id);
    const sharePermissions = {};
    for (const row of shareRows) {
      sharePermissions[row.ownerUid] = row.permission || "read";
    }
    return { rows, owners, sharePermissions };
  }

  async function portfolioAdd(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const symbolCode = String(payload.symbolCode || "").trim().toUpperCase();
    const investor = String(payload.investor || user.nickname || "我的资产").trim();
    const channel = String(payload.channel || "").trim();
    const quantity = safeNumber(payload.quantity);
    const costPrice = safeNumber(payload.costPrice);

    if (!symbolCode || quantity <= 0) {
      throw new AppError("INVALID_PARAMS", "标的代码和数量必须有效");
    }

    const market = payload.market || identifyMarket(symbolCode);
    let symbolName = String(payload.symbolName || "").trim();
    if (!symbolName) {
      symbolName = await quoteProvider.getSymbolName(market, symbolCode);
    }

    const row = await repo.addInvestment({
      ownerUid: user._id,
      investor: investor || user.nickname || "默认投资人",
      market,
      symbolCode,
      symbolName: symbolName || symbolCode,
      channel,
      costPrice,
      quantity,
      currency: marketCurrency(market),
    });

    await repo.upsertSymbols([{ market, symbolCode, symbolName: row.symbolName }], "portfolio_add");
    await repo.addOperationLog({
      entityType: "investment",
      entityId: row._id,
      action: "create",
      operatorUid: user._id,
      ownerUid: user._id,
      changedFields: "*",
      beforeData: "",
      afterData: JSON.stringify(row),
      actionTime: nowIso(),
    });

    return { row };
  }

  async function portfolioUpdate(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const id = String(payload.id || "").trim();
    if (!id) throw new AppError("INVALID_PARAMS", "缺少记录ID");

    const row = await repo.getInvestmentById(id);
    if (!row) throw new AppError("NOT_FOUND", "记录不存在", 404);
    if (!(await canEdit(row.ownerUid, user._id))) {
      throw new AppError("FORBIDDEN", "你没有编辑权限", 403);
    }

    const patch = {
      investor: String(payload.investor || row.investor || "").trim() || row.investor,
      costPrice: safeNumber(payload.costPrice, row.costPrice),
      quantity: safeNumber(payload.quantity, row.quantity),
    };
    const updated = await repo.updateInvestment(id, patch);

    await repo.addOperationLog({
      entityType: "investment",
      entityId: id,
      action: "update",
      operatorUid: user._id,
      ownerUid: row.ownerUid,
      changedFields: "investor,costPrice,quantity",
      beforeData: JSON.stringify({ investor: row.investor, costPrice: row.costPrice, quantity: row.quantity }),
      afterData: JSON.stringify({ investor: updated.investor, costPrice: updated.costPrice, quantity: updated.quantity }),
      actionTime: nowIso(),
    });

    return { row: updated };
  }

  async function portfolioDelete(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const id = String(payload.id || "").trim();
    if (!id) throw new AppError("INVALID_PARAMS", "缺少记录ID");

    const row = await repo.getInvestmentById(id);
    if (!row) throw new AppError("NOT_FOUND", "记录不存在", 404);
    if (!(await canEdit(row.ownerUid, user._id))) {
      throw new AppError("FORBIDDEN", "你没有删除权限", 403);
    }

    await repo.deleteInvestment(id);
    await repo.addOperationLog({
      entityType: "investment",
      entityId: id,
      action: "delete",
      operatorUid: user._id,
      ownerUid: row.ownerUid,
      changedFields: "*",
      beforeData: JSON.stringify(row),
      afterData: "",
      actionTime: nowIso(),
    });

    return { deleted: true };
  }

  async function portfolioInvestorReassign(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const fromInvestor = String(payload.fromInvestor || "").trim();
    const toInvestor = String(payload.toInvestor || "").trim();
    if (!fromInvestor || !toInvestor) {
      throw new AppError("INVALID_PARAMS", "请提供转移前后的投资人名称");
    }

    const affected = await repo.reassignInvestor(user._id, fromInvestor, toInvestor);
    await repo.addOperationLog({
      entityType: "investor",
      entityId: fromInvestor,
      action: "reassign",
      operatorUid: user._id,
      ownerUid: user._id,
      changedFields: "investor",
      beforeData: JSON.stringify({ fromInvestor }),
      afterData: JSON.stringify({ toInvestor, affected }),
      actionTime: nowIso(),
    });

    return { affected };
  }

  async function shareInviteByCode(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const inviteCode = String(payload.inviteCode || "").trim().toUpperCase();
    const permission = normalizePermission(payload.permission);

    if (!inviteCode) throw new AppError("INVALID_PARAMS", "邀请码不能为空");
    const target = await repo.getUserByInviteCode(inviteCode);
    if (!target) throw new AppError("INVITE_NOT_FOUND", "邀请码无效");
    if (target._id === user._id) throw new AppError("INVALID_PARAMS", "不能共享给自己");

    const share = await repo.upsertShare({ ownerUid: user._id, sharedWithUid: target._id, permission });
    return {
      share,
      target: userView(target),
    };
  }

  async function shareList(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const invitedByMe = await repo.listSharesByOwner(user._id);
    const sharedToMe = await repo.listSharesBySharedWith(user._id);

    const userIds = [...new Set([
      ...invitedByMe.map((x) => x.sharedWithUid),
      ...sharedToMe.map((x) => x.ownerUid),
    ].filter((x) => x && !isLegacyUid(x)))];
    const users = await repo.getUsersByIds(userIds);
    const map = new Map(users.map((x) => [x._id, userView(x)]));

    return {
      invitedByMe: invitedByMe.map((x) => ({ ...x, targetUser: map.get(x.sharedWithUid) || null })),
      sharedToMe: sharedToMe.map((x) => ({ ...x, ownerUser: map.get(x.ownerUid) || null })),
    };
  }

  async function shareRevoke(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const sharedWithUid = String(payload.sharedWithUid || "").trim();
    if (!sharedWithUid) throw new AppError("INVALID_PARAMS", "缺少 sharedWithUid");

    const ok = await repo.deleteShare(user._id, sharedWithUid);
    return { revoked: ok };
  }

  async function logList(wxContext, payload = {}) {
    const user = await requireUser(wxContext, payload);
    const owners = await repo.listAccessibleOwnerIds(user._id);
    const logs = await repo.listOperationLogsByOwners(owners, {
      limit: safeNumber(payload.limit, 100),
      offset: safeNumber(payload.offset, 0),
    });
    return { rows: logs };
  }

  async function symbolSearch(wxContext, payload = {}) {
    await requireUser(wxContext, payload);
    const keyword = String(payload.keyword || "").trim();
    if (!keyword) return { rows: [] };
    const rows = await repo.searchSymbols(keyword, safeNumber(payload.limit, 20));
    return { rows };
  }

  async function quoteBatch(wxContext, payload = {}) {
    await requireUser(wxContext, payload);
    const symbols = Array.isArray(payload.symbols) ? payload.symbols : [];
    if (!symbols.length) return { quotes: {}, stale: false };

    const normalized = symbols
      .map((x) => ({
        symbolCode: String(x.symbolCode || "").trim().toUpperCase(),
        market: x.market || identifyMarket(x.symbolCode),
      }))
      .filter((x) => x.symbolCode);

    const cacheRows = await repo.getPriceCache(normalized);
    const now = Date.now();
    const quoteMap = {};
    const missing = [];

    for (const item of normalized) {
      const cacheKey = repo.makePriceKey(item.market, item.symbolCode);
      const cached = cacheRows.find((r) => r.cacheKey === cacheKey);
      if (cached && cached.expireAt && Date.parse(cached.expireAt) > now) {
        quoteMap[item.symbolCode] = {
          symbolCode: item.symbolCode,
          market: item.market,
          price: safeNumber(cached.price),
          currency: cached.currency || marketCurrency(item.market),
          stale: !!cached.stale,
          source: "cache",
        };
      } else {
        missing.push(item);
      }
    }

    if (missing.length) {
      let remoteMap = {};
      try {
        remoteMap = await quoteProvider.fetchBatchQuotes(missing);
      } catch (_err) {
        remoteMap = {};
      }
      const toUpsert = [];
      for (const item of missing) {
        const remote = remoteMap[item.symbolCode];
        if (remote && safeNumber(remote.price) > 0) {
          const row = {
            symbolCode: item.symbolCode,
            market: item.market,
            price: safeNumber(remote.price),
            currency: remote.currency || marketCurrency(item.market),
            stale: !!remote.stale,
          };
          quoteMap[item.symbolCode] = { ...row, source: "realtime" };
          toUpsert.push(row);
        } else {
          const fallback = cacheRows.find((r) => r.cacheKey === repo.makePriceKey(item.market, item.symbolCode));
          if (fallback) {
            quoteMap[item.symbolCode] = {
              symbolCode: item.symbolCode,
              market: item.market,
              price: safeNumber(fallback.price),
              currency: fallback.currency || marketCurrency(item.market),
              stale: true,
              source: "stale-cache",
            };
          } else {
            quoteMap[item.symbolCode] = {
              symbolCode: item.symbolCode,
              market: item.market,
              price: 0,
              currency: marketCurrency(item.market),
              stale: true,
              source: "failed",
            };
          }
        }
      }
      if (toUpsert.length) {
        await repo.upsertPriceCache(toUpsert, 60);
      }
    }

    return { quotes: quoteMap };
  }

  async function systemPing(wxContext) {
    return {
      status: "ok",
      serverTime: nowIso(),
      openidPresent: !!(wxContext?.OPENID || wxContext?.openid),
    };
  }

  const actions = {
    "system.ping": systemPing,
    "auth.login": authLogin,
    "auth.bindLegacy": authBindLegacy,
    "portfolio.list": portfolioList,
    "portfolio.add": portfolioAdd,
    "portfolio.update": portfolioUpdate,
    "portfolio.delete": portfolioDelete,
    "portfolio.investor.reassign": portfolioInvestorReassign,
    "share.inviteByCode": shareInviteByCode,
    "share.list": shareList,
    "share.revoke": shareRevoke,
    "log.list": logList,
    "quote.batch": quoteBatch,
    "symbol.search": symbolSearch,
  };

  async function dispatch({ action, payload, wxContext }) {
    const fn = actions[action];
    if (!fn) throw new AppError("UNKNOWN_ACTION", `不支持的 action: ${action}`);
    const data = await fn(wxContext, payload || {});
    return { ok: true, data };
  }

  return {
    dispatch,
    actions,
  };
}

module.exports = {
  createCoreService,
  userView,
};
