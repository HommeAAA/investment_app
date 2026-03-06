# Cloud Functions

## core

统一业务云函数，调用方式：

```js
wx.cloud.callFunction({
  name: 'core',
  data: {
    action: 'portfolio.list',
    payload: {}
  }
})
```

已实现 action:

- `auth.login`
- `auth.bindLegacy`
- `portfolio.list`
- `portfolio.add`
- `portfolio.update`
- `portfolio.delete`
- `portfolio.investor.reassign`
- `share.inviteByCode`
- `share.list`
- `share.revoke`
- `log.list`
- `quote.batch`
- `symbol.search`

## quote-sync

定时同步 `investments` 中涉及到的行情至 `price_cache`。
可在云开发定时触发器中配置每分钟执行一次。
