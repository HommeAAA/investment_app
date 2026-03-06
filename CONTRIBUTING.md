# 开发规范手册

## 命名规范

### 文件命名

| 类型 | 规范 | 示例 |
|-----|------|-----|
| 页面文件 | 小写 + 连字符 | `portfolio-edit` |
| 组件文件 | PascalCase | `UserCard` |
| 工具文件 | 小写 + 连字符 | `api-helper` |
| 配置文件 | 小写 | `config` |

### 变量命名

| 类型 | 规范 | 示例 |
|-----|------|-----|
| 变量 | 驼峰命名 | `userProfile` |
| 常量 | 全大写 + 下划线 | `MAX_COUNT` |
| 私有变量 | 下划线前缀 | `_internalData` |
| 函数 | 动词开头 | `getUserProfile` |

### CSS 类名

```css
/* BEM 风格 */
.card { }
.card__header { }
.card__header--active { }

/* 简写风格 */
.card-header { }
.card-header.active { }
```

## 代码规范

### JavaScript/微信小程序

```javascript
// 1. 严格模式
'use strict';

// 2. 变量声明优先使用 const，次之 let
const app = getApp();
let count = 0;

// 3. 函数注释
/**
 * 获取用户信息
 * @param {string} uid - 用户ID
 * @returns {Promise<Object>} 用户信息
 */
async function getUser(uid) { }

// 4. 错误处理
try {
  await doSomething();
} catch (error) {
  console.error('操作失败:', error);
  showError(error);
}
```

### Python

```python
# 1. 类型注解
def calculate_profit(cost: float, mv: float) -> float:
    return mv - cost

# 2. 文档字符串
def get_user(uid: str) -> dict:
    """获取用户信息
    
    Args:
        uid: 用户ID
        
    Returns:
        用户信息字典
        
    Raises:
        UserNotFoundError: 用户不存在
    """
    pass

# 3. 类型检查（可选）
from typing import List, Optional
```

## Git 提交规范

### 提交格式

```
<type>(<scope>): <subject>

<body>
```

### Type 类型

| 类型 | 说明 |
|-----|------|
| feat | 新功能 |
| fix | 修复 |
| style | 样式调整 |
| refactor | 重构 |
| docs | 文档 |
| test | 测试 |
| chore | 构建/工具 |

### 示例

```
feat(portfolio): 添加收益率显示

- 计算并显示持仓收益率
- 根据收益自动着色（绿涨红跌）
- 优化数据展示格式

Closes #123
```

## 目录结构规范

```
miniapp/
├── pages/              # 页面
│   └── [page-name]/
│       ├── [page-name].js
│       ├── [page-name].json
│       ├── [page-name].wxml
│       └── [page-name].wxss
├── components/         # 组件（可选）
│   └── [ComponentName]/
├── utils/             # 工具函数
├── images/            # 图片资源
├── styles/            # 公共样式
├── app.js
├── app.json
└── app.wxss
```

## 性能优化规范

### 小程序

1. **图片优化**
   - 使用 WebP 格式
   - 图片尺寸适中
   - 懒加载非首屏图片

2. **数据缓存**
   ```javascript
   // 使用 setStorage 缓存数据
   wx.setStorageSync('key', data);
   
   // 使用 app 全局数据
   app.globalData.user = user;
   ```

3. **列表渲染**
   - 使用 `wx:key`
   - 避免复杂的嵌套循环
   - 虚拟列表（长列表）

### Python

1. **数据库查询**
   - 使用索引
   - 避免 N+1 查询
   - 批量操作

2. **缓存策略**
   - 使用 LRU 缓存
   - 缓存热点数据
   - 设置合理的过期时间

## 安全规范

### 敏感信息

```javascript
// ✅ 正确：使用环境变量
const apiKey = process.env.API_KEY;

// ❌ 错误：硬编码
const apiKey = 'sk-xxxxxx';
```

### 输入验证

```javascript
// 验证用户输入
function validateInput(input) {
  if (!input || input.trim() === '') {
    throw new Error('输入不能为空');
  }
  return input.trim();
}
```

## 可访问性规范

### 颜色对比度

- 正文文字对比度 ≥ 4.5:1
- 大文字对比度 ≥ 3:1
- 图标颜色要有足够对比度

### 焦点状态

```css
/* 明确的焦点样式 */
button:focus,
input:focus {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
```

### 触摸目标

- 最小触摸区域：44px × 44px（88rpx × 88rpx）
- 按钮间距至少 8px

## 测试规范

### 单元测试

```javascript
// 测试文件命名：[module].test.js
describe('auth module', () => {
  test('should login successfully', async () => {
    const user = await login();
    expect(user.uid).toBeDefined();
  });
});
```

### 测试覆盖率

- 核心业务逻辑覆盖率 ≥ 80%
- 工具函数覆盖率 ≥ 90%

## 文档规范

### 注释原则

- 代码本身是最好的文档
- 注释解释"为什么"而不是"是什么"
- 保持注释与代码同步

### README 结构

```markdown
# 项目名称

## 简介
简要说明项目用途

## 功能特性
- 特性1
- 特性2

## 快速开始
### 安装
### 配置
### 运行

## 开发指南
### 目录结构
### 开发规范
### 测试

## 部署
### 环境要求
### 部署步骤

## FAQ
常见问题

## License
许可证信息
```
