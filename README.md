# FundMate

**Automated broker statement processor with LLM-powered extraction and trade-confirmation updates.**

> 需要中文？请查看 [README_cn.md](README_cn.md)。

## Quick Links

- 📘 [Developer Guide](docs/DEV.md) — architecture, directory layout, CLI/TC/Web details, env vars, troubleshooting.
- 🤖 [Agent Onboarding](AGENTS.md) — pipeline decisions and testing philosophy for AI/automation agents.

## Highlights

- **Multi-format ingestion**: PDF (LLM OCR) + Excel statements unified into `Position` objects and cash buckets.
- **Incremental TC mode**: Apply trade confirmations on top of a base portfolio, with HK numeric option matching + cached baselines.
- **Real-time pricing**: Futu OpenD first, akshare fallback; money market funds auto-reclassified into cash.
- **Structured persistence**: Daily parquet/CSV outputs + summary metrics for downstream analytics.
- **Optional Flask UI**: Browse processed portfolios directly from `./out/result/<date>`.

## Quick Start

```bash
# 1. Install (editable) and optional web extras
pip install -e .
pip install -e .[web]    # only if you need the Flask UI

# 2. Process broker statements (archive structure recommended)
python -m src.main data/archives --date 2025-02-28

# 3. Incremental update via trade confirmations
python -m src.main data/archives --date 2025-07-22 --use-tc --base-date 2025-07-18

# 4. Tests
sh test/run_tests.sh                                  # full regression (needs Gemini + Futu)
python -m pytest test/e2e/test_tc_mode.py -vv         # cached TC regression
```

## Web UI

```bash
./run_web.sh 5000
# or
python -m src.webapp.app
```

The UI reads the persisted outputs under `./out/result/<date>`. Gunicorn deployments and template/static packaging details live in [docs/DEV.md](docs/DEV.md#6-web-ui).

---

For everything else—detailed CLI options, directory conventions, environment variables, testing matrix, data archiving tool—consult the [Developer Guide](docs/DEV.md). The previous long-form README content has been moved there verbatim for easier maintenance.
