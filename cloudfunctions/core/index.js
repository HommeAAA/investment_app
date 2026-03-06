const cloud = require("wx-server-sdk");

const { asErrorResponse } = require("./lib/errors");
const { createRepo } = require("./lib/repo");
const { createCoreService } = require("./lib/service");
const quoteProvider = require("./lib/quote");

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const repo = createRepo({ db });
const service = createCoreService({ repo, quoteProvider });

exports.main = async (event, context) => {
  const action = String(event?.action || "").trim();
  const payload = event?.payload || {};
  try {
    return await service.dispatch({ action, payload, wxContext: cloud.getWXContext() || context || {} });
  } catch (error) {
    return asErrorResponse(error);
  }
};
