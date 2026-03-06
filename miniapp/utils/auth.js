const { callCore } = require("./api");

async function loginAndLoadUser() {
  await wx.login();
  const data = await callCore("auth.login", {});
  const app = getApp();
  app.setUser(data.user || null);
  return data.user || null;
}

function requireUser() {
  const app = getApp();
  const user = app.globalData.user;
  if (!user || !user.uid) {
    wx.redirectTo({ url: "/pages/login/login" });
    return null;
  }
  return user;
}

module.exports = {
  loginAndLoadUser,
  requireUser,
};
