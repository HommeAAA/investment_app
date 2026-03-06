const { callCore, showError } = require("../../utils/api");
const { requireUser, loginAndLoadUser } = require("../../utils/auth");

function toFixed(value, digits = 2) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toFixed(digits) : "0.00";
}

function getProfitClass(value) {
  if (value > 0) return "profit";
  if (value < 0) return "loss";
  return "neutral";
}

function formatProfitPercent(cost, mv) {
  if (cost <= 0) return "0.00%";
  const percent = ((mv - cost) / cost) * 100;
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(2)}%`;
}

Page({
  data: {
    loading: false,
    rows: [],
    summary: {
      totalCostText: "0.00",
      totalMvText: "0.00",
      totalProfitText: "0.00",
      profitClass: "neutral",
    },
  },

  async onShow() {
    let user = requireUser();
    if (!user) return;
    if (!user.uid) {
      user = await loginAndLoadUser();
      if (!user || !user.uid) {
        wx.redirectTo({ url: "/pages/login/login" });
        return;
      }
    }
    await this.refreshAll();
  },

  async refreshAll() {
    this.setData({ loading: true });
    try {
      const user = requireUser();
      if (!user) return;

      const listData = await callCore("portfolio.list", {});
      const rows = listData.rows || [];
      const symbols = rows.map((x) => ({ symbolCode: x.symbolCode, market: x.market }));
      const quoteData = symbols.length ? await callCore("quote.batch", { symbols }) : { quotes: {} };
      const quoteMap = quoteData.quotes || {};
      const permissionMap = listData.sharePermissions || {};

      let totalCost = 0;
      let totalMv = 0;

      const viewRows = rows.map((row) => {
        const quote = quoteMap[row.symbolCode] || { price: 0, currency: row.currency || "USD" };
        const cost = Number(row.costPrice || 0) * Number(row.quantity || 0);
        const mv = Number(quote.price || 0) * Number(row.quantity || 0);
        totalCost += cost;
        totalMv += mv;

        const profitValue = mv - cost;

        return {
          ...row,
          ownerLabel: row.ownerUid === user.uid ? "我" : "共享",
          editable: row.ownerUid === user.uid || permissionMap[row.ownerUid] === "edit",
          currentPrice: toFixed(quote.price, 4),
          currency: quote.currency || "USD",
          currentMv: toFixed(mv, 2),
          profit: toFixed(profitValue, 2),
          profitClass: getProfitClass(profitValue),
          profitPercent: formatProfitPercent(cost, mv),
        };
      });

      const totalProfit = totalMv - totalCost;

      this.setData({
        rows: viewRows,
        summary: {
          totalCostText: toFixed(totalCost, 2),
          totalMvText: toFixed(totalMv, 2),
          totalProfitText: toFixed(totalProfit, 2),
          profitClass: getProfitClass(totalProfit),
        },
      });
    } catch (error) {
      showError(error, "加载失败");
    } finally {
      this.setData({ loading: false });
    }
  },

  goEdit(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/portfolio-edit/portfolio-edit?id=${id}` });
  },
});
