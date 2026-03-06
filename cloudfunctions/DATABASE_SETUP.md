# CloudBase 数据库初始化建议

## 1. 集合

请在云开发控制台创建以下集合：

- `users`
- `legacy_users`
- `investments`
- `shares`
- `operation_logs`
- `symbol_cache`
- `price_cache`

## 2. 索引（推荐）

按集合添加索引：

- `users`
  - `openid` 唯一索引
  - `inviteCode` 唯一索引
- `legacy_users`
  - `username` 唯一索引
  - `boundUid` 普通索引
- `investments`
  - `ownerUid` 普通索引
  - `symbolCode` 普通索引
  - `updatedAt` 普通索引
- `shares`
  - 组合唯一索引：`ownerUid + sharedWithUid`
  - `sharedWithUid` 普通索引
- `operation_logs`
  - `ownerUid` 普通索引
  - `actionTime` 普通索引
- `symbol_cache`
  - 组合唯一索引：`market + symbolCode`
- `price_cache`
  - `cacheKey` 唯一索引
  - `expireAt` 普通索引

## 3. 云函数权限

- `core`：HTTP 不开放，保持仅云调用。
- `quote-sync`：配置定时触发（建议每 1 分钟一次）。

## 4. 初始迁移顺序

1. 执行 `scripts/migrate_to_cloudbase.py` 导出 JSON。
2. 导入 `legacy_users / investments / shares / operation_logs / symbol_cache`。
3. 部署 `core` 云函数。
4. 部署 `quote-sync` 云函数并启用定时触发。
5. 打开小程序，微信登录后在登录页进行旧账号绑定。
