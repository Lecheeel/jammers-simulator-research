# 靶机测试方案

本方案只适用于自己拥有或明确获授权的一次性 Windows 虚拟机。默认离线；
如果必须联网，只连接本地模拟服务或明确列入授权范围的实验网段。

## 测试前

1. 创建 VM 快照，关闭共享剪贴板、共享目录、凭据同步和宿主机映射盘。
2. 使用非管理员账户，准备 Procmon/进程树/文件与注册表监控；不要使用真实账号、
   token、生产 URL 或生产数据库。
3. 将样本放入 VM 后，把仓库复制到 VM，先校验 SHA-256。
4. 为本次测试创建独立 artifacts 目录：

```powershell
cd C:\path\to\jammers-simulator-research
powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-test.ps1 -CaseName baseline
```

## 推荐的自动化回归（不启动 EXE）

这是发布工具的首选入口，用来验证我们重建的协议/仿真逻辑：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-automation-smoke.ps1 -CaseName baseline
```

它会校验样本、保存环境信息、生成确定性场景 JSON，并将结果写到
`artifacts/baseline/`。若安装了 pytest，可运行：

```powershell
python -m pytest -q
```

## 在靶机上测试 EXE

只有在快照和监控准备好后才执行：

```powershell
Start-Process -FilePath .\sample\jammers-simulator.exe -WorkingDirectory (Get-Location)
```

记录启动参数、PID、退出码、子进程、写入文件、注册表键、监听/连接的地址和时间。
先做 GUI 空操作，再按最小流程进入练习/正式测试页面；任何需要账号、上传或外部
机器人服务的步骤都使用本地假服务或停止并记录为“未测试”。不要为了让流程通过而
修改系统安全设置、绕过访问控制或连接第三方网络。

## 测试后

停止监控并保存脱敏日志和截图，检查是否出现自启动、计划任务、服务、启动项或新建
凭据；恢复 VM 快照。`artifacts/`、日志、转储、抓包和 SQLite 文件默认不提交仓库。
