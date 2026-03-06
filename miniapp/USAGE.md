# 微信开发者工具使用指南

## 正确打开项目的方式

### 方法一：直接打开 miniapp 目录（推荐）

1. 打开微信开发者工具
2. 点击「导入项目」或「+」号
3. **项目目录选择**：选择 `miniapp` 文件夹，而不是 `invest` 根目录
   ```
   ✅ 正确：c:\Users\Homme\Documents\anaconda_projects\invest\miniapp
   ❌ 错误：c:\Users\Homme\Documents\anaconda_projects\invest
   ```
4. AppID：选择你的小程序 AppID
5. 点击「导入」

### 方法二：如果已经打开了错误的目录

1. 在微信开发者工具中关闭当前项目
2. 按照方法一重新导入 `miniapp` 目录

## 项目结构说明

```
invest/                    # 项目根目录（不要在开发者工具中打开这个）
├── miniapp/              # 小程序目录（✅ 在开发者工具中打开这个）
│   ├── pages/
│   ├── utils/
│   ├── app.js
│   ├── app.json
│   ├── app.wxss
│   └── project.config.json  # 小程序配置文件
├── cloudfunctions/        # 云函数目录
├── app/                   # Python 后端
└── README.md
```

## 云函数配置

云函数目录在 `../cloudfunctions/`（相对于 miniapp 目录），这已经在 `project.config.json` 中正确配置了。

## 常见问题

### Q: 提示「在项目根目录未找到 app.json」

**A**: 这是因为你打开了错误的目录。请关闭项目，重新打开 `miniapp` 文件夹。

### Q: 云函数找不到

**A**: 确认 `project.config.json` 中的 `cloudfunctionRoot` 设置为 `"../cloudfunctions/"`

### Q: 如何恢复配置文件

**A**: 如果配置文件丢失，可以复制 `project.config.json.example` 为 `project.config.json`，然后修改 appid。
