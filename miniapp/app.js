App({
  globalData: {
    // 可选：填你的固定环境 ID；留空则使用微信开发者工具当前选中的云环境
    envId: "cloud1-4gc1cjgc9bad2689",
    // 云函数名称，默认 core。若控制台实际名称不同，请改这里。
    coreFunctionName: "core",
    user: null,
  },

  onLaunch() {
    if (!wx.cloud) {
      console.error("请使用基础库 2.2.3 或以上以使用云能力");
      return;
    }
    const env = this.globalData.envId || wx.cloud.DYNAMIC_CURRENT_ENV;
    wx.cloud.init({ env, traceUser: true });
    console.log("Cloud env:", env);
    console.log("Core function:", this.globalData.coreFunctionName);

    const cachedUser = wx.getStorageSync("current_user");
    if (cachedUser) {
      this.globalData.user = cachedUser;
    }
  },

  setUser(user) {
    this.globalData.user = user;
    wx.setStorageSync("current_user", user || null);
  },

  clearUser() {
    this.globalData.user = null;
    wx.removeStorageSync("current_user");
  },
});
