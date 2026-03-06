const { requireUser } = require("../../utils/auth");

Page({
  data: {
    user: {},
  },

  onShow() {
    const user = requireUser();
    if (!user) return;
    this.setData({ user });
  },

  goBind() {
    wx.navigateTo({ url: "/pages/login/login" });
  },

  logout() {
    const app = getApp();
    app.clearUser();
    wx.redirectTo({ url: "/pages/login/login" });
  },
});
