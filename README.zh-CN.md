<div align="center">

# resilience-kit

**零依赖的 Python 韧性工程工具库。**

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

[![PyPI](https://img.shields.io/badge/PyPI-1.0.0-blue.svg)](https://pypi.org/project/resilience-kit/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen.svg)](tests/)

</div>

## 🎉 介绍

一次缓慢或失败的下游调用，就足以把整个服务拖垮。**resilience-kit** 为 Python 应用提供一组小巧、可组合的韧性构件，让程序从容面对这种现实——而且不引入任何第三方依赖。

本项目是对令牌桶限流、熔断器等成熟工具的**产品思路**进行的独立实现。没有复制任何源代码；架构、API 与测试全部从零编写，重点放在清晰性、线程安全和可确定性的测试上。

设计目标：

- **零依赖**——仅用标准库，适用于资源受限环境、隔离网络和精简容器。
- **可组合**——每个构件既能单独使用，也能叠加成一条完整的韧性管线。
- **线程安全**——所有可变状态均由锁保护；时钟可注入，便于确定性测试。
- **类型与文档完备**——附带 `py.typed`，所有公开符号均有文档字符串。

## ✨ 特性

| 构件 | 模块 | 解决的问题 |
|------|------|-----------|
| 🚦 `TokenBucket` | `ratelimit` | 平滑长期速率，同时允许可控突发 |
| 🪟 `SlidingWindow` | `ratelimit` | 任意滚动时间窗口内严格限量 |
| ⚡ `CircuitBreaker` | `circuitbreaker` | 依赖故障时快速失败，并自动探测恢复 |
| 🔁 `Retry` / `retry` | `retry` | 支持指数/固定退避与抖动的重试 |
| 🧱 `Bulkhead` | `bulkhead` | 限制并发量，保护线程池与资源池 |

亮点：

- 🔒 令牌桶与滑动窗口限流器均线程安全，基于单调时钟。
- 🔌 熔断器实现 `CLOSED → OPEN → HALF_OPEN → CLOSED` 状态机，支持状态变更监听。
- 🎲 退避支持 `full` / `equal` / `none` 三种抖动，避免惊群效应。
- 🧵 基于信号量的舱壁，支持非阻塞与超时获取。
- 🧪 49 个单元测试覆盖并发、时序、边界条件与状态迁移。

## 🚀 快速开始

从源码安装（PyPI 包即将发布）：

```bash
git clone https://github.com/gitstq/resilience-kit.git
cd resilience-kit
python3 -m pip install .
```

验证安装：

```python
from resilience_kit import TokenBucket, CircuitBreaker, Retry, Bulkhead

limiter = TokenBucket(rate=5, capacity=5)
print(limiter.try_acquire())  # True
```

运行自带的完整示例：

```bash
PYTHONPATH=src python3 examples/quickstart.py
```

## 📖 使用指南

### 🚦 令牌桶

```python
from resilience_kit import TokenBucket, RateLimitExceeded

bucket = TokenBucket(rate=2, capacity=4)

if bucket.try_acquire():
    handle_request()          # 非阻塞
else:
    raise RateLimitExceeded()

bucket.acquire(timeout=1.0)   # 阻塞版本，最多等待 1 秒
```

### 🪟 滑动窗口

```python
from resilience_kit import SlidingWindow

window = SlidingWindow(limit=100, window=60)  # 每 60 秒最多 100 次
if window.try_acquire():
    handle_request()
```

### ⚡ 熔断器

```python
from resilience_kit import CircuitBreaker, CircuitOpenError

breaker = CircuitBreaker(failure_threshold=3, reset_timeout=30)
breaker.add_listener(lambda old, new: print(f"{old.value} -> {new.value}"))

@breaker
def call_remote():
    return remote_api()

try:
    call_remote()
except CircuitOpenError as exc:
    print(f"请在 {exc.retry_after:.1f} 秒后重试")
```

### 🔁 带退避的重试

```python
from resilience_kit import Retry, exponential_backoff, with_jitter

policy = Retry(
    attempts=4,
    backoff=with_jitter(exponential_backoff(initial=0.1, maximum=5)),
    exceptions=(ConnectionError, TimeoutError),
)

result = policy.call(call_remote)
```

也可作为装饰器使用：

```python
@Retry(attempts=3, backoff=lambda _: 0)
def flaky():
    ...
```

### 🧱 舱壁

```python
from resilience_kit import Bulkhead, BulkheadFull

pool = Bulkhead(limit=10, max_wait=0.5)

@pool
def heavy_task():
    ...
```

### 🧩 组合完整管线

```python
from resilience_kit import (
    TokenBucket, CircuitBreaker, Retry, Bulkhead,
    exponential_backoff, with_jitter,
)

bucket  = TokenBucket(rate=50, capacity=50)
breaker = CircuitBreaker(failure_threshold=5, reset_timeout=10)
retry   = Retry(attempts=3, backoff=with_jitter(exponential_backoff()))
pool    = Bulkhead(limit=20)

def guarded(*args, **kwargs):
    bucket.acquire(timeout=1)
    return pool.call(lambda: retry.call(lambda: breaker.call(call_remote, *args, **kwargs)))
```

可运行的完整版本见 [`examples/quickstart.py`](examples/quickstart.py)。

## 💡 设计迭代

本项目遵循明确的「参考思路，而非代码」原则：

| 迭代 | 改动 | 原因 |
|------|------|------|
| v1.0.0 | 初始四个构件 | 用零依赖覆盖最常见的韧性模式 |
| 可注入时钟 | 增加 `clock=` 参数 | 消除时序测试的不稳定性，支持精确边界断言 |
| 抖动策略 | 新增 `full` / `equal` / `none` | 防止分布式客户端同步重试造成惊群 |
| 半开探测锁 | 仅允许一个在途探测 | 避免大量探测压垮正在恢复的依赖 |
| 遥测计数器 | 每个构件提供 `.counters` | 无需指标依赖即可获得轻量可观测性 |
| 线程安全审计 | 所有可变状态加锁 | 保证并发请求下的正确性 |

明确的不做清单：不做分布式协调（跨进程限流请用 Redis/etcd）；v1.0.0 不提供专门的异步版本（当前构件为阻塞式，可在工作线程中安全调用）。

## 📦 打包部署

```bash
# 运行测试套件
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 构建 sdist 与 wheel
./build.sh
```

产物位于 `dist/`：

```
resilience_kit-1.0.0-py3-none-any.whl
resilience_kit-1.0.0.tar.gz
```

校验完整性：

```bash
cd dist && sha256sum *
```

作为**库**，本项目有意不发布二进制 Release。集成方式是将 wheel/sdist 加入依赖锁文件，或直接安装：

```bash
python3 -m pip install ./dist/resilience_kit-1.0.0-py3-none-any.whl
```

## 🤝 贡献

欢迎贡献。提交 Pull Request 前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 🐛 报告 Bug 时请附最小复现代码。
- ✨ 新增构件请说明使用场景并配套测试。
- ✅ 保持测试全绿：所有测试必须通过，新行为需新增测试。
- 📝 遵循约定式提交（`feat:`、`fix:`、`docs:`、`refactor:`、`test:`）。

## 📄 协议

基于 [MIT 协议](LICENSE) 发布，可用于个人与商业项目。
