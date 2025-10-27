---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    font-size: 28px;
  }
  h1 {
    color: #2c3e50;
    font-size: 48px;
  }
  h2 {
    color: #34495e;
    font-size: 40px;
  }
  code {
    background: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
  }
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
  }
---

# FundMate 系统整体架构
## 核心组件技术解析

基金经理技术分享会

---

## 架构概览

FundMate 采用模块化设计，将复杂的券商数据处理流程分解为五个核心组件：

1. **Exchange Rate Handler** - 汇率数据获取与缓存
2. **LLM Handler** - 大模型 API 调用与数据提取
3. **Price Fetcher** - 实时/历史股票价格查询
4. **Prompt Templates** - 针对性提示词管理
5. **Data Persistence** - 数据持久化与查询

---

## 1. Exchange Rate Handler
### 双层缓存架构的汇率管理器

**技术特性**

- **双层缓存设计**：内存缓存 + JSON 文件缓存
- **按需加载**：Lazy loading 机制，仅在需要时获取汇率
- **动态货币支持**：自动检测所需货币对，避免冗余 API 调用

---

## Exchange Rate Handler - 实现细节

<div class="columns">

<div>

**核心方法**

```python
# 单一汇率查询（带缓存）
get_single_rate(from, to, date)

# 动态批量查询
get_rates_dynamic(currencies_needed)

# 懒加载查询
get_rate_lazy(from_currency, to_currency)
```

</div>

<div>

**缓存策略**

1. **内存缓存** - 运行时快速访问
   - 字典结构：`{(from, to, date): rate}`

2. **JSON 文件缓存** - 持久化存储
   - 路径：`./out/exchange_rates_cache.json`
   - 格式：`{"USD_CNY_2025-02-28": 7.19}`

3. **API 调用限流** - 0.6秒延迟避免 429 错误

</div>

</div>

---

## Exchange Rate Handler - 使用场景

**场景 1：多券商组合跨币种转换**

```python
# 自动检测所有券商持仓中的货币类型
currencies_needed = ['HKD', 'CNY', 'EUR']
rates = exchange_handler.get_rates_dynamic(currencies_needed, 'USD', date)
# 结果: {'HKD': 0.128, 'CNY': 0.139, 'EUR': 1.08, 'USD': 1.0}
```

**场景 2：单笔持仓即时转换**

```python
# 懒加载：只在需要时查询汇率
rate = exchange_handler.get_rate_lazy('HKD', 'USD', date)
usd_value = hkd_amount * rate
```

---

## 2. LLM Handler
### Google Gemini API 数据提取引擎

**技术架构**

- **模型**：Gemini 2.5 Pro（多模态支持）
- **输入格式**：支持 PDF 和图片（PNG/JPG）直接处理
- **Temperature**: 0（确定性提取）
- **最大 Tokens**: 8192

---

## LLM Handler - 核心流程

```
┌─────────────┐
│  PDF/Image  │
│   Broker    │
│  Statement  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  System Prompt + Broker Prompt      │  ← 精确度要求 + 券商特定规则
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Base64 Encoding + API Call         │  ← 5次重试机制
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  JSON Response Parsing              │  ← 支持纯 JSON / Markdown 包裹
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  {"Cash": {...}, "Positions": [...]}│
└─────────────────────────────────────┘
```

---

## LLM Handler - 关键技术细节

<div class="columns">

<div>

**System Prompt 设计要点**

- 绝对精度要求：股票代码必须完全一致
- 数据完整性：提取所有可见现金和持仓
- 格式合规：严格 JSON 结构

**输出格式**

```json
{
  "Cash": {
    "CNY": 123.4,
    "HKD": 456.7,
    "USD": 789.0
  },
  "Positions": [
    {
      "StockCode": "AAPL",
      "Holding": 750000,
      "Price": 150.50,
      "Multiplier": 1
    }
  ]
}
```

</div>

<div>

**重试与容错**

