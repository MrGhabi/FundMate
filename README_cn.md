# FundMate

**基于LLM的自动化券商对账单处理系统**

## 概述

```
python src/main.py BROKER_FOLDER --date DATE [选项]
```

### 安装建议

```bash
pip install -e .
# 若需要 Web UI
pip install -e .[web]
```

## 描述

FundMate是一个生产级金融数据处理系统，用于从券商对账单中提取现金资产和持仓数据。支持PDF和Excel两种格式，使用LLM进行智能数据提取，并提供基于实时市价的资产估值。

### 核心特性

- **多格式支持**：PDF对账单（图像格式）和Excel文件（结构化数据）
- **LLM智能提取**：使用Google Gemini API进行智能解析
- **实时定价**：通过Futu OpenD API获取实时股票和期权价格（支持akshare备用）
- **智能MMF处理**：自动识别货币市场基金并重分类为现金
- **多币种处理**：自动货币转换并重新计算总额（USD、CNY、HKD）
- **并发处理**：多券商账户的并行处理（最多10个线程）
- **数据持久化**：Parquet和CSV格式的结构化输出

## 支持的券商

### PDF格式券商
- **IB** (Interactive Brokers/盈透证券)
- **HUATAI** (华泰证券)
- **SDICS** (申万宏源)
- **TIGER** (老虎证券)
- **MOOMOO** (富途证券)
- **TFI** (天风国际)
- **CICC** (中金公司)
- **HTI** (海通国际)
- **LB** (Longbridge/长桥证券)
- **First Shanghai** (第一上海)

### Excel格式券商  
- **MS** (Morgan Stanley/摩根士丹利)
- **GS** (Goldman Sachs/高盛)

## 选项

### 必需参数

**BROKER_FOLDER**
  包含券商对账单文件的目录路径。必须遵循标准目录结构（见文件部分）。

**--date DATE**
  处理日期，格式为YYYY-MM-DD。用于价格查询和输出组织。

### 可选参数

**--broker BROKER**
  仅处理指定的券商。有效值包括IB、HUATAI、SDICS、TIGER、MOOMOO、TFI、CICC、HTI、MS、GS。未指定时，处理所有检测到的券商。

**--output DIR**  
  转换图像的输出目录。默认：`./out/pictures`

**-f, --force**
  强制重新转换PDF文件，即使图像已存在。适用于模板更改后的重新处理。

**--max-workers N**
  并发处理线程的最大数量。默认：10。在多核系统上增加此值可提高处理速度。

### 交易确认书模式

**--use-tc**
  启用交易确认书模式进行增量组合更新。此模式使用交易确认书文件从基准日期更新到目标日期的投资组合，适用于券商结单延迟或错误的情况。

**--base-date DATE**
  交易确认书模式的基准日期（YYYY-MM-DD格式）。如果未指定，自动使用最新可用的投资组合日期。这应该是最后一次完整券商结单的日期。

**--tc-folder PATH**
  交易确认书文件夹路径。默认：`data/archives/TradeConfirmation`。交易确认书文件必须遵循命名规范：`TC-{YYYY-MM-DD}-{原始文件名}.xlsx`

## Web 界面

FundMate 自带的 Flask 看板位于 `src/webapp` 包内。完成一次 `pip install -e .` 并额外执行 `pip install -e .[web]` 后，不论你从哪个工作目录启动，模板与静态资源都能正确加载。

- **开发模式**：`./run_web.sh 5000`（默认监听 `localhost:5000`，支持热重载）
- **直接入口**：`python -m src.webapp.app`
- **生产部署**：`gunicorn -c gunicorn.conf.py src.webapp.app:app`

Web UI 会读取 `./out/result/<date>` 下的输出，所以启动前请先跑一遍日结或交易确认流程，确保有数据可视化。

## 目录结构

FundMate支持两种目录结构：

### 归档模式（推荐）

按券商组织，文件名包含日期信息：

```
data/archives/
├── IB/
│   ├── IB_2025-02-28_U9018171.pdf
│   ├── IB_2025-06-30_U9018171.pdf
│   └── IB_2025-07-31_U9018171.pdf
├── HUATAI/
│   ├── HUATAI_2025-02-28_20250228.pdf
│   └── HUATAI_2025-06-30_202506.pdf
├── MS/             # Excel券商
│   ├── MS_2025-02-28_OptionDaily.XLS
│   └── MS_2025-06-30_OptionDaily.XLS
├── TradeConfirmation/  # 交易确认书文件
│   ├── TC-2025-07-21-Asia Internal Trade Confirmation - 20250721.xlsx
│   ├── TC-2025-07-21-US Trading Confirmation 0721_2025.xlsx
│   ├── TC-2025-07-22-US Trading Confirmation 0722_2025.xlsx
│   └── TC-2025-09-22-Internal Trade Confirmation - 20250922.xlsx
└── ...
```

**文件命名规范**：`{券商名称}_{YYYY-MM-DD}_{账户标识}.{扩展名}`

