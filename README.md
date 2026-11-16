# 我的多端分流规则

GitHub 主仓库保存个人规则，现有 VPS 提供发布副本。日常把「网站 + 直连 / 代理 / 住宅 / 拒绝」发给 Codex，由 Codex 修改、检查、提交，再发布和验证。

这是公开域名规则仓库，不包含节点、账户、订阅地址或认证资料。它不是可直接替换全部客户端配置的节点订阅。

## 四类个人规则

| 源文件 | 用途 | 当前策略映射 |
| --- | --- | --- |
| [direct.list](rules/direct.list) | 强制直连，包括 `key.qudad.icu` | DIRECT |
| [proxy.list](rules/proxy.list) | 强制默认代理 | PROXY |
| [residential.list](rules/residential.list) | Claude 等住宅出口 | Claude / 住宅组 |
| [reject.list](rules/reject.list) | 拒绝连接 | REJECT |

每行仅使用 `DOMAIN,example.com` 或 `DOMAIN-SUFFIX,example.com`，不附加策略名称。前者只匹配精确域名，后者包含该域名及其子域名。空规则组保留 `.invalid` 占位。

客户端中保留管理入口、DNS、局域网规则的优先级，再按 **拒绝 → 直连 → 住宅 → 代理** 引用这四份规则，之后才是大范围基础规则。住宅组必须有住宅节点且以 REJECT 兜底，不能自动回落到 DIRECT。全局代理模式会绕过规则，请在规则模式下使用。

## 引用地址

GitHub Raw 的基本路径：

```text
https://raw.githubusercontent.com/dneo9527-ctrl/proxy-routing-rules/main/rules/
```

在路径后添加 `direct.list`、`proxy.list`、`residential.list` 或 `reject.list`。客户端应引用 Raw 原始文件地址，不能引用 GitHub 的 `/blob/` 网页地址。

现有设备继续使用已配置的 VPS 发布地址，无需重新导入：

```text
https://x.dvp.us.ci:2053/routing/direct.list
https://x.dvp.us.ci:2053/routing/proxy.list
https://x.dvp.us.ci:2053/routing/residential.list
https://x.dvp.us.ci:2053/routing/reject.list
```

| 客户端 | 本仓库产物 | 当前验收范围 |
| --- | --- | --- |
| Clash Verge / Mihomo | `rules/*.list`，classical + text | 现有 Mac 已接入 VPS 并实测自动更新 |
| Surge | `rules/*.list`，RULE-SET | 配置已接入；手机后台自动更新未独立实测 |
| Quantumult X | `dist/quantumult-x/*.list`，HOST / HOST-SUFFIX | 已生成格式及引用示例，尚未真机接入 |
| Shadowrocket | 可使用兼容域名规则，按应用规则集入口配置 | 尚未真机接入，不算已完成同步 |
| v2rayNG 等其他客户端 | 需要其自身支持的路由配置或转换 | 不保证能直接引用这些列表 |

参考片段见 [examples](examples/)。这些片段需要已有的代理策略组，不包含节点，也不是完整配置。新设备引用 GitHub Raw 前应确认该设备能访问它；现有 VPS 地址减少了对 GitHub 下载路径的依赖。设置的 300 秒是检查间隔，网络、缓存及 iOS 运行状态会影响实际送达时间，不承诺即时推送。

## 成熟基础规则

- 已 Fork 保存到自己的账号：[dneo9527-ctrl/ios_rule_script](https://github.com/dneo9527-ctrl/ios_rule_script)。上游为 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)，提供 Clash、Surge、QX 等分类规则，保留原项目 GPL-2.0 许可证及来源声明。现有客户端基础规则仍引用原上游，本次没有批量替换。
- 当前配置还参考 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 的域名资源，上游许可证为 GPL-3.0；本仓库没有复制它的全量数据。

个人覆盖规则与成熟规则库分开维护，避免更新基础库时覆盖个人选择。Fork 是保存的副本，不会自动跟随上游；需要时由 Codex 比较并同步上游，不能把「已 Fork」当作「始终最新」。本次只复用分流规则，不启用上游重写或脚本功能。

## 修改与发布

直接编辑 `rules/`，或者运行：

```sh
python3 scripts/rules.py set direct https://key.qudad.icu/dashboard
python3 scripts/rules.py set proxy example.com --suffix
python3 scripts/rules.py build
python3 scripts/rules.py check
python3 -m unittest discover -s tests -v
```

校验会拒绝策略后缀、无效域名、重复规则及跨类别的父子域名重叠。QX 文件与 `manifest.json` 自动生成，不直接手改。

发布顺序：检查 → 提交并推送 GitHub → Actions 校验 main 并生成 `release` 分支 → VPS 的 1Panel 可见计划任务拉取固定发布分支 → 固定发布器校验 CI provenance、manifest、域名语法和跨列表冲突 → 在原目录完成同文件系统目录级切换 → 回读四个公开 URL 及 SHA-256 → 终端按自己的间隔刷新。发布器保留上一有效版本，下载、校验或 HTTP 回读失败会恢复旧版。

自动发布使用官方 [kubernetes/git-sync](https://github.com/kubernetes/git-sync) v4.8.0 镜像，镜像按摘要固定。它只负责把 Git 数据拉到隔离暂存区；VPS 不执行下载仓库中的脚本。1Panel 计划任务运行固定的 `deploy/run-sync.py`，规则校验和发布器是单独安装的受信代码。GitHub 不保存面板密码、SSH 私钥或订阅令牌，也不新增公网入口。

修改 main 后，Actions 变绿才会产生 `release`；VPS 下一次计划任务才会拉取。终端继续使用现有 VPS 地址，无需重新导入，但各终端的后台刷新时间不同，四个文件和所有设备不会同时切换。若要手动回滚，1Panel 任务保留的上一版本可恢复。私有节点订阅保持关闭。

私有节点订阅保持关闭。修改规则不需要打开它；新增节点、DNS 或策略组结构仍需要单独更新完整客户端配置。

## 参考资料

- [Mihomo rule-provider](https://wiki.metacubex.one/config/rule-providers/)
- [Surge RULE-SET](https://manual.nssurge.com/rules/ruleset.html)
- [Quantumult X 官方示例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)
- [GitHub Raw 文件说明](https://docs.github.com/en/repositories/working-with-files/using-files/viewing-and-understanding-files)

本仓库原创工具和个人规则使用 MIT 许可证；上游项目保持各自许可证。
