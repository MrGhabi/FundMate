# FundMate 批量上传快速开始

## 🚀 5 分钟快速上手

### 第一步：准备报表文件

将所有券商的报表重命名，确保文件名包含券商名称：

```bash
# ✅ 正确的命名
IB_Statement_Feb.pdf
FUTU_Holdings_Feb.pdf
MOOMOO_Report_Feb.pdf

# ❌ 错误的命名（无法自动识别）
statement.pdf
holdings.pdf
report.pdf
```

### 第二步：打包（可选）

```bash
# 方法 1：创建 ZIP（推荐）
zip statements_2025-02-28.zip *.pdf *.xlsx

# 方法 2：直接上传多个文件（不打包）
# 跳过这一步，直接选择多个文件上传
```

### 第三步：启动服务

```bash
# 终端 1：启动 Futu OpenD（必需）
./tools/futu/FutuOpenD -addr 127.0.0.1 -port 11111

# 终端 2：启动 Web 应用
python web_app.py
```

### 第四步：上传并处理

1. 打开浏览器：`http://localhost:5000`
2. 点击 **Upload** 菜单
3. 确保 **"Auto-detect brokers"** 已勾选 ✓
4. 选择日期（如今天）
5. 拖放 ZIP 文件（或选择多个文件）
6. 看到检测到的券商后，点击 **"Process Statements"**
7. 等待进度条完成（约 5-10 分钟）
8. 自动跳转到 Dashboard 查看结果！

## 📦 ZIP 文件示例

创建一个包含所有报表的 ZIP：

```
statements_2025-02-28.zip
├── IB_Statement.pdf          ← 会被识别为 IB
├── FUTU_Holdings.pdf         ← 会被识别为 FUTU
├── MOOMOO_Cash.pdf           ← 会被识别为 MOOMOO
├── MOOMOO_Positions.pdf      ← 会被识别为 MOOMOO
├── MS_Options.xlsx           ← 会被识别为 MS
└── GS_Options.xlsx           ← 会被识别为 GS
```

**结果**：系统会检测到 5 个券商（IB, FUTU, MOOMOO, MS, GS），并逐个处理！

## 🎯 实际示例

### 示例 1：最简单的方式

```bash
# 1. 准备文件（重命名以包含券商名称）
ls
IB_Feb.pdf  FUTU_Feb.pdf  MOOMOO_Feb.pdf

# 2. 打包
zip all_statements.zip *.pdf

# 3. 上传
# - 访问 http://localhost:5000/upload
# - 拖放 all_statements.zip
# - 选择日期
# - 点击 "Process Statements"

# 4. 完成！
# 3 个券商全部处理完成，自动跳转到 Dashboard
```

### 示例 2：不使用 ZIP

```bash
# 1. 准备文件
IB_Statement.pdf
FUTU_Holdings.pdf
MOOMOO_Report.pdf

# 2. 直接上传
# - 访问 http://localhost:5000/upload
# - 点击浏览，同时选择 3 个 PDF 文件
# - 系统实时显示检测到的券商
# - 点击 "Process Statements"

# 3. 完成！
```

## 🏷️ 券商名称关键词

确保文件名包含以下任一关键词：

| 券商 | 关键词 |
|-----|--------|
| IB | `ib`, `interactive` |
| FUTU | `futu`, `富途` |
| MOOMOO | `moomoo`, `moo`, `富牛` |
| MS | `morgan`, `ms` |
| GS | `goldman`, `gs` |
| 其他 | 见 [BATCH_UPLOAD_GUIDE.md](BATCH_UPLOAD_GUIDE.md) |

## ⚡ 进度显示

上传后会看到实时进度：

```
[==>       ] 10%  Processing IB (1/3)...
[====>     ] 30%  Extracting data for IB with LLM...
[======>   ] 60%  Processing FUTU (2/3)...
[========> ] 85%  Processing MOOMOO (3/3)...
[==========] 100% Successfully processed all 3 broker(s)!
```

## ❓ 常见问题速查

### Q: 文件名无法识别？

```bash
# 重命名文件，添加券商关键词
mv statement.pdf IB_statement.pdf
```

### Q: 不想自动检测？

取消勾选 "Auto-detect brokers"，手动输入券商名称。

### Q: ZIP 太大？

分批上传：
```bash
# 批次 1
zip batch1.zip IB*.pdf FUTU*.pdf

# 批次 2
zip batch2.zip MOOMOO*.pdf MS*.xlsx
```

### Q: 处理失败？

1. 检查 Futu OpenD 是否运行
2. 查看 `log/` 目录中的日志
3. 确认 `.env` 中的 API 密钥

## 📊 完成后

处理完成后，在 Dashboard 可以看到：

- ✅ 所有券商的总资产
- ✅ 各币种现金余额
- ✅ 所有持仓和市值
- ✅ 跨券商汇总报告

## 🎓 下一步

- 查看 [BATCH_UPLOAD_GUIDE.md](BATCH_UPLOAD_GUIDE.md) 了解详细功能
- 阅读 [WEB_UPLOAD_GUIDE.md](WEB_UPLOAD_GUIDE.md) 了解 API 使用
- 参考 [CLAUDE.md](CLAUDE.md) 了解系统架构

## 💡 专业提示

1. **批量命名工具**：使用 `rename` 或 PowerRename 批量重命名
2. **定期备份**：保存原始报表文件
3. **自动化**：考虑编写脚本自动下载和上传
4. **监控日志**：关注 `log/` 目录中的处理日志

开始使用批量上传，享受高效的投资组合管理！