**优势**：
- 所有文件按券商集中管理，不再有日期目录碎片
- 文件名包含完整信息，易于查找和管理
- 支持多账户（同一券商不同账户通过标识符区分）

### Statement模式（传统）

按日期组织的目录结构：

```
data/20250228_Statement/
├── IB/
│   └── statement.pdf
├── HUATAI/
│   └── account.pdf
├── MS/
│   └── options.xlsx
└── ...
```

**注意**：
- 两种模式可以并存，程序自动识别
- 归档模式：传入 `data/archives` 路径
- Statement模式：传入 `data/YYYYMMDD_Statement` 路径

## 使用示例

### 基本用法

**归档模式**（推荐）：
```bash
# 处理特定日期的所有券商
python src/main.py data/archives --date 2025-02-28

# 仅处理指定券商
python src/main.py data/archives --date 2025-02-28 --broker IB

# 强制重新处理并提高并发度
python src/main.py data/archives --date 2025-02-28 -f --max-workers 8
```

**Statement模式**（传统）：
```bash
# 处理特定日期目录
python src/main.py data/20250228_Statement --date 2025-02-28

# 仅处理指定券商
python src/main.py data/20250228_Statement --date 2025-02-28 --broker IB
```

### 高级用法
```bash
# 自定义输出目录
python src/main.py ./data/statements --date 2025-02-28 --output ./custom/images

# 调试单个券商并启用详细日志
python src/main.py ./data/statements --date 2025-02-28 --broker HUATAI --max-workers 1
```

### 交易确认书模式

当券商结单延迟或错误时，使用交易确认书文件更新投资组合：

```bash
# 自动检测基准日期并更新到目标日期
python src/main.py data/archives --date 2025-07-22 --use-tc

# 显式指定基准日期
python src/main.py data/archives --date 2025-07-22 --use-tc --base-date 2025-07-18

# 自定义交易确认书文件夹
python src/main.py data/archives --date 2025-07-22 --use-tc \
  --base-date 2025-07-18 \
  --tc-folder /custom/path/to/TradeConfirmation
```

**工作原理**：
1. 从指定的（或自动检测的）基准日期加载基础投资组合
2. 应用基准日期到目标日期之间的所有交易确认书
3. 将价格更新到目标日期
4. 保存更新后的投资组合

**前提条件**：
- 必须存在基础投资组合（首先运行正常模式生成基准日期的数据）
- 交易确认书文件必须预处理为标准命名格式：`TC-{YYYY-MM-DD}-{原始文件名}.xlsx`
- 如需预处理文件，使用 `src/scripts/rename_trade_confirmations.py`

## 交易确认书文件预处理

来自不同来源的交易确认书文件可能具有不一致的命名。使用预处理脚本将其标准化：

```bash
# 预览更改（dry-run）
python src/scripts/rename_trade_confirmations.py

# 执行重命名
python src/scripts/rename_trade_confirmations.py --execute

# 自定义文件夹
python src/scripts/rename_trade_confirmations.py --folder /path/to/tc/files --execute
```

**Excel格式要求**：
交易确认书文件必须包含以下列：
- `Trade Date`: 交易日期
- `Stock Code`: 股票代码（例如 "9988 HK", "TSLA"）
- `BUY/SELL`: 交易方向（BUY、SELL 或 BUYCOVER）
- `Quantity`: 股数
- `Avg. Price`: 成交均价
- `Amount (USD)`: USD金额（现金影响）
- `Broker`: 券商名称
- `Currency`: 原始币种
- `Market/Exchange`（可选）: 市场标识符

## 输出

FundMate生成三类输出：

### 1. 资产汇总报告
控制台输出显示：
- 券商列表及数据源（PDF/Excel）
- 按币种分类的现金总额及美元等值
- 持仓价值及定价成功率
- 所有账户的总计

### 2. 结构化数据文件
保存至`./out/result/DATE/`：
- `cash_summary_DATE.parquet` - 按券商和币种分类的现金资产
- `positions_DATE.parquet` - 带市场价值和定价详情的持仓数据
- `portfolio_details_DATE.csv` - 人类可读的投资组合详细报告
- `metadata_DATE.json` - 处理元数据和汇率信息

### 3. 处理日志
`./log/DATE/fundmate.log`中的详细日志包括：
- PDF转换状态
- LLM提取结果
- 价格查询尝试
- 错误条件和重试

## 环境要求

### 必需依赖
- Python 3.8+
- Google Gemini API密钥（用于LLM数据提取）
- Futu OpenD（用于实时价格数据）
- 互联网连接（用于API访问和汇率）

### Python包
```
akshare>=1.17.0       # 市场数据备用源
futu-api>=9.4.0       # 主要价格数据源（Futu OpenD）
pandas>=2.0.0         # 数据操作
pydantic>=2.0.0       # 数据验证
loguru>=0.7.0         # 日志记录
pdf2image>=1.16.0     # PDF转换
openpyxl>=3.1.0       # Excel解析
python-dotenv>=1.0.0  # 环境变量
requests>=2.28.0      # HTTP客户端
Pillow>=9.0.0         # 图像处理
```

