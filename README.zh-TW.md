<div align="center">

# resilience-kit

**零依賴的 Python 韌性工程工具庫。**

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

[![PyPI](https://img.shields.io/badge/PyPI-1.0.0-blue.svg)](https://pypi.org/project/resilience-kit/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen.svg)](tests/)

</div>

## 🎉 介紹

一次緩慢或失敗的下游呼叫，就足以把整個服務拖垮。**resilience-kit** 為 Python 應用程式提供一組小巧、可組合的韌性構件，讓程式從容面對這種現實——而且不引入任何第三方依賴。

本專案是對令牌桶限流、熔斷器等成熟工具的**產品思路**進行的獨立實作。沒有複製任何原始碼；架構、API 與測試全部從零撰寫，重點放在清晰度、執行緒安全與可確定性的測試上。

設計目標：

- **零依賴**——僅用標準函式庫，適用於資源受限環境、隔離網路與精簡容器。
- **可組合**——每個構件既能單獨使用，也能疊加成完整的韌性管線。
- **執行緒安全**——所有可變狀態均由鎖保護；時鐘可注入，便于確定性測試。
- **型別與文件完備**——附帶 `py.typed`，所有公開符號均有文件字串。

## ✨ 特性

| 構件 | 模組 | 解決的問題 |
|------|------|-----------|
| 🚦 `TokenBucket` | `ratelimit` | 平滑長期速率，同時允許可控突發 |
| 🪟 `SlidingWindow` | `ratelimit` | 任意滾動時間視窗內嚴格限量 |
| ⚡ `CircuitBreaker` | `circuitbreaker` | 依賴故障時快速失敗，並自動探測恢復 |
| 🔁 `Retry` / `retry` | `retry` | 支援指數/固定退避與抖動的重試 |
| 🧱 `Bulkhead` | `bulkhead` | 限制並行量，保護執行緒池與資源池 |

亮點：

- 🔒 令牌桶與滑動視窗限流器均為執行緒安全，基於單調時鐘。
- 🔌 熔斷器實作 `CLOSED → OPEN → HALF_OPEN → CLOSED` 狀態機，支援狀態變更監聽。
- 🎲 退避支援 `full` / `equal` / `none` 三種抖動，避免驚群效應。
- 🧵 基於號誌的艙壁，支援非阻塞與超時取得。
- 🧪 49 個單元測試涵蓋並行、時序、邊界條件與狀態遷移。

## 🚀 快速開始

從原始的碼安裝（PyPI 套件即將發布）：

```bash
git clone https://github.com/gitstq/resilience-kit.git
cd resilience-kit
python3 -m pip install .
```

驗證安裝：

```python
from resilience_kit import TokenBucket, CircuitBreaker, Retry, Bulkhead

limiter = TokenBucket(rate=5, capacity=5)
print(limiter.try_acquire())  # True
```

執行自帶的完整範例：

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

### 🪟 滑動視窗

```python
from resilience_kit import SlidingWindow

window = SlidingWindow(limit=100, window=60)  # 每 60 秒最多 100 次
if window.try_acquire():
    handle_request()
```

### ⚡ 熔斷器

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
    print(f"請在 {exc.retry_after:.1f} 秒後重試")
```

### 🔁 帶退避的重試

```python
from resilience_kit import Retry, exponential_backoff, with_jitter

policy = Retry(
    attempts=4,
    backoff=with_jitter(exponential_backoff(initial=0.1, maximum=5)),
    exceptions=(ConnectionError, TimeoutError),
)

result = policy.call(call_remote)
```

也可作為裝飾器使用：

```python
@Retry(attempts=3, backoff=lambda _: 0)
def flaky():
    ...
```

### 🧱 艙壁

```python
from resilience_kit import Bulkhead, BulkheadFull

pool = Bulkhead(limit=10, max_wait=0.5)

@pool
def heavy_task():
    ...
```

### 🧩 組合完整管線

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

可執行的完整版本請見 [`examples/quickstart.py`](examples/quickstart.py)。

## 💡 設計迭代

本專案遵循明確的「參考思路，而非程式碼」原則：

| 迭代 | 改動 | 原因 |
|------|------|------|
| v1.0.0 | 初始四個構件 | 用零依賴覆蓋最常見的韌性模式 |
| 可注入時鐘 | 增加 `clock=` 參數 | 消除時序測試的不穩定性，支援精確邊界斷言 |
| 抖動策略 | 新增 `full` / `equal` / `none` | 防止分散式用戶端同步重試造成驚群 |
| 半開探測鎖 | 僅允許一個在途探測 | 避免大量探測壓垮正在恢復的依賴 |
| 遙測計數器 | 每個構件提供 `.counters` | 無需指標依賴即可獲得輕量可觀測性 |
| 執行緒安全稽核 | 所有可變狀態加鎖 | 保證並行請求下的正確性 |

明確不做的部分：不做分散式協調（跨行程限流請用 Redis/etcd）；v1.0.0 不提供專門的非同步版本（目前構件為阻塞式，可在工作執行緒中安全呼叫）。

## 📦 打包部署

```bash
# 執行測試套件
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 建造 sdist 與 wheel
./build.sh
```

產物位於 `dist/`：

```
resilience_kit-1.0.0-py3-none-any.whl
resilience_kit-1.0.0.tar.gz
```

校驗完整性：

```bash
cd dist && sha256sum *
```

作為**函式庫**，本專案刻意不發布二進位 Release。整合方式是將 wheel/sdist 加入依賴鎖定檔，或直接安裝：

```bash
python3 -m pip install ./dist/resilience_kit-1.0.0-py3-none-any.whl
```

## 🤝 貢獻

歡迎貢獻。提交 Pull Request 前請閱讀 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 🐛 回報 Bug 時請附最小重現程式碼。
- ✨ 新增構件請說明使用情境並搭配測試。
- ✅ 保持測試全綠：所有測試必須通過，新行為需新增測試。
- 📝 遵循慣例式提交（`feat:`、`fix:`、`docs:`、`refactor:`、`test:`）。

## 📄 授權

基於 [MIT 授權](LICENSE) 發布，可用於個人與商業專案。
