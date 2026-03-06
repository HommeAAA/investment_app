const { callCore, showError } = require("../../utils/api");
const { loginAndLoadUser } = require("../../utils/auth");

Page({
  data: {
    loadingCheck: false,
    loadingLogin: false,
    loadingBind: false,
    user: null,
    legacyUsername: "",
    legacyPassword: "",
  },

  async onShow() {
    const app = getApp();
    if (app.globalData.user && app.globalData.user.uid) {
      this.setData({ user: app.globalData.user });
    }
  },

  async onCheckCloud() {
    this.setData({ loadingCheck: true });
    try {
      const info = await callCore("system.ping", {});
      wx.showModal({
        title: "云函数正常",
        content: `已连通 core 云函数\n服务器时间: ${info.serverTime}`,
        showCancel: false,
      });
    } catch (error) {
      showError(error, "云函数连接失败");
    } finally {
      this.setData({ loadingCheck: false });
    }
  },

  async onWechatLogin() {
    this.setData({ loadingLogin: true });
    try {
      const user = await loginAndLoadUser();
      this.setData({ user });
      if (user && user.uid) {
        wx.switchTab({ url: "/pages/portfolio/portfolio" });
      }
    } catch (error) {
      showError(error, "微信登录失败");
    } finally {
      this.setData({ loadingLogin: false });
    }
  },

  onLegacyUsernameInput(e) {
    this.setData({ legacyUsername: e.detail.value });
  },

  onLegacyPasswordInput(e) {
    this.setData({ legacyPassword: e.detail.value });
  },

  async onBindLegacy() {
    const { legacyUsername, legacyPassword } = this.data;
    if (!legacyUsername || !legacyPassword) {
      wx.showToast({ title: "请输入旧账号信息", icon: "none" });
      return;
    }

    this.setData({ loadingBind: true });
    try {
      const data = await callCore("auth.bindLegacy", {
        username: legacyUsername,
        password: legacyPassword,
      });
      const app = getApp();
      app.setUser(data.user || null);
      this.setData({ user: data.user || null, legacyPassword: "" });
      wx.showToast({ title: "绑定成功", icon: "success" });
      wx.switchTab({ url: "/pages/portfolio/portfolio" });
    } catch (error) {
      showError(error, "绑定失败");
    } finally {
      this.setData({ loadingBind: false });
    }
  },

  goPortfolio() {
    wx.switchTab({ url: "/pages/portfolio/portfolio" });
  },
});