```python
max_retries = 5
for attempt in range(max_retries):
    try:
        response = requests.post(...)
        if response.status_code == 200:
            break
        # 失败自动重试
    except Exception as e:
        if attempt < max_retries - 1:
            logger.warning(f"Retry {attempt+1}")
            continue
        else:
            raise
```

**多格式解析**

1. 优先尝试直接 JSON 解析
2. 失败则提取 Markdown 代码块
3. 正则匹配：`` `json {...} ` ``

</div>

</div>

---

## 3. Price Fetcher
### 双源价格查询系统

**架构设计**

- **主数据源**：Futu OpenD API（实时行情）
- **备用数据源**：akshare 库（历史数据）
- **优先级策略**：API 价格 > 券商提供价格 > 失败回退

---

## Price Fetcher - 数据流

```
                    ┌──────────────────┐
                    │  Price Request   │
                    │  (symbol, date)  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Symbol Normalize │  ← 清洗券商符号格式
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
            ┌───────┤  Option Detection?│
            │       └────────┬─────────┘
            │                │
         YES│                │NO
            │                │
            ▼                ▼
┌─────────────────┐   ┌──────────────────┐
│ Option Helpers  │   │  get_price_futu  │ ← Primary Source
│ - US Format     │   └────────┬─────────┘
│ - HK Format     │            │
│ - Morgan Format │            ▼
└─────────────────┘   ┌──────────────────┐
                      │ get_price_akshare│ ← Fallback Source
                      └────────┬─────────┘
                               │
                               ▼
                      ┌──────────────────┐
                      │  Return Price    │
                      └──────────────────┘
```

---

## Price Fetcher - 期权处理策略

**三种期权格式识别**

<div class="columns">

<div>

**1. 美股期权（OCC 格式）**

```
AMZN US 06/18/26 C300
IB格式: AMZN 18JUN26 300 C
```

使用 `us_option_price_helper.py` 处理

**2. 港股期权（HKATS 格式）**

```
CLI 250929 19.00 CALL
```

正则检测：`[A-Z]{3}\s+\d{6}`

</div>

<div>

**3. Morgan 格式（OTC 期权）**

```
CALL OTC-1810 1.0@28.0439
EXP 08/26/2026 XIAOMI-W
```

解析流程：
1. 提取 OTC 代码 → `OTC-1810`
2. 映射到 Futu 标的 → `HK.01810`
3. 提取行权价 → `28.0439`
4. 查询最接近合约

</div>

</div>

---

## Price Fetcher - Futu API 技术细节

**连接与订阅**

```python
quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

# 订阅 K 线数据
ret, msg = quote_ctx.subscribe([symbol], [ft.SubType.K_DAY])

# 获取历史数据（300天）
ret, data = quote_ctx.get_cur_kline(symbol, num=300, ktype=ft.KLType.K_DAY)
```

**日期匹配策略**

1. **精确匹配**：查找 `time_key` 包含目标日期的记录
2. **回退策略**：找不到精确日期时使用券商价格
3. **资源释放**：确保 `quote_ctx.close()` 执行

---

## Price Fetcher - 期权倍数逻辑

**Multiplier 优先级设计**

```python
def get_option_multiplier(symbol, description, broker_multiplier):
    # 优先级 1: 券商提供的明确倍数
    if broker_multiplier and broker_multiplier > 1:
        return broker_multiplier

    # 优先级 2: OTC 期权特殊处理
    if 'OTC' in description.upper():
        return 1  # OTC 期权不需要倍数

    # 优先级 3: 标准期权合约
    if is_option_contract(symbol, description):
        return 100  # 标准美股/港股期权

    return 1  # 普通股票
```

---

## 4. Prompt Templates
### 券商特定提取规则库

**设计理念**

每家券商的账单格式完全不同，需要针对性的提取指令：

- **CICC**：`Ledger Balance` + `Securities Holding for`
- **IB**：`Ending Cash` vs `Starting Cash` 区分
- **MOOMOO**：同时处理 `Securities` 和 `Funds` 两张表
- **TIGER**：支持 `Multiplier` 字段提取

