# 投资管家 - 微信小程序

一款简洁高效的投资组合管理微信小程序，帮助您轻松追踪和管理投资。

## 📋 页面结构

| 页面 | 路径 | 功能 |
|-----|------|-----|
| 登录页 | `pages/login` | 微信一键登录、旧账号绑定迁移 |
| 资产页 | `pages/portfolio` | 资产总览、持仓列表、实时更新 |
| 编辑页 | `pages/portfolio-edit` | 新增/编辑/删除持仓 |
| 共享页 | `pages/share` | 邀请码共享管理、权限控制 |
| 个人中心 | `pages/profile` | 用户信息、统计数据、设置 |

## 🛠️ 工具函数

| 文件 | 功能 |
|-----|-----|
| `utils/api.js` | 云函数调用封装 |
| `utils/auth.js` | 登录态管理工具 |

## 🎨 设计系统

### 色彩规范

- **主色调**: `#2563eb`（专业蓝）
- **辅助色**: `#0ea5e9`（天蓝）
- **成功/收益**: `#10b981`（绿色）
- **危险/亏损**: `#ef4444`（红色）
- **背景**: `#f1f5f9`（浅灰）

### 组件规范

所有组件样式统一在 `app.wxss` 中定义，使用 CSS 变量确保风格一致性。

## 🚀 部署指南

### 1. 小程序配置

1. 在微信开发者工具导入 `miniapp` 目录
2. 修改 `miniapp/project.config.json` 的 `appid`
3. 云环境配置：
   - **推荐**: `miniapp/app.js` 保持 `envId: ""`，在开发者工具顶部手动选择环境
   - **可选**: 在 `miniapp/app.js` 填入固定 `envId`

### 2. 云函数部署

1. 确认 `project.config.json` 中 `cloudfunctionRoot: "../cloudfunctions"`
2. 右键 `cloudfunctions/core` → 上传并部署（云端安装依赖）
3. 右键 `cloudfunctions/quote-sync` → 上传并部署（云端安装依赖）

### 3. 数据库集合

在云开发控制台创建以下集合：

- `users` - 用户信息
- `legacy_users` - 旧账号数据（可选）
- `investments` - 持仓数据
- `shares` - 共享关系
- `operation_logs` - 操作日志
- `symbol_cache` - 标的缓存
- `price_cache` - 价格缓存

## ⚠️ 常见问题

### 报错：Environment invalid

**原因**: 未绑定有效云环境或选错环境

**处理**:
1. 微信开发者工具顶部切换到正确 CloudBase 环境
2. 确认该环境下已部署 `core` 云函数
3. 重新编译并点击登录

### 报错：FunctionName parameter could not be found

**原因**: 云函数不存在

**处理**:
1. 在开发者工具"云开发 > 云函数"右键 `core` → 上传并部署
2. 如函数名不是 `core`，修改 `miniapp/app.js` 的 `coreFunctionName`

## 📝 开发规范

### 命名规范

- 页面文件：小写 + 连字符 (`portfolio-edit`)
- 变量名：驼峰命名 (`userProfile`)
- 常量名：全大写 + 下划线 (`MAX_COUNT`)
- CSS 类：小写 + 连字符 (`card-header`)

### Git 提交规范

- `feat:` 新功能
- `fix:` 修复
- `style:` 样式
- `refactor:` 重构
- `docs:` 文档
