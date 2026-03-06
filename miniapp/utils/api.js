async function callCore(action, payload = {}) {
  const app = getApp();
  const functionName = app?.globalData?.coreFunctionName || "core";
  let res;
  try {
    res = await wx.cloud.callFunction({
      name: functionName,
      data: { action, payload },
    });
  } catch (rawError) {
    const text = rawError && (rawError.errMsg || rawError.message || String(rawError));
    if (text && (text.includes("Environment invalid") || text.includes("-501000"))) {
      if (text.includes("FunctionName parameter could not be found") || text.includes("FUNCTION_NOT_FOUND")) {
        const err = new Error(
          `云函数不存在：当前调用 "${functionName}"，请在该云环境部署同名函数或修改 app.js 的 coreFunctionName`
        );
        err.code = "FUNCTION_NOT_FOUND";
        throw err;
      }
      const err = new Error("云开发环境无效：请在微信开发者工具顶部选择正确 CloudBase 环境后重试");
      err.code = "INVALID_ENV";
      throw err;
    }
    const err = new Error(text || "云函数调用失败");
    err.code = rawError?.errCode ? String(rawError.errCode) : "CALL_FUNCTION_FAIL";
    throw err;
  }

  const rawResult = res && typeof res.result !== "undefined" ? res.result : null;
  if (
    rawResult &&
    typeof rawResult === "object" &&
    !("ok" in rawResult) &&
    "action" in rawResult &&
    "payload" in rawResult
  ) {
    const err = new Error("云函数 core 仍是默认模板，请重新上传部署 cloudfunctions/core（云端安装依赖）");
    err.code = "DEPLOY_REQUIRED";
    throw err;
  }

  const data = rawResult || { ok: false, code: "EMPTY_RESULT", message: "云函数无返回" };
  if (!data.ok) {
    const rawMessage = String(data.message || "");
    let message = rawMessage || "请求失败";
    if (data.code === "INTERNAL_ERROR" && /collection|集合|not exist|does not exist/i.test(rawMessage)) {
      message = "数据库集合未创建，请先在云开发数据库创建 users / investments / shares 等集合";
    }
    const err = new Error(message);
    err.code = data.code || "UNKNOWN";
    err.action = action;
    throw err;
  }
  return data.data;
}

function showError(error, fallback = "请求失败") {
  const message = error?.message || fallback;
  const code = error?.code ? `\n错误码: ${error.code}` : "";
  const content = `${message}${code}`;
  wx.showModal({
    title: "操作失败",
    content,
    showCancel: false,
  });
}

module.exports = {
  callCore,
  showError,
};