---

## Prompt Templates - 实际示例

**盈透证券（IB）复杂提取规则**

```python
"IB": [{"type": "text", "text": """
In the 'Cash Report' section, which may span multiple pages:
  1. Find the block under 'HKD' header → 'Ending Cash' row → 'Total' column
  2. Find the block under 'USD' header → 'Ending Cash' row → 'Total' column
  3. DO NOT confuse 'Ending Cash' with 'Starting Cash' or 'Ending Settled Cash'
  Set 'CNY', 'Total', 'Total_type' to None.

Then, from 'Open Positions' section, for each position:
  - Extract 'Symbol', 'Quantity', 'Mult' (as 'Multiplier'), 'Close Price'
  - Currency determined by header row above the position group
"""}]
```

---

## Prompt Templates - 数据质量控制

**关键指令设计**

1. **精确度保证**
   ```
   "股票代码必须与文档完全一致 - 仔细区分 6 vs 8, 0 vs O"
   ```

2. **字段映射清晰**
   ```
   "'Sellable Quantity' → 'Holding'"
   "'Closing Price' → 'Price'"
   ```

3. **分页处理**
   ```
   "Consider table pagination"
   ```

4. **货币识别**
   ```
   "Currency indicated in category header: '(HKD)'"
   ```

---

## 5. Data Persistence
### Parquet + CSV 双格式存储

**存储架构**

```
./out/result/
└── 2025-02-28/
    ├── cash_summary_2025-02-28.parquet      ← 现金汇总（Snappy压缩）
    ├── positions_2025-02-28.parquet         ← 持仓明细（Snappy压缩）
    ├── portfolio_details_2025-02-28.csv     ← 人类可读报告
    └── metadata_2025-02-28.json             ← 处理元数据
```

**技术选型**

- **Parquet**：高效列式存储，适合大数据分析
- **CSV**：通用格式，Excel/Pandas 直接读取
- **JSON**：元数据记录，包含汇率和处理时间戳

---

## Data Persistence - 现金数据结构

**Cash Summary Schema**

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | string | 数据日期 (YYYY-MM-DD) |
| `broker_name` | string | 券商名称 (IB, MOOMOO, etc.) |
| `account_id` | string | 账户标识 |
| `cny` | float | 人民币现金 |
| `hkd` | float | 港币现金 |
| `usd` | float | 美元现金 |
| `total` | float | 券商提供的总计 |
| `total_type` | string | 总计货币类型 |
| `usd_total` | float | **换算后的美元总额** |
| `timestamp` | string | 处理时间戳 |

---

## Data Persistence - 持仓数据结构

**Positions Schema**

| 字段 | 类型 | 说明 |
|------|------|------|
| `stock_code` | string | 股票代码 |
| `raw_description` | string | 原始描述（用于期权识别）|
| `holding` | int | 持仓数量 |
| `broker_price` | float | 券商提供价格 |
| `broker_price_currency` | string | 券商价格货币 |
| `final_price` | float | **最终使用价格** |
| `final_price_source` | string | 价格来源（API/Broker） |
| `optimized_price_currency` | string | 优化后价格货币 |
| `multiplier` | float | 期权倍数 |
| `position_value_usd` | float | **持仓美元价值** |

---

## Data Persistence - 智能特性

<div class="columns">

<div>

**1. 货币市场基金重分类**

```python
if is_money_market_fund(description):
    # 从持仓移除
    # 计算价值: holding × price
    # 添加到对应货币现金
    cash[currency] += mmf_value
```

示例：
```
"CSOP USD Money Market Fund"
→ 从 Positions 移除
→ 加入 USD 现金
```

</div>

<div>

**2. 跨券商持仓去重**

```python
# 按 stock_code 聚合
position_aggregation = {}
for position in positions:
    key = raw_description if is_option
          else stock_code
    position_aggregation[key] += value

total_positions = sum(
    position_aggregation.values()
)
```

防止同一股票在多个券商重复计算

</div>

</div>

