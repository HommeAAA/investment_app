const { callCore, showError } = require("../../utils/api");
const { requireUser } = require("../../utils/auth");

Page({
  data: {
    id: "",
    isEdit: false,
    loading: false,
    loadingDelete: false,
    form: {
      investor: "",
      symbolCode: "",
      market: "",
      channel: "",
      costPrice: "",
      quantity: "",
    },
  },

  async onLoad(options) {
    const user = requireUser();
    if (!user) return;

    const id = options && options.id ? options.id : "";
    if (!id) {
      this.setData({ isEdit: false, id: "", form: { ...this.data.form, investor: user.nickname || "" } });
      return;
    }

    this.setData({ id, isEdit: true });
    await this.loadCurrentRow(id);
  },

  async loadCurrentRow(id) {
    try {
      const list = await callCore("portfolio.list", {});
      const row = (list.rows || []).find((x) => x._id === id);
      if (!row) {
        wx.showToast({ title: "记录不存在", icon: "none" });
        return;
      }
      this.setData({
        form: {
          investor: row.investor || "",
          symbolCode: row.symbolCode || "",
          market: row.market || "",
          channel: row.channel || "",
          costPrice: String(row.costPrice || ""),
          quantity: String(row.quantity || ""),
        },
      });
    } catch (error) {
      showError(error, "加载失败");
    }
  },

  onInvestorInput(e) { this.setData({ "form.investor": e.detail.value }); },
  onSymbolInput(e) { this.setData({ "form.symbolCode": e.detail.value.toUpperCase() }); },
  onMarketInput(e) { this.setData({ "form.market": e.detail.value }); },
  onChannelInput(e) { this.setData({ "form.channel": e.detail.value }); },
  onCostInput(e) { this.setData({ "form.costPrice": e.detail.value }); },
  onQtyInput(e) { this.setData({ "form.quantity": e.detail.value }); },

  async onSubmit() {
    const user = requireUser();
    if (!user) return;

    const { id, isEdit, form } = this.data;
    if (!form.symbolCode || Number(form.quantity || 0) <= 0) {
      wx.showToast({ title: "代码和数量必填", icon: "none" });
      return;
    }

    this.setData({ loading: true });
    try {
      if (!isEdit) {
        await callCore("portfolio.add", {
          investor: form.investor,
          symbolCode: form.symbolCode,
          market: form.market,
          channel: form.channel,
          costPrice: Number(form.costPrice || 0),
          quantity: Number(form.quantity || 0),
        });
        wx.showToast({ title: "新增成功", icon: "success" });
      } else {
        await callCore("portfolio.update", {
          id,
          investor: form.investor,
          costPrice: Number(form.costPrice || 0),
          quantity: Number(form.quantity || 0),
        });
        wx.showToast({ title: "更新成功", icon: "success" });
      }
      wx.switchTab({ url: "/pages/portfolio/portfolio" });
    } catch (error) {
      showError(error, isEdit ? "更新失败" : "新增失败");
    } finally {
      this.setData({ loading: false });
    }
  },

  async onDelete() {
    if (!this.data.isEdit || !this.data.id) return;

    this.setData({ loadingDelete: true });
    try {
      await callCore("portfolio.delete", { id: this.data.id });
      wx.showToast({ title: "删除成功", icon: "success" });
      wx.switchTab({ url: "/pages/portfolio/portfolio" });
    } catch (error) {
      showError(error, "删除失败");
    } finally {
      this.setData({ loadingDelete: false });
    }
  },
});
