# Jammers Simulator：逆向分析与授权测试记录

本仓库记录 `jammers-simulator.exe` 的静态分析、动态观察、自动化辅助工具，以及在隔离靶机上的可复现实验流程。仅用于自有或明确获授权的环境。

## 安全与授权声明

仅在自己拥有或明确获授权的 Windows 虚拟机中运行样本。建议使用快照、非管理员账户、断网或专用模拟网络；不要暴露真实凭据、生产数据或宿主机共享目录。提交前清理日志、数据库和个人信息。

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

## 自动化工具用法

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-test.ps1 -CaseName baseline
```

`prepare-test.ps1` 只创建记录目录和环境清单，不会启动样本或连接外部网络。测试前请阅读 [`docs/lab-test-plan.md`](docs/lab-test-plan.md)。

## 在靶机上测试

使用一次性 Windows VM、可回滚快照和非管理员账户；默认断网，仅在需要时连接本地模拟网络。记录样本哈希、快照、参数、时间、进程/文件/注册表/网络证据和清理结果。结束后恢复快照并确认宿主机无新增持久化项。

## License

文档与脚本采用 MIT License。样本版权和使用权归其原权利人所有，仓库不授予额外许可。
