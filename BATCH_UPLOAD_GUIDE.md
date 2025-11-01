# FundMate 批量上传功能指南

## 🚀 新功能概述

FundMate 现在支持**智能批量上传**，让您可以一次性上传多个券商的报表，系统会自动识别并分类处理！

### 核心特性

1. **📦 ZIP 文件支持** - 上传包含所有报表的 ZIP 压缩包
2. **🤖 自动识别券商** - 从文件名自动检测券商名称
3. **⚡ 批量处理** - 同时处理多个券商的报表
4. **🎯 智能分类** - 自动按券商和日期组织文件
5. **📊 实时进度** - 显示每个券商的处理进度

## 使用方法

### 方式 1：ZIP 批量上传（推荐）

这是最简单的方式！

#### 步骤 1：准备文件

将所有券商报表放入一个 ZIP 文件：

```
statements_2025-02-28.zip
├── IB_Statement_Feb.pdf
├── FUTU_Holdings_Feb.pdf
├── MOOMOO_Cash.pdf
├── MOOMOO_Positions.pdf
├── MS_Options.xlsx
└── GS_Options.xlsx
```

**重要**：确保文件名包含券商名称（如 IB、FUTU、MOOMOO）

#### 步骤 2：上传

1. 打开 FundMate Web 界面：`http://localhost:5000`
2. 点击 **Upload** 导航链接
3. 确保 **"Auto-detect brokers"** 复选框已勾选
4. 选择报表日期（如 2025-02-28）
5. 拖放 ZIP 文件到上传区域，或点击浏览
6. 系统会显示检测到的券商：`IB` `FUTU` `MOOMOO` `MS` `GS`
7. 点击 **"Process Statements"**

#### 步骤 3：等待处理

系统会自动：
- 解压 ZIP 文件
- 识别各个券商
- 按券商分类文件
- 逐个处理每个券商的报表
- 显示整体进度（如 "Processing FUTU (2/5)..."）

完成后自动跳转到 Dashboard 查看结果！

### 方式 2：多文件直接上传

不想打包成 ZIP？可以直接选择多个文件：

1. 点击 Upload 页面
2. 勾选 **"Auto-detect brokers"**
3. 选择日期
4. 同时选择多个文件（按住 Ctrl/Cmd）：
   - `IB_Statement.pdf`
   - `FUTU_Holdings.pdf`
   - `MOOMOO_Report.pdf`
5. 系统会实时显示检测到的券商
6. 点击 "Process Statements"

### 方式 3：手动模式（单券商）

如果文件名不包含券商信息：

1. **取消勾选** "Auto-detect brokers"
2. 会显示 "Broker Name" 输入框
3. 手动输入券商名称（如 `IB`）
4. 选择日期和文件
5. 所有文件将被处理为该券商的报表

## 券商名称检测规则

系统会从文件名中检测以下券商：

| 券商代码 | 检测关键词 | 示例文件名 |
|---------|-----------|-----------|
| **IB** | ib, interactive, ibkr | `IB_Statement.pdf`, `Interactive_Brokers.pdf` |
| **FUTU** | futu, 富途 | `FUTU_Feb.pdf`, `富途证券_2月.pdf` |
| **MOOMOO** | moomoo, moo, 富牛 | `MOOMOO_Holdings.pdf`, `富牛_现金.pdf` |
| **MS** | morgan stanley, ms | `MS_Options.xlsx`, `Morgan_Stanley.xlsx` |
| **GS** | goldman sachs, gs | `GS_Statement.pdf`, `Goldman_Sachs.xlsx` |
| **SC** | standard chartered, sc | `SC_Report.pdf`, `渣打银行.pdf` |
| **HSBC** | hsbc, 汇丰 | `HSBC_Statement.pdf`, `汇丰_2月.pdf` |
| **CS** | credit suisse, cs | `CS_Holdings.pdf`, `瑞信_报表.pdf` |
| **LB** | longbridge, lb | `LB_Statement.pdf`, `长桥_现金.pdf` |
| **SOFI** | sofi | `SoFi_Statement.pdf` |
| **UBS** | ubs, 瑞银 | `UBS_Report.pdf`, `瑞银_持仓.pdf` |
| **WB** | webull, wb | `Webull_Statement.pdf`, `微牛_2月.pdf` |

**命名建议**：
- ✅ `IB_Statement_Feb2025.pdf`
- ✅ `FUTU-Holdings-20250228.pdf`
- ✅ `MOOMOO_Cash.pdf`
- ❌ `Statement.pdf` （无法识别）
- ❌ `Feb_Report.pdf` （无法识别）

## 实际使用案例

### 案例 1：月末批量处理

**场景**：每月底从 3 个券商下载报表

**操作流程**：

