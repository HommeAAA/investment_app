# 投资管家

一款简洁高效的投资组合管理微信小程序，帮助您轻松追踪和管理投资。

## 📋 项目结构

```
invest/
├── app/                      # 后端核心模块 (Python)
│   ├── __init__.py
│   ├── app.py               # Streamlit 应用入口
│   ├── config.py            # 配置管理
│   ├── db.py                # 数据库连接
│   ├── models.py            # 数据模型
│   ├── repositories.py       # 数据仓库
│   ├── services.py          # 业务逻辑
│   └── ui.py                # UI 组件
│
├── cloudfunctions/           # 云函数
│   ├── core/                # 核心云函数
│   │   ├── index.js
│   │   ├── package.json
│   │   └── lib/             # 云函数工具库
│   ├── quote-sync/          # 行情同步云函数
│   │   ├── index.js
│   │   └── package.json
│   └── README.md
│
├── miniapp/                  # 微信小程序
│   ├── pages/               # 页面
│   │   ├── login/          # 登录页
│   │   ├── portfolio/      # 资产页
│   │   ├── portfolio-edit/ # 编辑页
│   │   ├── share/          # 共享页
│   │   └── profile/        # 个人中心
│   ├── utils/               # 工具函数
│   │   ├── api.js          # API 调用
│   │   └── auth.js         # 认证相关
│   ├── app.js               # 小程序入口
│   ├── app.json             # 小程序配置
│   ├── app.wxss             # 全局样式
│   └── sitemap.json         # 站点地图
│
├── requirements.txt          # Python 依赖
└── .gitignore               # Git 忽略文件
```

## 🎨 设计系统

### 色彩规范

```css
/* 主色系 */
--primary: #2563eb;       /* 专业蓝 */
--secondary: #0ea5e9;     /* 天蓝 */

/* 功能色 */
--success: #10b981;       /* 成功/收益 */
--danger: #ef4444;        /* 危险/亏损 */
--warning: #f59e0b;       /* 警告 */

/* 中性色 */
--bg-page: #f1f5f9;       /* 页面背景 */
--bg-card: #ffffff;       /* 卡片背景 */
--text-primary: #0f172a;  /* 主文字 */
--text-secondary: #475569; /* 次要文字 */
--text-muted: #94a3b8;    /* 弱化文字 */
--border: #e2e8f0;        /* 边框 */
```

### 组件规范

所有组件使用统一的样式类，详见 `app.wxss`

## 📱 功能模块

| 模块 | 路径 | 功能 |
|-----|------|-----|
| 登录 | `pages/login` | 微信登录、旧账号绑定 |
| 资产 | `pages/portfolio` | 资产总览、持仓列表 |
| 编辑 | `pages/portfolio-edit` | 新增/编辑持仓 |
| 共享 | `pages/share` | 共享管理、邀请好友 |
| 个人中心 | `pages/profile` | 用户信息、统计数据 |

## 🚀 部署指南

### 微信小程序

1. 打开微信开发者工具
2. 导入项目，选择 `miniapp` 目录
3. 配置云环境 ID
4. 上传并部署

### 云函数

1. 在微信开发者工具中右键 `cloudfunctions/core`
2. 选择「上传并部署：云端安装依赖」
3. 同步云函数到云端

## 📝 开发规范

### 命名规范

- 文件：小写 + 连字符 (`portfolio-edit`)
- 变量：驼峰命名 (`userProfile`)
- 常量：全大写 + 下划线 (`MAX_COUNT`)
- 组件：PascalCase (`UserCard`)

### 提交规范

- `feat:` 新功能
- `fix:` 修复
- `style:` 样式
- `refactor:` 重构
- `docs:` 文档

## 📄 License

MIT License