---

## Data Persistence - CSV 报告生成

**Summary Rows 自动追加**

```csv
[SUMMARY],TOTAL_CASH,"Total Cash across 10 brokers",,,,,,,1234567.89
[SUMMARY],TOTAL_POSITIONS,"Total Positions (deduplicated)",,,,,,,987654.32
[SUMMARY],GRAND_TOTAL,"Grand Total (Cash + Positions)",,,,,,,2222222.21
```

**精度控制**

- `position_value_usd` 四舍五入到 2 位小数
- 汇总行金额使用 `round(value, 2)`

---

## Data Persistence - 元数据记录

**metadata.json 示例**

```json
{
  "date": "2025-02-28",
  "timestamp": "2025-02-28T15:30:45.123456",
  "broker_count": 10,
  "total_positions": 127,
  "exchange_rates": {
    "USD": 1.0,
    "HKD": 0.128,
    "CNY": 0.139
  },
  "brokers_processed": ["IB", "MOOMOO", "TIGER", ...],
  "files": {
    "cash_summary": "cash_summary_2025-02-28.parquet",
    "positions": "positions_2025-02-28.parquet",
    "portfolio_csv": "portfolio_details_2025-02-28.csv"
  }
}
```

---

## 跨组件协作示例
### 完整数据流演示

**用户命令**

```bash
python src/main.py ./data/statements --date 2025-02-28 --max-workers 10
```

**执行流程**

1. **Prompt Templates** 加载 IB 券商提取规则
2. **LLM Handler** 处理 PDF → 返回 JSON
3. **Exchange Rate Handler** 懒加载 HKD→USD 汇率
4. **Price Fetcher** 批量查询 127 个股票价格
5. **Data Persistence** 保存 Parquet + CSV + Metadata

---

## 跨组件协作 - 并发优化

**ThreadPoolExecutor 并发策略**

```python
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {
        executor.submit(process_broker, pdf): pdf
        for pdf in pdf_files
    }

    for future in as_completed(futures):
        result = future.result()
        # ✅ [3/10] IB/U12345 processed
```

**Cross-Broker Pricing 优化**

```python
# 聚合所有券商的唯一股票代码
all_symbols = set()
for result in results:
    all_symbols.update([p['StockCode'] for p in result.positions])

# 批量查询一次（而非每个券商重复查）
optimized_prices = batch_query_prices(all_symbols, date)
```

---

## 性能优化技术要点

<div class="columns">

<div>

**1. 缓存层次化**

- L1: 内存字典（毫秒级）
- L2: JSON 文件（秒级）
- L3: API 调用（分钟级）

**2. API 限流**

```python
time.sleep(0.6)  # Exchange Rate
time.sleep(0.2)  # Price Fetcher
```

**3. 连接池管理**

```python
finally:
    if quote_ctx:
        quote_ctx.close()
```

</div>

<div>

**4. 数据压缩**

```python
df.to_parquet(
    file,
    compression='snappy'
)
```

Snappy：高速压缩，适合热数据

**5. 精确匹配优先**

```python
# 先尝试精确日期
exact_match = data[
    data['time_key'].str.contains(date)
]
if not exact_match.empty:
    return exact_match.iloc[0]['close']
```

</div>

</div>

---

## 错误处理与容错

**多层次容错设计**

1. **LLM API 重试**：5 次自动重试
2. **价格查询降级**：API 失败 → 券商价格
3. **汇率懒加载**：仅在需要时触发，失败不中断
4. **期权解析回退**：US → HK → Morgan 格式逐级尝试

**日志追踪**

```python
logger.info(f"Stock: AAPL, Price: $150.50 (Source: API)")
logger.warning(f"No rate for EUR, using 1:1 (inaccurate)")
logger.error(f"Failed to fetch rate after 5 attempts: {e}")
```

---

## 数据质量保证

<div class="columns">

<div>

**Multiplier 正确性**

```python
# 优先级逻辑
1. broker_multiplier (明确值)
2. OTC 检测 → 1x
3. 标准期权 → 100x
4. 普通股票 → 1x
```

