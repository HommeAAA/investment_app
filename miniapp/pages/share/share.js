const { callCore, showError } = require("../../utils/api");
const { requireUser } = require("../../utils/auth");

Page({
  data: {
    myInviteCode: "",
    inviteCodeInput: "",
    permissionOptions: ["仅查看", "可编辑"],
    permissionIndex: 0,
    invitedByMe: [],
    sharedToMe: [],
    loadingInvite: false,
  },

  async onShow() {
    const user = requireUser();
    if (!user) return;
    this.setData({ myInviteCode: user.inviteCode || "" });
    await this.loadShareList();
  },

  copyMyCode() {
    const code = this.data.myInviteCode;
    if (!code) {
      wx.showToast({ title: "暂无邀请码", icon: "none" });
      return;
    }
    wx.setClipboardData({
      data: code,
      success: () => {
        wx.showToast({ title: "已复制邀请码", icon: "success" });
      },
    });
  },

  onInviteCodeInput(e) {
    this.setData({ inviteCodeInput: (e.detail.value || "").toUpperCase() });
  },

  onPermissionChange(e) {
    this.setData({ permissionIndex: Number(e.detail.value || 0) });
  },

  selectedPermission() {
    return this.data.permissionIndex === 1 ? "edit" : "read";
  },

  async loadShareList() {
    try {
      const data = await callCore("share.list", {});
      this.setData({
        invitedByMe: data.invitedByMe || [],
        sharedToMe: data.sharedToMe || [],
      });
    } catch (error) {
      showError(error, "加载共享失败");
    }
  },

  async onInvite() {
    const code = this.data.inviteCodeInput;
    if (!code) {
      wx.showToast({ title: "请输入邀请码", icon: "none" });
      return;
    }

    this.setData({ loadingInvite: true });
    try {
      await callCore("share.inviteByCode", {
        inviteCode: code,
        permission: this.selectedPermission(),
      });
      wx.showToast({ title: "共享成功", icon: "success" });
      this.setData({ inviteCodeInput: "" });
      await this.loadShareList();
    } catch (error) {
      showError(error, "共享失败");
    } finally {
      this.setData({ loadingInvite: false });
    }
  },

  async onRevoke(e) {
    const uid = e.currentTarget.dataset.uid;
    if (!uid) return;
    
    wx.showModal({
      title: "确认撤销",
      content: "确定要撤销该用户的共享权限吗？",
      success: async (res) => {
        if (res.confirm) {
          try {
            await callCore("share.revoke", { sharedWithUid: uid });
            wx.showToast({ title: "已撤销", icon: "success" });
            await this.loadShareList();
          } catch (error) {
            showError(error, "撤销失败");
          }
        }
      },
    });
  },
});
