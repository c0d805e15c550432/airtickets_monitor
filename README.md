# 机票价格监控

持续监控机票票价，并在低价时通过邮件进行提醒。

## 功能特性

- **多数据源采集**：支持携程、同程、飞猪三大平台，可自定义优先级，主源失败时自动降级
- **双模式运行**：提供 GUI 图形界面（`main.py`）和轻量命令行模式（`main_simple.py`）
- **自动记录**：每次采集后自动保存至 `history.json` 并追加到 Excel 表格
- **低价监控**：可设置关注航班，检测到历史最低价时自动发送邮件提醒
- **后台运行**：支持无头浏览器模式，可长期后台持续运行

## 环境要求

- Python 3.10+
- 系统需安装 Chromium 浏览器（playwright 会自动安装）

## 安装步骤

### 1. 克隆或下载本项目

```bash
cd airtickets_monitor
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 playwright 浏览器驱动

```bash
playwright install chromium
```

## 数据源说明

使用 Playwright 框架从以下网站获取最新机票价格信息：

| 数据源 | 网址 | 特点 |
|--------|------|------|
| **携程旅行** | [ctrip.com](https://www.ctrip.com) | 数据全且准确，但容易触发人机验证或强制登录 |
| **同程旅行** | [ly.com](https://www.ly.com) | 数据不全，且价格偏高，但长时间运行稳定，不易触发反爬 |
| **飞猪旅行** | [fliggy.com](https://www.fliggy.com) | 数据较全，但价格含平台折扣，不够精准 |

> 建议将同程（ly）作为首选数据源以获得最稳定的采集体验。

## 配置说明

编辑 `config.json` 进行配置：

```json
{
  "depart": "BJS",              // 出发地三字码（如 BJS=北京, SHA=上海, URC=乌鲁木齐）
  "arrive": "URC",              // 目的地三字码
  "year": "2026",               // 出发日期-年
  "month": "06",                // 出发日期-月
  "day": "25",                  // 出发日期-日
  "headless": true,             // 是否使用无头模式（true=后台运行，false=显示浏览器）
  "dump_raw_data": false,       // 是否保存原始响应数据到 raw_data/ 目录
  "priority": [                 // 数据源优先级，排在前面的优先使用
    "ly",
    "fliggy",
    "ctrip"
  ],
  "monitored_flights": [        // 关注的航班号列表（用于低价邮件提醒）
    "CZ6902",
    "CA1291"
  ],
  "interval_seconds": 21600,    // 采集间隔（秒），21600=每6小时
  "auto_save_excel": true,      // 是否自动保存到 Excel
  "email": {                    // 邮件提醒配置（可选）
    "enabled": true,
    "smtp_server": "smtp.qq.com",
    "smtp_port": 587,
    "username": "your_email@qq.com",
    "password": "your_smtp_auth_code",
    "recipient": "recipient@qq.com"
  }
}
```

## 使用方法

### 方式一：GUI 图形界面（推荐）

```bash
python main.py
```

或双击 `run.bat` 启动。

功能包括：
- 可视化配置航线、日期、数据源优先级
- 一键启动/停止后台监控
- 实时查看采集数据表格
- 手动导出 Excel
- 邮件提醒开关与 SMTP 设置
- 关注航班管理

### 方式二：命令行轻量模式

```bash
python main_simple.py
```

适用于服务器或无需 GUI 的场景，默认每 2 小时采集一次携程数据并保存至 Excel。

## 项目结构

```
airtickets_monitor/
├── main.py                  # GUI 主程序（tkinter 界面）
├── main_simple.py           # 命令行轻量版主程序
├── run.bat                  # Windows 一键启动脚本
├── config.json              # 配置文件
├── requirements.txt         # Python 依赖列表
├── README.md                # 项目说明
├── utils/                   # 工具模块
│   ├── __init__.py
│   ├── process_data.py      # 数据处理（解析各平台原始数据）
│   ├── get_data_ctrip.py    # 携程数据采集
│   ├── get_data_ly.py       # 同程数据采集
│   ├── get_data_fliggy.py   # 飞猪数据采集
│   ├── get_data_trip.py     # Trip.com 国际版携程
│   ├── get_data_csair.py    # 南方航空数据采集
│   └── get_data_ceair.py    # 东方航空数据采集（开发中）
├── outputs/                 # 输出目录
│   └── history.json         # 历史数据记录
└── raw_data/                # 原始响应数据（dump_raw_data=true 时）
```

