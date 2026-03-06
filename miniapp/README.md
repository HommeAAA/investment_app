# Investment MiniApp (CloudBase Native)

## 目录说明

- `pages/login`: 微信登录 + 旧账号绑定
- `pages/portfolio`: 资产列表 + 汇总
- `pages/portfolio-edit`: 新增/编辑/删除
- `pages/share`: 邀请码共享管理
- `pages/logs`: 操作日志
- `pages/profile`: 用户信息与退出
- `utils/api.js`: 云函数调用封装
- `utils/auth.js`: 登录态工具

## 使用步骤

1. 在微信开发者工具导入 `miniapp` 目录。
2. 修改 `miniapp/project.config.json` 的 `appid`。
3. 云环境配置（二选一，推荐第 3.1）：
   - 3.1 推荐：`miniapp/app.js` 保持 `envId: ""`，在微信开发者工具顶部手动选择当前 CloudBase 环境（代码会使用 `wx.cloud.DYNAMIC_CURRENT_ENV`）。
   - 3.2 可选：在 `miniapp/app.js` 填入固定 `envId`（例如 `prod-xxxxxxxx`）。
4. 确认微信开发者工具项目设置包含云函数根目录：
   - `cloudfunctionRoot: "../cloudfunctions"`（已在仓库默认配置）
5. 在云开发控制台创建并部署云函数：
   - `cloudfunctions/core`
   - `cloudfunctions/quote-sync`
6. 创建数据库集合：
   - `users`
   - `legacy_users`
   - `investments`
   - `shares`
   - `operation_logs`
   - `symbol_cache`
   - `price_cache`

## 常见错误

- 报错：`cloud.callFunction:fail ... -501000 Environment invalid`
  - 原因：当前小程序未绑定有效云环境，或选错环境。
  - 处理：
    1. 微信开发者工具顶部切到正确 CloudBase 环境。
    2. 确认该环境下已部署 `core` 云函数。
    3. 重新编译并再次点击“微信一键登录”。

- 报错：`FunctionName parameter could not be found` / `FUNCTION_NOT_FOUND`
  - 原因：当前环境里没有你正在调用的云函数名（默认 `core`）。
  - 处理：
    1. 在开发者工具“云开发 > 云函数”右键 `core` -> 上传并部署（云端安装依赖）。
    2. 若你云端函数名不是 `core`，修改 `miniapp/app.js` 的 `coreFunctionName` 与云端保持一致。

## 迁移历史数据

```bash
python scripts/migrate_to_cloudbase.py --source sqlite:///testApp.db --out-dir cloudbase_migration_out
```

如要直接写入 CloudBase Mongo：

```bash
python scripts/migrate_to_cloudbase.py \
  --source sqlite:///testApp.db \
  --mongo-uri 'mongodb://<user>:<pass>@<host>:<port>/<db>?authSource=admin' \
  --truncate
```
