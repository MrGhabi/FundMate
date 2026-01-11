# 持仓/现金变化核对技能

验证两个日期之间的持仓和现金变化是否正确、完整、可追溯。

---

## 适用场景

- 验证 TC 模式计算结果是否正确
- 排查持仓/现金异常变化
- 审计两个日期之间的交易完整性
- 确认缺失的 TC 文件

---

## 核对流程

### Step 1: 准备数据

收集两个日期的以下文件：

```bash
# 结果文件
out/result/{DATE}/portfolio_details_{DATE}.csv
out/result/{DATE}/cash_summary_{DATE}.parquet
out/result/{DATE}/positions_{DATE}.parquet

# 日志文件
log/{DATE}/fundmate_*.log  # 选择最新的

# TC 文件
data/archives/TC/TC-{DATE}-*.xlsx
# 或
temp/archives/TC/TC-{DATE}-*.xlsx
```

### Step 2: 确认运行参数

从日志中提取关键运行参数：

```
关键信息:
- base_date: 基础日期（使用的报表日期）
- target_date: 目标日期
- 各券商使用的报表: XXX_YYYY-MM-DD_*.pdf/xlsx
- TC 文件应用范围: (base_date, target_date]
```

**示例日志片段：**
```
Base date inferred from archive files: 2025-12-10
Target Date: 2025-12-11
CICC: no 2025-12-10 statement found; using nearest 2025-12-04
Filtered 12/50 transactions in date range [2025-10-31, 2025-12-11]
```

### Step 3: 提取持仓变化

使用 Python 对比两个日期的 CSV：

```python
import pandas as pd

df_old = pd.read_csv('out/result/2025-12-03/portfolio_details_2025-12-03.csv')
df_new = pd.read_csv('out/result/2025-12-11/portfolio_details_2025-12-11.csv')

# 分离持仓（排除 [CASH] 和 [SUMMARY]）
pos_old = df_old[~df_old['stock_code'].str.contains(r'\[CASH\]|\[SUMMARY\]', na=False)]
pos_new = df_new[~df_new['stock_code'].str.contains(r'\[CASH\]|\[SUMMARY\]', na=False)]

# 创建唯一键
pos_old['key'] = pos_old['broker_name'] + '|' + pos_old['stock_code']
pos_new['key'] = pos_new['broker_name'] + '|' + pos_new['stock_code']

# 对比
keys_old = set(pos_old['key'])
keys_new = set(pos_new['key'])

new_positions = keys_new - keys_old      # 新增持仓
removed_positions = keys_old - keys_new  # 移除持仓
common_positions = keys_old & keys_new   # 共有持仓
```

### Step 4: 提取现金变化

```python
cash_old = df_old[df_old['stock_code'].str.contains(r'\[CASH\]', na=False)]
cash_new = df_new[df_new['stock_code'].str.contains(r'\[CASH\]', na=False)]

# 按券商对比
for broker in cash_old['broker_name'].unique():
    v_old = cash_old[cash_old['broker_name'] == broker]['position_value_usd'].sum()
    v_new = cash_new[cash_new['broker_name'] == broker]['position_value_usd'].sum()
    diff = v_new - v_old
    if abs(diff) > 100:
        print(f"{broker}: ${v_old:,.2f} → ${v_new:,.2f} (Δ${diff:+,.2f})")
```

### Step 5: 提取 TC 交易记录

```python
import pandas as pd

# 读取 TC 文件
tc = pd.read_excel('temp/archives/TC/TC-2025-12-11-UNKNOWN.xlsx')
print(tc[['Trade Date', 'Broker', 'Stock Code', 'BUY/SELL', 'Quantity', 'Avg. Price', 'Amount (USD)']].to_string())
```

### Step 6: 逐笔验证持仓变化与 TC 交易

创建验证表格：

| Broker | 标的 | 旧持仓 | 新持仓 | 变化 | TC 记录 | 验证 |
|--------|------|--------|--------|------|---------|------|
| LB | DUOL | 0 | 10,000 | +10,000 | BUY 10000 DUOL | ✅ |
| CICC | COIN | 25,000 | 15,000 | -10,000 | SELL 10000 COIN | ✅ |
| TIGER | SERV | 400,000 | 350,000 | -50,000 | (无记录) | ⚠️ |

**验证状态：**
- ✅ 匹配: TC 记录与持仓变化一致
- ⚠️ 缺失: 持仓变化但无 TC 记录
- ❌ 错误: TC 记录与持仓变化不一致

### Step 7: 现金验证（反推法）