### 系统要求
- 4GB+内存（用于并发LLM处理）
- 2GB+磁盘空间（用于图像转换）
- 建议使用多核CPU（当`--max-workers > 10`时）
- 需要本地运行Futu OpenD（默认：127.0.0.1:11111）

## 环境变量

### 必需变量
- `LLM_API_KEY` - Google Gemini API密钥
- `LLM_BASE_URL` - Gemini API端点URL
- `EXCHANGE_API_KEY` - 汇率API密钥（exchangerate.host）

### 可选变量
- `LLM_MODEL` - LLM模型名称（默认：`gemini-2.5-pro`）
- `FUNDMATE_PRICE_SOURCE` - 价格源：`futu`或`akshare`（默认：`futu`）
- `FUTU_HOST` - Futu OpenD主机（默认：`127.0.0.1`）
- `FUTU_PORT` - Futu OpenD端口（默认：`11111`）
- `FUTU_TIMEOUT` - Futu API超时秒数（默认：`30`）
- `FUNDMATE_OUTPUT_DIR` - 输出目录（默认：`./out`）
- `FUNDMATE_LOG_DIR` - 日志目录（默认：`./log`）

### .env文件示例
在项目根目录创建`.env`文件：
```bash
# LLM配置（Google Gemini）
LLM_API_KEY=your_gemini_api_key_here
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_MODEL=gemini-2.5-pro

# 汇率API
EXCHANGE_API_KEY=your_exchange_rate_key_here

# 价格数据源（Futu OpenD）
FUNDMATE_PRICE_SOURCE=futu
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# 输出目录
FUNDMATE_OUTPUT_DIR=./out
FUNDMATE_LOG_DIR=./log
```

## 前置依赖

### Futu OpenD配置（价格数据必需）

FundMate使用Futu OpenD API获取实时股票和期权价格。处理对账单前必须运行Futu OpenD。

**安装步骤：**
1. 从[富途开放API](https://www.futunn.com/download/OpenAPI)下载Futu OpenD
2. 安装并启动Futu OpenD：
   ```bash
   ./FutuOpenD -addr 127.0.0.1 -port 11111
   ```
3. 验证连接（FundMate将自动连接到`FUTU_HOST:FUTU_PORT`）

**注意**：如果Futu OpenD未运行，价格获取将失败，持仓将仅使用券商提供的价格。

## 限制

### 价格数据覆盖范围
- **股票价格**：通过Futu API支持美股、港股和A股市场（支持akshare备用）
- **期权**：
  - ✅ **美股期权**（通过Futu API，OCC格式）
  - ✅ **港股期权**（通过Futu API，HKATS格式）
  - ✅ **OTC期权**（使用券商提供的价格）
- **退市股票**：当历史API数据不可用时自动使用券商价格
- **货币市场基金**：自动检测并重分类为现金（例如："CSOP USD Money Market Fund"）

### 券商特定说明
- **MS/GS Excel**：仅有持仓数据（Excel对账单中无现金资产）
- **PDF质量**：LLM提取精度依赖于对账单图像质量
- **MOOMOO**：处理证券和基金两个表格；自动检测MMF

### 已知问题
- Futu API需要本地OpenD实例运行
- 部分A股期权可能回退到券商价格
- 历史价格受限于Futu API数据可用性

请使用`./log/DATE/fundmate.log`中的详细日志报告错误。

## 数据归档工具

### 归档现有对账单

FundMate提供了归档工具，可将传统的 `*_Statement` 目录结构转换为归档模式：

```bash
# 试运行（查看将要执行的操作）
python scripts/archive_statements.py --dry-run

# 正式归档（复制文件到 data/archives）
python scripts/archive_statements.py

# 自定义路径
python scripts/archive_statements.py --data-dir /path/to/data --archive-dir /path/to/archives
```

**归档工具功能**：
- 自动扫描所有 `data/*_Statement/` 目录
- 按券商分类复制文件到 `data/archives/{券商}/`
- 统一重命名为标准格式：`{券商}_{YYYY-MM-DD}_{账户ID}.{扩展名}`
- 智能提取账户ID（支持所有券商格式）
- 生成详细的归档报告

**注意**：归档工具只复制文件，不删除原始数据，确保安全。

## 文件

### 输入文件
- `BROKER_FOLDER/BROKER/*.pdf` - 券商PDF对账单
- `BROKER_FOLDER/BROKER/*.xlsx` - Excel期权对账单（MS/GS）

### 输出文件
- `./out/pictures/DATE/BROKER/` - 转换的PNG图像
- `./out/result/DATE/` - 结构化数据文件
- `./log/DATE/fundmate.log` - 处理日志

### 配置文件
- `src/prompt_templates.py` - 各券商的LLM提取提示
- `src/price_fetcher.py` - 市场数据源配置
- `src/config.py` - 全局设置和环境变量
- `.env` - 环境变量配置（不在仓库中）


## 版本

本文档对应FundMate v1.0 - 集成Excel功能的生产版本。
