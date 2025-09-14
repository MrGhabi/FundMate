# FundMate

**基于LLM的自动化券商对账单处理系统**

## 概述

```
python src/main.py BROKER_FOLDER --date DATE [选项]
```

## 描述

FundMate是一个生产级金融数据处理系统，用于从券商对账单中提取现金资产和持仓数据。支持PDF和Excel两种格式，使用LLM进行智能数据提取，并提供基于实时市价的资产估值。


### 核心特性

- **多格式支持**：PDF对账单（图像格式）和Excel文件（结构化数据）
- **LLM智能提取**：非结构化券商文档的智能解析
- **实时定价**：通过akshare集成获取实时股票和期权价格
- **多币种处理**：自动货币转换（USD、CNY、HKD）
- **并发处理**：多券商账户的并行处理
- **数据持久化**：Parquet格式的结构化输出

## 支持的券商

### PDF格式券商
- **IB** (Interactive Brokers)
- **HUATAI** 
- **SDICS**
- **TIGER** 
- **MOOMOO** 
- **TFI** 
- **CICC** 
- **HTI** 
- **First Shanghai** 

### Excel格式券商  
- **MS** (Morgan Stanley)
- **GS** (Goldman Sachs)

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
  并发处理线程的最大数量。默认：3。在多核系统上增加此值可提高处理速度。

## 目录结构

FundMate需要特定的目录布局：

```
statements/
├── DATE/               # 例如：2025-02-28/
│   ├── IB/
│   │   └── statement.pdf
│   ├── HUATAI/
│   │   └── account.pdf
│   ├── MS/             # Excel券商
│   │   └── options.xlsx
│   └── ...
```

对于按日期处理，结构变为：
```
statements/DATE/BROKER/files
```

## 使用示例

### 基本用法
```bash
# 处理特定日期的所有券商
python src/main.py ./data/statements --date 2025-02-28

# 仅处理指定券商
python src/main.py ./data/statements --date 2025-02-28 --broker IB

# 强制重新处理并提高并发度
python src/main.py ./data/statements --date 2025-02-28 -f --max-workers 8
```

### 高级用法
```bash
# 自定义输出目录
python src/main.py ./data/statements --date 2025-02-28 --output ./custom/images

# 调试单个券商并启用详细日志
python src/main.py ./data/statements --date 2025-02-28 --broker HUATAI --max-workers 1
```

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
- `cash_summary_DATE.parquet` - 按券商分类的现金资产
- `positions_DATE.parquet` - 带市场价值的持仓数据
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
- OpenAI API密钥（用于LLM处理）
- 互联网连接（用于价格数据和汇率）

### Python包
```
akshare>=1.11.0      # 中国市场数据
openai>=1.0.0        # LLM处理
pandas>=2.0.0        # 数据操作
pydantic>=2.0.0      # 数据验证
loguru>=0.7.0        # 日志记录
pdf2image>=1.16.0    # PDF转换
```

### 系统要求
- 4GB+内存（用于并发LLM处理）
- 2GB+磁盘空间（用于图像转换）
- 建议使用多核CPU（当`--max-workers > 3`时）

## 限制

### 价格数据覆盖范围
- **股票价格**：通过akshare支持美股、港股和A股市场
- **期权**：仅限中国境内期权；美股/港股期权显示为未定价
- **退市股票**：自动检测并跳过（如HK:04827）

### 券商特定说明
- **MOOMOO**：需要PDF密码"0592"
- **MS/GS Excel**：仅有持仓数据（无现金资产）
- **PDF质量**：OCR精度依赖于对账单图像质量


请使用`./log/DATE/fundmate.log`中的详细日志报告错误。

## 文件

### 输入文件
- `BROKER_FOLDER/DATE/BROKER/*.pdf` - 券商PDF对账单
- `BROKER_FOLDER/DATE/BROKER/*.xlsx` - Excel期权对账单（MS/GS）

### 输出文件
- `./out/pictures/DATE/BROKER/` - 转换的PNG图像
- `./out/result/DATE/` - 结构化数据文件
- `./log/DATE/fundmate.log` - 处理日志

### 配置文件
- `src/prompt_templates.py` - 各券商的LLM提取提示
- `src/price_fetcher.py` - 市场数据源配置


## 版本

本文档对应FundMate v1.0 - 集成Excel功能的生产版本。