对于有 TC 记录的券商，验证现金变化是否符合预期：

```python
# 计算 TC 交易对现金的影响
tc_cash_impact = 0
for _, row in tc[tc['Broker'] == 'TIGER'].iterrows():
    if 'SELL' in row['BUY/SELL']:
        tc_cash_impact += abs(row['Amount (USD)'])  # 卖出收入
    else:
        tc_cash_impact -= abs(row['Amount (USD)'])  # 买入支出

# 对比实际现金变化
actual_diff = tiger_cash_new - tiger_cash_old
unexplained = actual_diff - tc_cash_impact

print(f"TC 交易影响: ${tc_cash_impact:,.2f}")
print(f"实际现金变化: ${actual_diff:,.2f}")
print(f"未解释部分: ${unexplained:,.2f}")
```

**未解释部分可能来源：**
- 缺失的 TC 交易（如 SERV 卖出）
- 基础报表差异（不同日期报表本身现金不同）
- 利息、分红、费用等

### Step 8: 验证缺失 TC 的交易

对于缺失 TC 记录的持仓变化，通过现金反推验证：

```python
# 示例：验证 SERV 卖出
serv_qty_change = -50000
serv_price_est = 10.5  # 估计卖出价格
serv_proceeds_est = abs(serv_qty_change) * serv_price_est

# 检查是否能解释未解释的现金变化
if abs(unexplained - serv_proceeds_est) < unexplained * 0.3:
    print(f"✓ SERV 卖出 ({serv_qty_change:,} × ${serv_price_est}) 可解释 ${serv_proceeds_est:,.2f}")
```

---

## 常见问题排查

### 问题 1: 持仓变化但无 TC 记录

**可能原因：**
1. 交易发生在两个报表之间，体现在新报表中
2. TC 文件缺失
3. 期权到期/行权

**验证方法：**
- 检查现金是否有对应的流入/流出
- 确认是否是期权到期日期

### 问题 2: 代码格式不一致

**症状：**
```
12-03: GOOGL270617C00500000
12-11: GOOGL270617C500000
```

**原因：**
不同日期的报表解析格式差异

**处理：**
手动确认是同一持仓，统计时合并处理

### 问题 3: 现金变化与 TC 交易不符

**可能原因：**
1. 缺失 TC 交易
2. 基础报表差异（不同日期报表本身现金不同）
3. 汇率变化（HKD/CNY 余额的 USD 估值变化）

**验证方法：**
```python
# 检查汇率变化
rate_old = 0.128478  # 12-03 HKD→USD
rate_new = 0.128501  # 12-11 HKD→USD
hkd_balance = 10000000
fx_impact = hkd_balance * (rate_new - rate_old)
print(f"汇率变化影响: ${fx_impact:,.2f}")
```

---

## 核对清单

```
□ Step 1: 收集两个日期的 CSV、日志、TC 文件
□ Step 2: 从日志确认 base_date、target_date、报表来源
□ Step 3: 对比持仓变化（新增/移除/数量变化）
□ Step 4: 对比现金变化（按券商）
□ Step 5: 提取 TC 交易记录
□ Step 6: 逐笔验证持仓变化与 TC 交易
□ Step 7: 现金反推验证
□ Step 8: 排查缺失 TC 的交易
□ 最终确认: 所有变化可解释
```

---

## 输出模板

```markdown
## {DATE_OLD} vs {DATE_NEW} 核对报告

### 运行参数
- 旧日期 base_date: {DATE_OLD}
- 新日期 base_date: {DATE_NEW_BASE}
- 新日期 target_date: {DATE_NEW}

### 总体变化
| 指标 | 旧值 | 新值 | 变化 |
|------|------|------|------|
| Total Cash | ${X} | ${Y} | ${Z} |
| Total Positions | ${X} | ${Y} | ${Z} |
| Grand Total | ${X} | ${Y} | ${Z} |

### TC 交易验证
| Broker | 标的 | 旧持仓 | 新持仓 | 变化 | TC 记录 | 验证 |
|--------|------|--------|--------|------|---------|------|
| ... | ... | ... | ... | ... | ... | ✅/⚠️/❌ |

### 问题项
1. [问题描述]
2. [问题描述]

### 结论
- 计算正确: ✅/❌
- 缺失 TC: [列表]
- 建议操作: [建议]
```

---

## 相关文件

- `src/trade_confirmation_processor.py`: TC 处理逻辑
- `src/data_persistence.py`: 数据持久化
- `docs/DEV.md` Section 5: TC 模式说明
