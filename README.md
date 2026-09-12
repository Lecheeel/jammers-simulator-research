# Jammers Simulator 逆向成果与自动化工具

本仓库发布我们对 `jammers-simulator.exe` 的离线逆向结论，以及用于复现、回归和靶机测试准备的 Python/PowerShell 自动化工具。重点是“可重复测试”：固定样本哈希、自动生成场景、用虚拟时间运行仿真、通过本地 HTTP 四命令服务回归协议，并保存每次测试的环境与输出。

> 仅在自己拥有或明确获授权的 Windows VM/靶机中使用。默认断网；不要连接生产系统、使用真实凭据或把日志、转储、抓包和 SQLite 数据提交到仓库。

## 快速开始

```powershell
git clone https://github.com/Lecheeel/jammers-simulator-research.git
cd jammers-simulator-research
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\\scripts\\run-automation-smoke.ps1 -CaseName baseline
python -m pytest -q
```

没有 `pytest` 时仍可直接使用核心 CLI：

```powershell
python .\\automation\\jammers_simulator.py --seed 1234 --count 4 --out .\\artifacts\\scenario.json
```

## 自动化工具（重点）

### 一键 smoke

`scripts/run-automation-smoke.ps1` 依次执行样本校验、测试目录准备和确定性场景生成：

```powershell
powershell -ExecutionPolicy Bypass -File .\\scripts\\run-automation-smoke.ps1 -Seed 1234 -CaseName baseline
```

输出位于 `artifacts/baseline/`：`environment.txt`、`started-at.txt` 和 `scenario.json`。

### Python 仿真器

`automation/jammers_simulator.py` 是从 Go 状态机和前端协议重建的本地兼容层，不依赖网络，也不需要启动原始 EXE。

```python
from jammers_simulator import SimulationRules, Session, generate_practice

scenario = generate_practice(seed=1234, count=12)
session = Session(scenario, SimulationRules.fast_test())
print(session.enter())
print(session.measure(0.0, 0.0, channel=1))
print(session.summary())
```

已覆盖 seed 稳定生成、全向圆盘、定向扇区、角度归一化/量化、虚拟时间限制、移动/测量/清除/退出、换信道、失败原因和 snapshot/restore；规则可覆写，适合 CI 与批量测试。

### 本地 HTTP 四命令服务

`automation/simulator_http.py` 提供 loopback 服务：`/enter`、`/measure`、`/clear`、`/exit`。默认只绑定 `127.0.0.1`，支持请求校验、重复 JSON 键拒绝、请求 ID 幂等和冲突检测。

```python
from jammers_simulator import SimulationRules, generate_practice
from simulator_http import serve

server = serve(generate_practice(1234), host="127.0.0.1", port=2026,
               rules=SimulationRules.fast_test())
server.serve_forever()
```

客户端请求示例：

```powershell
$body = @{ arena_id='default'; robot_id='local'; request_id='e1' } | ConvertTo-Json -Compress
Invoke-RestMethod http://127.0.0.1:2026/enter -Method Post -ContentType 'application/json; charset=utf-8' -Body $body
```

### 加密测试信封与 GPU 预筛选

`automation/jammers_crypto.py` 用临时密钥离线验证 gzip、分块 AES-256-GCM、RSA-OAEP-SHA256、HKDF、SHA-256 和 Ed25519 组合；它不是官方服务器上传格式。`automation/gpu_monte_carlo.py` 提供 NumPy 参考和可选 CuPy/CUDA 后端，用于覆盖率策略预筛选，最终协议行为仍由仿真器与 HTTP 回归确认。

## 我们如何逆向

```text
固定 SHA-256 → PE/架构/导入表/字符串分诊 → Go 元数据与符号恢复
→ 提取 Wails/WebView2 HTML/JS → 定位 scenario/bearingnoise/simcore/testsession
→ Python 重建状态机与几何逻辑 → 本地回归 + HTTP 协议交叉验证
```

样本为 PE32+ x86-64、Go 1.27.1、Wails v3 beta/WebView2，前端为 Vue/Vite。关键锚点包括 `scenario.GeneratePractice`、`DefaultGenerationRules`、`bearingnoise`、`simcore.directionalCoverage`、`insideJammerDisk` 和 `counterSource`。详见 [`docs/reverse-notes.md`](docs/reverse-notes.md)、[`analysis/reverse-report.md`](analysis/reverse-report.md) 与 [`analysis/evidence/`](analysis/evidence/)。

## 在授权靶机上测试原始 EXE

先阅读 [`docs/lab-test-plan.md`](docs/lab-test-plan.md)：一次性 Windows VM + 可回滚快照，关闭共享目录/剪贴板/凭据同步；使用非管理员账户和 Procmon/进程树/文件/注册表监控；先执行 `verify-sample.ps1`、`prepare-test.ps1`，再在监控就绪后启动 `sample/jammers-simulator.exe`。记录 PID、子进程、文件、注册表、网络、退出码和时间。账号、上传或机器人服务只使用本地假服务；结束后脱敏、检查持久化项并恢复快照。

## 目录结构

```text
sample/                 固定哈希的样本
automation/             发布的 Python 自动化工具
tests/                  仿真器与 HTTP 协议回归
scripts/                样本校验、测试准备、一键 smoke
analysis/evidence/      逆向证据摘要和样例输出
analysis/embedded/      从 PE 提取的 Wails/WebView2 资源
docs/                   逆向笔记与靶机测试方案
```

## 已知边界与许可

Python 实现是高保真兼容层，不宣称字节级等价或官方服务器可接受。官方认证、签名练习票据、SQLite 上传队列、正式行为日志加密格式、外部机器人传输和未恢复的精确参数仍需在有授权的真实集成环境中验证。

文档、Python 工具和 PowerShell 脚本采用 MIT License。样本版权和使用权归原权利人，本仓库不授予额外许可。