```bash
# 1. 下载所有报表到本地
IB_Statement_Feb.pdf
FUTU_Holdings_Feb.pdf
MOOMOO_Report_Feb.pdf

# 2. 打包成 ZIP（可选）
zip statements_2025-02-28.zip *.pdf

# 3. 上传到 FundMate
- 访问 http://localhost:5000/upload
- 勾选 "Auto-detect brokers"
- 选择日期：2025-02-28
- 拖放 ZIP 文件

# 4. 等待处理（约 5-10 分钟）
Processing IB (1/3) - 1 file(s)...     [====>     ] 30%
Processing FUTU (2/3) - 1 file(s)...   [=======>  ] 60%
Processing MOOMOO (3/3) - 1 file(s)... [=========>] 90%
Completed all 3 broker(s)!             [==========] 100%

# 5. 自动跳转到 Dashboard 查看汇总结果
```

**结果**：一次操作处理所有券商，节省大量时间！

### 案例 2：混合文件类型上传

**场景**：同时处理 PDF 和 Excel 文件

```bash
# 准备文件
IB_Statement.pdf        # PDF 报表
FUTU_Holdings.pdf       # PDF 报表
MS_Options.xlsx         # Excel 期权报表
GS_Options.xlsx         # Excel 期权报表

# 一次性上传所有文件
- 同时选择 4 个文件
- 系统检测到：IB, FUTU, MS, GS
- 自动分类处理 PDF 和 Excel
```

### 案例 3：处理同券商多个账户

**场景**：在同一券商有多个账户

```bash
# 文件命名
IB_Account1.pdf
IB_Account2.pdf
IB_Account3.pdf

# 上传后
- 检测到券商：IB
- 处理 3 个文件
- 合并到同一个券商的数据中
```

## 处理进度说明

### 进度阶段

批量上传会显示详细的进度信息：

```
5%   - Starting batch processing for 3 broker(s)...
10%  - Processing IB (1/3) - 1 file(s)...
25%  - Extracting data for IB with LLM...
30%  - Completed IB (1/3)...
40%  - Processing FUTU (2/3) - 1 file(s)...
55%  - Extracting data for FUTU with LLM...
60%  - Completed FUTU (2/3)...
70%  - Processing MOOMOO (3/3) - 1 file(s)...
85%  - Extracting data for MOOMOO with LLM...
90%  - Completed MOOMOO (3/3)...
100% - Successfully processed all 3 broker(s) for 2025-02-28
```

### 状态指示

- **🟢 Completed** - 所有券商处理成功
- **🟡 Partial** - 部分券商成功，部分失败
- **🔴 Failed** - 全部失败

## 文件组织结构

上传的文件会自动组织成以下结构：

```
data/uploads/
├── temp/
│   └── {job-id}/          # 临时解压目录（处理后删除）
│       └── *.pdf
├── IB/
│   └── 2025-02-28/
│       ├── IB_Statement.pdf
│       └── IB_Account2.pdf
├── FUTU/
│   └── 2025-02-28/
│       └── FUTU_Holdings.pdf
└── MOOMOO/
    └── 2025-02-28/
        ├── MOOMOO_Cash.pdf
        └── MOOMOO_Positions.pdf
```

处理结果保存在：

```
out/result/
└── 2025-02-28/
    ├── cash_summary_2025-02-28.parquet      # 包含所有券商的现金
    ├── positions_2025-02-28.parquet         # 包含所有券商的持仓
    ├── portfolio_details_2025-02-28.csv     # 可读的汇总报告
    └── metadata_2025-02-28.json             # 处理元数据
```

## 常见问题

### Q1: 如果文件名无法识别怎么办？

**A:** 有两种解决方案：

1. **重命名文件**（推荐）：
   ```bash
   # 在文件名中添加券商关键词
   mv Statement.pdf IB_Statement.pdf
   ```

2. **使用手动模式**：
   - 取消勾选 "Auto-detect brokers"
   - 手动输入券商名称

### Q2: ZIP 文件中可以有子文件夹吗？

**A:** 可以！系统会自动提取所有有效文件，忽略文件夹结构。

```
statements.zip
├── IB/
│   └── Statement.pdf        # ✅ 会被提取
├── FUTU/
│   └── Holdings.pdf         # ✅ 会被提取
└── README.txt               # ❌ 非 PDF/Excel，会被忽略
```

### Q3: 一次可以上传多少文件？

**A:**
- 文件数量：无限制
- 总大小：200MB（可在 `web_app.py` 中调整）
- 建议：每次上传不超过 20 个文件，避免处理时间过长

### Q4: 如果某个券商处理失败怎么办？

**A:** 系统会继续处理其他券商：

