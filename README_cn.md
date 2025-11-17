# FundMate

**基于 LLM 的券商对账单处理与交易确认书增量更新系统。**

> Looking for English? Check [README.md](README.md).

## 快速入口

- 📘 [Developer Guide](docs/DEV.md) — 详细架构、目录规范、CLI/TC/Web 说明、环境变量、排障（英文）。
- 🤖 [Agent Onboarding](AGENTS.md) — 针对智能体/自动化流程的管线与测试说明。

## 核心特性

- **多格式解析**：PDF（LLM OCR）与 Excel 对账单统一成 `Position` 对象与现金科目。
- **交易确认书模式**：在基准组合上增量应用 TC，内置港股数字期权映射、基线缓存。
- **实时定价**：优先 Futu OpenD，akshare 兜底，货币市场基金自动归类为现金。
- **结构化落库**：每日输出 parquet/CSV 与汇总指标，供下游分析使用。
- **可选 Web UI**：直接浏览 `./out/result/<date>` 中的持仓/现金。

## 快速上手

```bash
# 1. 可编辑安装 + Web 依赖（如需 UI）
pip install -e .
pip install -e .[web]     # 仅在需要 Flask UI 时执行

# 2. 处理对账单（推荐 archives 目录）
python -m src.main data/archives --date 2025-02-28

# 3. 使用交易确认书做增量
python -m src.main data/archives --date 2025-07-22 --use-tc --base-date 2025-07-18

# 4. 测试
sh test/run_tests.sh                                   # 全量回归（需 Gemini + Futu）
python -m pytest test/e2e/test_tc_mode.py -vv          # 缓存基线的 TC 回归
```

## Web UI

```bash
./run_web.sh 5000
# 或
python -m src.webapp.app
```

Web 界面读取 `./out/result/<date>` 的结果文件。生产部署、模板/静态资源打包细节见 [docs/DEV.md](docs/DEV.md#6-web-ui)（英文）。

---

目录结构、所有 CLI 选项、交易确认书基线、环境变量、数据归档脚本等完整内容，已迁移至 [Developer Guide](docs/DEV.md)。此 README 仅保留入口与常用命令，方便快速上手。
