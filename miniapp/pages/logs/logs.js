const { callCore, showError } = require("../../utils/api");
const { requireUser } = require("../../utils/auth");

Page({
  data: {
    loading: false,
    rows: [],
  },

  async onShow() {
    if (!requireUser()) return;
    await this.loadLogs();
  },

  async loadLogs() {
    this.setData({ loading: true });
    try {
      const data = await callCore("log.list", { limit: 100, offset: 0 });
      this.setData({ rows: data.rows || [] });
    } catch (error) {
      showError(error, "加载日志失败");
    } finally {
      this.setData({ loading: false });
    }
  },
});
