# iPhone 直接使用（无需上架）

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 启动应用

```bash
streamlit run testApp.py --server.address 0.0.0.0 --server.port 8501
```

## 3. 暴露为 HTTPS 地址（Face ID 必须）

Face ID/Passkey 需要 HTTPS 域名（或 localhost）。

可选方式：
- Cloudflare Tunnel
- ngrok
- 你自己的 HTTPS 反向代理

示例（Cloudflare Tunnel）：

```bash
cloudflared tunnel --url http://localhost:8501
```

## 4. iPhone 上直接使用

1. 用 iPhone 的 Safari 打开 HTTPS 地址。
2. 点击“分享” -> “添加到主屏幕”。
3. 首次用用户名/密码登录。
4. 在侧边栏“Face ID 登录”中点击“在当前设备启用 Face ID”。
5. 退出登录后，回到登录页点击“使用 Face ID 登录”。

## 5. 关键说明

- 不需要 App Store 上架。
- 本质是安装到主屏幕的 Web App（PWA 使用方式）。
- Passkey 绑定的是域名：如果你每次都换随机域名，之前的 Face ID 凭证会失效。建议固定域名。

## 6. 固定 HTTPS 域名部署（推荐）

前提：你的域名已经托管在 Cloudflare（例如你拥有 `example.com`）。

1. 安装并登录 Cloudflare Tunnel：

```bash
brew install cloudflared
cloudflared tunnel login
```

2. 一键创建固定域名映射（示例域名：`app.example.com`）：

```bash
./scripts/cloudflare_tunnel_setup.sh app.example.com 8501 investment-app
```

3. 启动应用（终端 A）：

```bash
./scripts/start_streamlit.sh 8501
```

4. 启动隧道（终端 B）：

```bash
./scripts/start_tunnel.sh investment-app
```

这样你的固定地址就是：

```text
https://app.example.com
```
