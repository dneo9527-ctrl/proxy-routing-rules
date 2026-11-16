# VPS 自动发布组件

`run-sync.py` 是由 1Panel 可见计划任务调用的固定入口。它在锁内：

1. 查询公开 `release` 分支；
2. 通过固定摘要的官方 `kubernetes/git-sync` v4.8.0 容器，以非 root UID 下载固定 SHA；
3. 调用独立安装的 `publisher.py`。

`publisher.py` 只读取四个 `.list`、`manifest.json` 和 CI 生成的
`publication.json`。它不导入或运行 checkout 中的 Python/JavaScript，查询 GitHub
Actions API 确认来源提交的 CI 已成功，然后在同一文件系统内用目录交换切换规则目录。
切换后访问四个公开 URL；任何失败都恢复上一版本。规则目录保持原路径，避免修改
OpenResty 配置和终端订阅 URL。

这些文件必须作为经过审查的固定版本安装到 `/opt/1panel/tools/routing-rules-sync/`，
不能让计划任务直接执行 GitHub checkout 中的文件。计划任务不应以下载仓库内容为脚本，
不应配置面板密码或 SSH 私钥。

当前发布镜像：

```text
registry.k8s.io/git-sync/git-sync:v4.8.0
sha256:a20644562fba94773e594885cb001aadb5a3172175f13ac1215e5b2033c9200e
```

`publisher.py` 使用 Linux `renameat2(RENAME_EXCHANGE)` 或 macOS 对应实现做同卷目录交换；
VPS 运行时必须验证该原语、容器挂载和 OpenResty 读取结果。客户端四份规则请求仍是
独立 HTTP 请求，因此没有跨文件、跨设备的事务一致性。
