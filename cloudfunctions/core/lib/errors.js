class AppError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = "AppError";
    this.code = code;
    this.status = status;
  }
}

function asErrorResponse(error) {
  if (error instanceof AppError) {
    return { ok: false, code: error.code, message: error.message };
  }
  return { ok: false, code: "INTERNAL_ERROR", message: error?.message || "内部错误" };
}

module.exports = {
  AppError,
  asErrorResponse,
};
