const { requireUser } = require("../../utils/auth");
const { callCore } = require("../../utils/api");

Page({
  data: {
    user: {},
    stats: {
      holdings: 0,
      sharedUsers: 0,
      days: 0,
    },
    version: "1.0.0",
  },

  async onShow() {
    const user = requireUser();
    if (!user) return;
    this.setData({ user });
    await this.loadStats();
  },

  async loadStats() {
    try {
      const listData = await callCore("portfolio.list", {});
      const holdings = (listData.rows || []).length;
      
      const shareData = await callCore("share.list", {});
      const sharedUsers = (shareData.shares || []).length;

      const user = this.data.user;
      const createdAt = user.createdAt ? new Date(user.createdAt) : new Date();
      const days = Math.max(1, Math.floor((Date.now() - createdAt.getTime()) / (1000 * 60 * 60 * 24)));

      this.setData({
        stats: { holdings, sharedUsers, days },
      });
    } catch (error) {
      console.error("加载统计失败", error);
    }
  },

  copyInviteCode() {
    const code = this.data.user.inviteCode;
    if (!code) return;
    wx.setClipboardData({
      data: code,
      success: () => {
        wx.showToast({ title: "已复制", icon: "success" });
      },
    });
  },

  goShare() {
    wx.navigateTo({ url: "/pages/share/share" });
  },

  goInvite() {
    const code = this.data.user.inviteCode;
    if (!code) {
      wx.showToast({ title: "暂无邀请码", icon: "none" });
      return;
    }
    wx.setClipboardData({
      data: `邀请您使用投资管家小程序，邀请码：${code}`,
      success: () => {
        wx.showToast({ title: "已复制邀请信息", icon: "success" });
      },
    });
  },

  goFeedback() {
    wx.showModal({
      title: "意见反馈",
      content: "请添加微信：invest_helper 反馈问题",
      showCancel: false,
    });
  },

  goAbout() {
    wx.showModal({
      title: "关于投资管家",
      content: `版本：${this.data.version}\n\n投资管家是一款简洁高效的投资组合管理工具，帮助您轻松追踪和管理投资。`,
      showCancel: false,
    });
  },

  onLogout() {
    wx.showModal({
      title: "确认退出",
      content: "确定要退出登录吗？",
      success: (res) => {
        if (res.confirm) {
          const app = getApp();
          app.clearUser();
          wx.redirectTo({ url: "/pages/login/login" });
        }
      },
    });
  },
});
