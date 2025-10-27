# FundMate Web Client - Quick Start Guide

快速开始使用 FundMate Web 界面查看和分析您的投资组合数据。

## 5 分钟快速启动

### 1. 安装 Web 依赖

```bash
# 激活 FundMate conda 环境
conda activate FundMate

# 安装 Flask 和相关依赖
pip install -r requirements-web.txt
```

### 2. 确保您有数据

Web 界面需要已处理的数据文件。如果还没有处理数据：

```bash
# 启动 Futu OpenD（用于获取实时价格）
./FutuOpenD -addr 127.0.0.1 -port 11111

# 处理 broker 语句
python src/main.py ./data/statements --date 2025-02-28
```

这将在 `./out/result/2025-02-28/` 生成数据文件。

### 3. 启动 Web 应用

```bash
# 使用启动脚本（推荐）
./run_web.sh

# 或直接运行
python web_app.py
```

### 4. 访问界面

在浏览器中打开: **http://localhost:5000**

## 主要功能

### 📊 Dashboard（仪表盘）
- 投资组合总览
- 现金和持仓汇总
- 按经纪商统计
- 货币分布

### 📈 Positions（持仓）
- 所有持仓详情
- 按经纪商筛选
- 搜索功能
- 可排序表格
- 导出 CSV

### 💰 Cash（现金）
- 按货币查看现金
- 按经纪商查看分布
- 汇率信息
- USD 等值总计

### 🔄 Compare（对比）
- 日期对比分析
- 投资组合变化追踪
- 收益率计算
- 详细指标对比

## 常见问题

### Q: 显示"No Portfolio Data Available"
A: 确保您已经运行了主处理程序并生成了数据文件：
```bash
python src/main.py ./data/statements --date YYYY-MM-DD
```
检查 `./out/result/` 目录是否有日期文件夹。

### Q: 端口 5000 已被占用
A: 使用其他端口：
```bash
./run_web.sh 8080  # 使用端口 8080
```

### Q: 数据显示不完整
A: 当前版本的数据结构包含以下列：
- **Cash**: date, broker_name, account_id, cny, hkd, usd, usd_total
- **Positions**: date, broker_name, account_id, stock_code, holding

## 键盘快捷键

- `Ctrl/Cmd + K` - 聚焦搜索框
- `Esc` - 清除搜索
- `Ctrl/Cmd + P` - 打印报告

## 生产部署

对于生产环境，使用 Gunicorn：

```bash
# 使用配置文件
gunicorn -c gunicorn.conf.py web_app:app

# 或手动指定参数
gunicorn -w 4 -b 0.0.0.0:5000 web_app:app
```

### 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 目录结构

```
FundMate-1/
├── web_app.py              # Flask 主应用
├── web/
│   ├── templates/          # HTML 模板
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── positions.html
│   │   ├── cash.html
│   │   ├── compare.html
│   │   └── about.html
│   └── static/             # 静态资源
│       ├── css/style.css   # 样式
│       └── js/main.js      # JavaScript
├── run_web.sh              # 启动脚本
├── gunicorn.conf.py        # 生产配置
└── requirements-web.txt    # Web 依赖
```

## 安全建议

生产环境中：

1. **修改密钥**: 设置环境变量 `FLASK_SECRET_KEY`
2. **使用 HTTPS**: 配置 SSL 证书
3. **添加认证**: 考虑使用 Flask-Login
4. **防火墙**: 限制访问 IP
5. **关闭 Debug**: 生产环境不要使用 debug 模式

## 下一步

- 查看 [WEB_README.md](WEB_README.md) 了解完整文档
- 查看 [CLAUDE.md](CLAUDE.md) 了解 FundMate 架构
- 查看 [README.md](README.md) 了解项目概述

## 获取帮助

如有问题：
1. 检查终端中的 Flask 日志
2. 检查浏览器控制台错误
3. 查看 `./log/` 目录中的日志文件
4. 确认数据文件正确生成

祝使用愉快！🚀