**Money Market Fund 识别**

```python
if 'money market fund' in desc.lower():
    # 重分类为现金
    cash[currency] += value
```

</div>

<div>

**货币转换一致性**

```python
# 使用统一的汇率数据
usd_value = amount * rate
# rate 始终是 from_currency→USD
```

**持仓去重验证**

```python
# 期权按 raw_description 聚合
# 股票按 stock_code 聚合
unique_key = (
    raw_description if is_option
    else stock_code
)
```

</div>

</div>

---

## 扩展性设计

**新增券商流程**

1. 添加 `PROMPT_TEMPLATES` 提取规则
2. （可选）配置 PDF 密码/页面过滤
3. 测试样本账单验证

**新增价格源流程**

```python
def get_price_new_source(symbol, date):
    # 实现新数据源逻辑
    pass

# 在 get_stock_price 中添加分支
if source == "new_source":
    return get_price_new_source(symbol, date)
```

---

## 监控与可观测性

**日志文件结构**

```
./log/2025-02-28/fundmate_20250228_153045.log
```

**关键日志内容**

- PDF 处理状态
- LLM 提取结果
- 价格查询来源
- 汇率缓存命中率
- 错误堆栈追踪

**Parquet 查询示例**

```python
import pandas as pd
df = pd.read_parquet('cash_summary_2025-02-28.parquet')
total_usd = df['usd_total'].sum()
print(f"Total: ${total_usd:,.2f}")
```

---

## 技术栈总结

| 组件 | 技术选型 | 理由 |
|------|----------|------|
| LLM | Google Gemini 2.5 Pro | 多模态支持，直接处理 PDF |
| 价格源 | Futu OpenD + akshare | 实时行情 + 历史数据回退 |
| 存储 | Parquet + CSV | 高性能列存 + 通用格式 |
| 并发 | ThreadPoolExecutor | 简单高效的线程池 |
| 日志 | loguru | 结构化日志，自动轮转 |
| 汇率 | exchangerate-api.com | 可靠的历史汇率 API |

---

## 实际应用场景

**1. 日终资产核对**

```bash
python src/main.py ./statements --date 2025-02-28
```

自动处理 10+ 券商账单，生成统一报表

**2. 历史数据分析**

```python
dates = persistence.get_available_dates()
# ['2025-01-31', '2025-02-28', ...]

for date in dates:
    data = persistence.load_broker_data(date)
    # 时间序列分析
```

---

## 实际应用场景（续）

**3. 跨券商持仓汇总**

CSV 文件自动生成汇总行：

- 总现金（跨券商）
- 总持仓（去重后）
- 总资产

**4. 期权组合估值**

自动识别并正确计算：

- 美股标准期权（100x）
- 港股期权（100x）
- OTC 期权（1x）

---

## Q&A

**常见问题**

1. **如何添加新券商支持？**
   - 修改 `prompt_templates.py` 添加提取规则

2. **如何处理价格查询失败？**
   - 自动降级使用券商提供价格

3. **如何查看历史数据？**
   - Parquet 文件可用 Pandas/Spark 直接读取

4. **如何调试 LLM 提取错误？**
   - 检查 `./log/DATE/fundmate_*.log` 中的完整 API 响应

---

## 总结

**FundMate 核心优势**

- **自动化**：LLM 驱动的智能数据提取
- **准确性**：双层缓存 + 价格降级策略
- **可扩展**：模块化设计，易于添加新券商
- **高性能**：并发处理 + 批量优化
- **可追溯**：Parquet 持久化 + 详细日志

**技术创新点**

1. 多模态 LLM 直接处理 PDF（无需人工转换）
2. 跨券商持仓去重与价格优化
3. 货币市场基金智能重分类
4. 期权倍数优先级逻辑

---

# 谢谢！

**项目地址**: `/Users/seven/Project/FundMate-1`

**文档**: `CLAUDE.md`

**联系方式**: [您的联系方式]