```
✓ IB - 成功
✓ FUTU - 成功
✗ MOOMOO - 失败（错误：无法读取 PDF）

状态：Partial
结果：成功处理 2/3 个券商
```

失败的券商可以：
- 查看错误信息
- 检查文件是否损坏
- 单独重新上传该券商的文件

### Q5: 支持加密的 PDF 吗？

**A:** 支持！系统会自动尝试解密已配置密码的券商 PDF（如 MOOMOO、LB）。

其他加密 PDF 需要在 `src/pdf_processor.py` 中配置密码。

## 性能优化建议

### 提高处理速度

1. **使用 ZIP 文件**：减少上传时间
2. **合理命名**：准确的券商名称检测更快
3. **避免大文件**：单个 PDF 建议不超过 20MB
4. **高峰期避让**：LLM API 调用在非高峰期更快

### 减少 API 调用

系统已优化：
- 跨券商股票价格去重
- 相同股票只查询一次
- 批量价格查询

## API 使用示例

### 批量上传 API

```bash
# 上传 ZIP 文件（自动检测）
curl -X POST http://localhost:5000/upload \
  -F "files=@statements.zip" \
  -F "auto_detect=true" \
  -F "date=2025-02-28"

# 响应
{
  "job_id": "uuid-here",
  "status": "processing",
  "brokers": ["IB", "FUTU", "MOOMOO"],
  "message": "Processing 8 file(s) for 3 broker(s): IB, FUTU, MOOMOO"
}
```

### 查询批量处理状态

```bash
curl http://localhost:5000/api/jobs/{job_id}

# 响应
{
  "status": "processing",
  "brokers": ["IB", "FUTU", "MOOMOO"],
  "date": "2025-02-28",
  "progress": 45,
  "message": "Processing FUTU (2/3) - 3 file(s)...",
  "result": null,
  "error": null
}
```

## 与原有功能对比

| 功能 | 原版本 | 批量上传版本 |
|-----|-------|------------|
| 上传方式 | 手动选择单券商 | 自动识别多券商 |
| 文件格式 | PDF, Excel | PDF, Excel, **ZIP** |
| 券商数量 | 一次一个 | 一次多个 |
| 命名要求 | 需手动输入 | 自动检测 |
| 进度显示 | 单一进度 | 分券商进度 |
| 处理时间 | N 次操作 | 1 次操作 |

## 最佳实践

### 文件命名规范

建议采用以下命名格式：

```
{券商}_{账户}_{类型}_{日期}.{扩展名}

示例：
IB_U12345_Statement_20250228.pdf
FUTU_HK_Holdings_Feb2025.pdf
MOOMOO_Cash_2025-02.pdf
MS_Options_Feb.xlsx
```

### 批量处理工作流

```
月末操作流程：
1. [Day 1] 从各券商下载报表
2. [Day 1] 统一命名规范
3. [Day 1] 打包成 ZIP
4. [Day 1] 上传到 FundMate
5. [Day 1] 等待处理（10-20 分钟）
6. [Day 1] 查看 Dashboard 汇总
7. [Day 2] 生成月度报告
```

### 错误处理策略

```python
# 如果批量上传失败：
1. 检查 log/ 目录中的日志
2. 确认 Futu OpenD 正在运行
3. 验证 API 密钥配置
4. 尝试单独上传失败的券商
5. 检查文件是否损坏
```

## 故障排查

### 问题：检测不到券商

```
错误：No broker could be detected from filenames

解决：
1. 检查文件名是否包含券商关键词
2. 参考上面的"券商名称检测规则"表格
3. 或使用手动模式
```

### 问题：ZIP 解压失败

```
错误：Invalid ZIP file

解决：
1. 确认 ZIP 文件未损坏
2. 重新打包 ZIP
3. 确保使用标准 ZIP 格式（非 RAR、7z）
```

### 问题：部分券商失败

```
状态：Partial - Processed 2/3 brokers

解决：
1. 查看任务历史中的错误详情
2. 单独重新上传失败的券商
3. 检查该券商的文件是否正确
```

## 总结

批量上传功能让 FundMate 的使用更加高效：

- ✅ **节省时间**：一次操作处理所有券商
- ✅ **减少错误**：自动识别，无需手动输入
- ✅ **更大容量**：支持 ZIP，最大 200MB
- ✅ **智能分类**：自动按券商组织文件
- ✅ **实时反馈**：详细的处理进度显示

开始使用批量上传，让投资组合管理更轻松！

## 相关文档

- [WEB_UPLOAD_GUIDE.md](WEB_UPLOAD_GUIDE.md) - 基础上传功能文档
- [UPLOAD_DEMO.md](UPLOAD_DEMO.md) - 使用演示和示例
- [CLAUDE.md](CLAUDE.md) - 完整的项目文档
