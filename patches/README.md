# 60s Node 图片代理修复

本机部署的 60s 2.54.2 使用 Node fetch 代理早报图片。fetch 已解压上游响应，但原实现继续转发旧 Content-Encoding 和 Content-Length，导致 Python 客户端重复解压或截断 PNG。

`60s-node-image-proxy.patch` 保存了服务端修复：移除失效的编码、长度及传输头，让 HTTP 框架重新生成响应头。服务器路径为 `/bot/services/60s-api/app/src/modules/60s.module.ts`。升级 60s 后应确认上游是否已包含此修复，避免覆盖后复发。

插件同时兼容图片代理错误保留 gzip 标记的情况；实际 gzip 响应仍做限长解压和图片完整性校验。其他接口沿用原有解码方式。
