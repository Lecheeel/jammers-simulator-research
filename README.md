# Jammers Simulator Automation Lab

面向 `jammers-simulator.exe` 的自动化分析与授权测试工具集。项目重点是把“样本校验 → 测试准备 → 证据归档 → 逆向记录”整理成可重复的工作流，帮助研究人员在隔离 Windows 靶机上快速建立一致的实验记录。

## 安全与授权声明

仅在自己拥有或明确获授权的 Windows 虚拟机中运行样本。建议使用快照、非管理员账户、断网或专用模拟网络；不要暴露真实凭据、生产数据或宿主机共享目录。提交前清理日志、数据库和个人信息。

## 自动化工具

当前提供两个 PowerShell 工具：

- `scripts/verify-sample.ps1`：计算并核对样本 SHA-256，防止分析过程中误用不同版本。
- `scripts/prepare-test.ps1`：创建按案例区分的 `artifacts/<案例名>/` 目录，并保存 Windows 版本、系统构建号和测试开始时间。该脚本不会启动样本、修改系统配置或访问外部网络。

### 快速开始

在 PowerShell 中执行：

```powershell
cd D:\benchmark_b\jammers-simulator-research

# 1. 校验样本
powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1

# 2. 为一次测试创建独立记录目录
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-test.ps1 -CaseName baseline
```

也可以指定待校验文件：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1 -SamplePath .\sample\jammers-simulator.exe
```

执行后会生成：

```text
artifacts/baseline/environment.txt   # 靶机系统信息
artifacts/baseline/started-at.txt   # 测试开始时间
```

研究人员可以把进程监控、Procmon、网络捕获和反编译器导出的证据放入对应案例目录。`artifacts/`、抓包、转储、日志和 SQLite 状态文件默认被 `.gitignore` 排除，避免把本地敏感数据推入公开仓库。

### 推荐自动化流程

```text
verify-sample.ps1
        ↓
prepare-test.ps1 -CaseName <name>
        ↓
在隔离 VM 中执行最小测试
        ↓
归档进程 / 文件 / 注册表 / 网络证据
        ↓
恢复快照并人工复核
```

## 仓库结构

```text
sample/       样本及校验信息
docs/         逆向笔记、测试方案
scripts/      自动化辅助脚本
```

## 样本信息

- 文件：`sample/jammers-simulator.exe`
- SHA-256：`2373B9E7AF83735A04309E2983EB433EC46FAF7E0B8494410CE7FDED2A297C27`
- 类型：Windows PE 可执行文件

运行 `powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1` 可重新校验。发布大文件建议使用 Git LFS；若样本不能公开，请只提交哈希和获取方式。

## 我们如何逆向

采用“静态 → 受控动态 → 交叉验证”：固定哈希并记录工具/VM；使用 PE、字符串、导入表和反编译器建立画像；在隔离靶机观察进程、文件、注册表、网络和退出码；将动态证据与静态交叉引用对应。详细模板见 [`docs/reverse-notes.md`](docs/reverse-notes.md)。

测试前请阅读 [`docs/lab-test-plan.md`](docs/lab-test-plan.md)。

## 在靶机上测试

使用一次性 Windows VM、可回滚快照和非管理员账户；默认断网，仅在需要时连接本地模拟网络。记录样本哈希、快照、参数、时间、进程/文件/注册表/网络证据和清理结果。结束后恢复快照并确认宿主机无新增持久化项。

## License

文档与脚本采用 MIT License。样本版权和使用权归其原权利人所有，仓库不授予额外许可。
