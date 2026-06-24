"""
机票价格监控系统 - GUI界面
功能：
1. 三大数据源（携程/同程/飞猪）可自定义优先级采集
2. 表格同时记录数据源信息
3. 自定义监控航班，检测到最低票价时通过SMTP发送邮件提醒
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import os
import time
from datetime import datetime
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict

# 导入现有数据处理模块
from utils import process_data

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# 数据源映射
SOURCE_MAP = {
    "ctrip": ("携程", "#4CAF50"),
    "ly": ("同程", "#2196F3"),
    "fliggy": ("飞猪", "#FF9800"),
    "csair": ("南航", "#F44336"),
    "ceair": ("东航", "#9C27B0"),
    "hnair": ("海航", "#009688")
}


class AirfareMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("机票价格监控系统 v2.0")
        self.root.geometry("1200x750")
        self.root.minsize(1000, 650)

        # 加载配置
        self.config = self.load_config()

        # 数据存储
        self.all_records = []       # [{time, flightNo, price, source}, ...]
        self.price_lowest = {}      # {flightNo: {"price": min_price, "source": src, "time": t}}

        # 监控状态
        self.monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()

        # 设置样式
        self.setup_styles()

        # 构建界面
        self.build_ui()

        # 加载已有历史数据到表格
        self.load_history()

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── 配置管理 ──────────────────────────────────────────────

    def load_config(self):
        """加载或创建默认配置"""
        defaults = {
            "depart": "BJS",
            "arrive": "URC",
            "year": "2026",
            "month": "06",
            "day": "25",
            "headless": True,
            "dump_raw_data": True,
            "priority": ["ctrip", "ly", "fliggy", "csair", "ceair", "hnair"],
            "monitored_flights": [],
            "interval_seconds": 7200,
            "auto_save_excel": True,
            "email": {
                "enabled": False,
                "smtp_server": "smtp.qq.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "recipient": "",
            },
        }
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                defaults.update(loaded)
        return defaults

    def save_config(self):
        """保存配置到文件"""
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # ── 样式 ──────────────────────────────────────────────────

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=25, font=("Microsoft YaHei", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))
        style.configure("TButton", font=("Microsoft YaHei", 10))
        style.configure("TLabel", font=("Microsoft YaHei", 10))
        style.configure("TLabelframe.Label", font=("Microsoft YaHei", 10, "bold"))

    # ── 界面构建 ──────────────────────────────────────────────

    def build_ui(self):
        # 顶部控制面板
        self.build_control_panel()

        # 主内容区：左侧配置面板 + 右侧表格
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧配置面板（带滚动条）
        left_frame = ttk.Frame(main_pane, width=380)
        self.build_config_panel(left_frame)
        main_pane.add(left_frame, weight=0)

        # 右侧表格+日志
        right_frame = ttk.Frame(main_pane)
        self.build_data_panel(right_frame)
        main_pane.add(right_frame, weight=1)

        # 底部状态栏
        self.build_status_bar()

    def build_control_panel(self):
        """顶部控制栏"""
        ctrl_frame = ttk.Frame(self.root, padding="5 5 5 5")
        ctrl_frame.pack(fill=tk.X, padx=5, pady=(5, 0))

        # 左侧：监控按钮组
        left_btns = ttk.Frame(ctrl_frame)
        left_btns.pack(side=tk.LEFT)

        self.btn_fetch = ttk.Button(left_btns, text="▶ 立即采集", command=self.manual_fetch)
        self.btn_fetch.pack(side=tk.LEFT, padx=2)

        self.btn_start = ttk.Button(left_btns, text="⏳ 开始监控", command=self.start_monitoring)
        self.btn_start.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(left_btns, text="⏹ 停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)

        self.btn_clear = ttk.Button(left_btns, text="🗑 清空表格", command=self.clear_table)
        self.btn_clear.pack(side=tk.LEFT, padx=2)

        self.btn_export = ttk.Button(left_btns, text="📊 导出Excel", command=self.export_excel)
        self.btn_export.pack(side=tk.LEFT, padx=2)

        # 右侧：采集间隔设置
        right_opts = ttk.Frame(ctrl_frame)
        right_opts.pack(side=tk.RIGHT)

        ttk.Label(right_opts, text="采集间隔(秒):").pack(side=tk.LEFT, padx=(10, 2))
        self.interval_var = tk.StringVar(value=str(self.config.get("interval_seconds", 7200)))
        interval_entry = ttk.Entry(right_opts, textvariable=self.interval_var, width=6)
        interval_entry.pack(side=tk.LEFT)
        interval_entry.bind("<FocusOut>", lambda e: self.save_interval())

    def build_config_panel(self, parent):
        """左侧配置面板"""
        canvas = tk.Canvas(parent, width=370, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 鼠标滚轮支持（仅当鼠标在canvas区域时）
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 航线设置 ──
        route_frame = ttk.LabelFrame(scroll_frame, text="✈ 航线设置", padding="8 5 8 5")
        route_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        grid_frame = ttk.Frame(route_frame)
        grid_frame.pack(fill=tk.X)

        ttk.Label(grid_frame, text="出发地代码:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.depart_var = tk.StringVar(value=self.config.get("depart", "BJS"))
        ttk.Entry(grid_frame, textvariable=self.depart_var, width=12).grid(row=0, column=1, sticky=tk.W, pady=3)

        ttk.Label(grid_frame, text="目的地代码:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.arrive_var = tk.StringVar(value=self.config.get("arrive", "URC"))
        ttk.Entry(grid_frame, textvariable=self.arrive_var, width=12).grid(row=1, column=1, sticky=tk.W, pady=3)

        date_frame = ttk.Frame(grid_frame)
        date_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(date_frame, text="出发日期:").pack(side=tk.LEFT)

        self.year_var = tk.StringVar(value=self.config.get("year", "2026"))
        self.month_var = tk.StringVar(value=self.config.get("month", "06"))
        self.day_var = tk.StringVar(value=self.config.get("day", "25"))

        ttk.Entry(date_frame, textvariable=self.year_var, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Label(date_frame, text="年").pack(side=tk.LEFT)
        ttk.Entry(date_frame, textvariable=self.month_var, width=3).pack(side=tk.LEFT, padx=1)
        ttk.Label(date_frame, text="月").pack(side=tk.LEFT)
        ttk.Entry(date_frame, textvariable=self.day_var, width=3).pack(side=tk.LEFT, padx=1)
        ttk.Label(date_frame, text="日").pack(side=tk.LEFT)

        self.headless_var = tk.BooleanVar(value=self.config.get("headless", True))
        ttk.Checkbutton(grid_frame, text="无头模式（后台运行浏览器）",
                        variable=self.headless_var,
                        command=self._toggle_headless).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=3)

        self.auto_save_excel_var = tk.BooleanVar(value=self.config.get("auto_save_excel", True))
        ttk.Checkbutton(grid_frame, text="每次采集后自动追加至Excel表",
                        variable=self.auto_save_excel_var,
                        command=self._toggle_auto_save_excel).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, pady=3)

        ttk.Button(route_frame, text="保存航线设置", command=self.save_route_config).pack(pady=(5, 0))

        # ── 数据源优先级 ──
        priority_frame = ttk.LabelFrame(scroll_frame, text="📋 数据源优先级（仅从最高有效源采集，失败时逐级降级）", padding="8 5 8 5")
        priority_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.priority_listbox = tk.Listbox(priority_frame, height=3, font=("Microsoft YaHei", 10),
                                           selectmode=tk.SINGLE, activestyle="none")
        self.priority_listbox.pack(fill=tk.X, pady=(0, 5))
        self._refresh_priority_listbox()

        btn_frame = ttk.Frame(priority_frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="▲ 上移", command=self.move_priority_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="▼ 下移", command=self.move_priority_down).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="保存优先级", command=self.save_priority).pack(side=tk.LEFT, padx=2)

        # ── 监控航班列表 ──
        flight_frame = ttk.LabelFrame(scroll_frame, text="🎯 监控航班（检测最低价并发邮件）", padding="8 5 8 5")
        flight_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.monitored_listbox = tk.Listbox(flight_frame, height=4, font=("Microsoft YaHei", 10))
        self.monitored_listbox.pack(fill=tk.X, pady=(0, 5))
        self._refresh_monitored_listbox()

        add_frame = ttk.Frame(flight_frame)
        add_frame.pack(fill=tk.X)
        self.new_flight_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_flight_var, width=12).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(add_frame, text="➕ 添加航班", command=self.add_monitored_flight).pack(side=tk.LEFT, padx=2)
        ttk.Button(add_frame, text="🗑 删除选中", command=self.remove_monitored_flight).pack(side=tk.LEFT, padx=2)

        # ── 邮件设置 ──
        email_frame = ttk.LabelFrame(scroll_frame, text="📧 邮件提醒设置 (SMTP)", padding="8 5 8 5")
        email_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        email = self.config.get("email", {})

        self.email_enabled_var = tk.BooleanVar(value=email.get("enabled", False))
        ttk.Checkbutton(email_frame, text="启用邮件提醒",
                        variable=self.email_enabled_var,
                        command=lambda: self._update_email_config("enabled")).pack(anchor=tk.W, pady=(0, 5))

        email_grid = ttk.Frame(email_frame)
        email_grid.pack(fill=tk.X)

        fields = [
            ("SMTP服务器:", "smtp_server", email.get("smtp_server", "smtp.qq.com")),
            ("SMTP端口:", "smtp_port", str(email.get("smtp_port", 587))),
            ("发件邮箱:", "username", email.get("username", "")),
            ("授权码/密码:", "password", email.get("password", ""), "*"),
            ("收件邮箱:", "recipient", email.get("recipient", "")),
        ]

        self.email_vars = {}
        for i, f in enumerate(fields):
            label, key, default, *rest = f
            show = rest[0] if rest else None
            ttk.Label(email_grid, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.email_vars[key] = var
            ttk.Entry(email_grid, textvariable=var, width=24, show=show).grid(row=i, column=1, sticky=tk.W, pady=2)

        ttk.Button(email_frame, text="保存邮件设置", command=self.save_email_config).pack(pady=(5, 0))

    def build_data_panel(self, parent):
        """右侧数据表格 + 日志区"""
        # 表格区域
        table_frame = ttk.LabelFrame(parent, text="📊 采集数据（双击行可查看详情）", padding="3 3 3 3")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=(0, 3))

        columns = ("采集时间", "航班号", "票价(¥)", "数据源")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)

        col_widths = [180, 120, 120, 100]
        for col, width in zip(columns, col_widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor=tk.CENTER)

        # 滚动条
        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 双击行弹窗详情
        self.tree.bind("<Double-1>", self.show_row_detail)

        # 日志区域
        log_frame = ttk.LabelFrame(parent, text="📝 运行日志", padding="3 3 3 3")
        log_frame.pack(fill=tk.BOTH, expand=False, padx=3, pady=(0, 3))

        self.log_area = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9), wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def build_status_bar(self):
        """底部状态栏"""
        status_frame = ttk.Frame(self.root, padding="3 3 3 3")
        status_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.status_label = ttk.Label(status_frame, text="● 就绪 | 等待操作", foreground="gray")
        self.status_label.pack(side=tk.LEFT)

        self.count_label = ttk.Label(status_frame, text="记录数: 0")
        self.count_label.pack(side=tk.RIGHT, padx=(10, 0))

        self.time_label = ttk.Label(status_frame, text="")
        self.time_label.pack(side=tk.RIGHT)

    # ── 配置面板辅助方法 ──────────────────────────────────────

    def _refresh_priority_listbox(self):
        self.priority_listbox.delete(0, tk.END)
        for src in self.config.get("priority", ["ctrip", "ly", "fliggy"]):
            name, _ = SOURCE_MAP.get(src, (src, "#000"))
            self.priority_listbox.insert(tk.END, f"  {name}  ({src})")

    def _refresh_monitored_listbox(self):
        self.monitored_listbox.delete(0, tk.END)
        for fn in self.config.get("monitored_flights", []):
            self.monitored_listbox.insert(tk.END, fn)

    def _toggle_headless(self):
        self.config["headless"] = self.headless_var.get()
        self.save_config()

    def _toggle_auto_save_excel(self):
        self.config["auto_save_excel"] = self.auto_save_excel_var.get()
        self.save_config()

    def _update_email_config(self, key):
        self.config.setdefault("email", {})[key] = self.email_enabled_var.get()
        self.save_config()

    def save_route_config(self):
        self.config["depart"] = self.depart_var.get().strip()
        self.config["arrive"] = self.arrive_var.get().strip()
        self.config["year"] = self.year_var.get().strip()
        self.config["month"] = self.month_var.get().strip()
        self.config["day"] = self.day_var.get().strip()
        self.save_config()
        self.log(f"航线设置已保存: {self.config['depart']} → {self.config['arrive']} ({self.config['year']}-{self.config['month']}-{self.config['day']})")

    def save_interval(self):
        try:
            val = int(self.interval_var.get())
            if val < 10:
                raise ValueError
            self.config["interval_seconds"] = val
            self.save_config()
            self.log(f"采集间隔已更新: {val}秒")
        except ValueError:
            self.interval_var.set(str(self.config.get("interval_seconds", 7200)))

    def save_priority(self):
        """保存数据源优先级"""
        current_items = list(self.priority_listbox.get(0, tk.END))
        priority = []
        for item in current_items:
            # 提取括号内的source key
            if "(" in item and ")" in item:
                src = item.split("(")[-1].split(")")[0].strip()
                priority.append(src)
        if len(priority) >= 3:
            self.config["priority"] = priority
            self.save_config()
            self.log(f"数据源优先级已保存: {' → '.join(priority)}")
        else:
            messagebox.showwarning("警告", "请保留全部3个数据源")

    def move_priority_up(self):
        sel = self.priority_listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            item = self.priority_listbox.get(idx)
            self.priority_listbox.delete(idx)
            self.priority_listbox.insert(idx - 1, item)
            self.priority_listbox.selection_set(idx - 1)

    def move_priority_down(self):
        sel = self.priority_listbox.curselection()
        if sel and int(sel[0]) < self.priority_listbox.size() - 1:
            idx = sel[0]
            item = self.priority_listbox.get(idx)
            self.priority_listbox.delete(idx)
            self.priority_listbox.insert(idx + 1, item)
            self.priority_listbox.selection_set(idx + 1)

    def add_monitored_flight(self):
        fn = self.new_flight_var.get().strip().upper()
        if not fn:
            return
        if fn in self.config.get("monitored_flights", []):
            messagebox.showinfo("提示", f"航班 {fn} 已在监控列表中")
            return
        self.config.setdefault("monitored_flights", []).append(fn)
        self._refresh_monitored_listbox()
        self.save_config()
        self.new_flight_var.set("")
        self.log(f"已添加监控航班: {fn}")

    def remove_monitored_flight(self):
        sel = self.monitored_listbox.curselection()
        if sel:
            fn = self.monitored_listbox.get(sel[0])
            self.config["monitored_flights"].remove(fn)
            self._refresh_monitored_listbox()
            self.save_config()
            self.log(f"已移除监控航班: {fn}")

    def save_email_config(self):
        email = self.config.setdefault("email", {})
        email["enabled"] = self.email_enabled_var.get()
        for key, var in self.email_vars.items():
            if key == "smtp_port":
                email[key] = int(var.get())
            else:
                email[key] = var.get().strip()
        self.save_config()
        self.log("邮件设置已保存")

    # ── 数据采集 ──────────────────────────────────────────────

    def fetch_from_best_source(self):
        """按优先级降级采集：从最高优先级数据源尝试，成功则停止，失败则降级到下一源"""
        priority = self.config.get("priority", ["ctrip", "ly", "fliggy"])

        fetch_funcs = {
            "ctrip": process_data.ctrip,
            "ly": process_data.ly,
            "fliggy": process_data.fliggy,
            "csair": process_data.csair,
            "ceair": process_data.ceair,
        }

        for src in priority:
            name, _ = SOURCE_MAP.get(src, (src, "#000"))
            try:
                self.log(f"正在从 {name} 采集数据...")
                data = fetch_funcs[src]()
                # 给每条记录加上数据源标记
                for item in data:
                    item["source"] = src
                if data:
                    self.log(f"  ✓ {name} 采集成功，获取 {len(data)} 条航班数据")
                    return data
                else:
                    self.log(f"  ⚠ {name} 返回空数据，尝试下一个数据源...")
            except Exception as e:
                self.log(f"  ✗ {name} 采集失败: {e}，尝试下一个数据源...")

        self.log("  ✗ 所有数据源均采集失败")
        return []

    def process_and_record(self, data_list):
        """处理数据并记录到表格，同时检测最低价"""
        if not data_list:
            self.log("无数据可记录")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_lows = []  # 本次采集中的新低航班

        for item in data_list:
            flight_no = item.get("flightNo", "?")
            price = int(item.get("price", 0))
            source = item.get("source", "?")

            # 记录到内存
            record = {
                "time": current_time,
                "flightNo": flight_no,
                "price": price,
                "source": source,
            }
            self.all_records.append(record)

            # 更新最低价记录
            prev = self.price_lowest.get(flight_no)
            if prev is None or int(price) < int(prev["price"]):
                self.price_lowest[flight_no] = {
                    "price": price,
                    "source": source,
                    "time": current_time,
                }
                # 如果在监控列表中，标记为新低
                if flight_no in self.config.get("monitored_flights", []):
                    new_lows.append(record)

            # 插入表格
            src_name, _ = SOURCE_MAP.get(source, (source, "#000"))
            self.tree.insert("", tk.END, values=(current_time, flight_no, f"¥{price}", src_name))

        # 更新状态栏
        self.count_label.config(text=f"记录数: {len(self.all_records)}")
        self.time_label.config(text=f"最近采集: {current_time}")

        # 自动保存到Excel（追加模式，可由选项控制）
        if self.config.get("auto_save_excel", True):
            self.save_flights_to_excel(data_list, current_time)

        # 检测到监控航班新低 → 发邮件
        if new_lows:
            self.log(f"🎉 检测到 {len(new_lows)} 个监控航班创历史新低!")
            for r in new_lows:
                self.log(f"  → {r['flightNo']}: ¥{r['price']} (来源: {SOURCE_MAP.get(r['source'], (r['source'],))[0]})")
            self.send_low_price_alert(new_lows)

    def load_history(self):
        """加载已有历史数据到表格（从内存数据文件恢复）"""
        history_file = os.path.join(OUTPUT_DIR, "history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                for r in records:
                    self.all_records.append(r)
                    src_name, _ = SOURCE_MAP.get(r.get("source", "?"), (r.get("source", "?"), "#000"))
                    self.tree.insert("", tk.END, values=(r["time"], r["flightNo"], f"¥{r['price']}", src_name))
                    # 更新最低价
                    fn = r["flightNo"]
                    prev = self.price_lowest.get(fn)
                    if prev is None or int(r["price"]) < int(prev["price"]):
                        self.price_lowest[fn] = {"price": int(r["price"]), "source": r["source"], "time": r["time"]}
                self.count_label.config(text=f"记录数: {len(self.all_records)}")
            except Exception as e:
                self.log(f"加载历史数据失败: {e}")

    def save_flights_to_excel(self, data_list, current_time):
        """
        将本次采集数据追加到Excel文件。
        格式：首列=采集时间, 第二列=数据源, 后续每列=一个航班的价格
        文件命名: flight_<depart>to<arrive>_<year><month><day>.xlsx
        """
        import pandas as pd

        # 提取数据源（同一次采集所有数据来自同一源）
        source = data_list[0].get("source", "?") if data_list else "?"
        src_name, _ = SOURCE_MAP.get(source, (source, "#000"))

        # 构建行数据: {'采集时间': ..., '数据源': ..., 'CZ6903': 1990, ...}
        row_data = {"采集时间": current_time, "数据源": src_name}
        for item in data_list:
            row_data[item["flightNo"]] = item["price"]

        df_new = pd.DataFrame([row_data])

        # 生成文件名
        depart = self.config.get("depart", "XXX")
        arrive = self.config.get("arrive", "XXX")
        year = self.config.get("year", "2026")
        month = self.config.get("month", "01")
        day = self.config.get("day", "01")
        file_name = os.path.join(OUTPUT_DIR, f"flight_{depart}_to_{arrive}_{year}{month}{day}.xlsx")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        try:
            if not os.path.exists(file_name):
                df_new.to_excel(file_name, index=False)
                self.log(f"Excel文件已创建: {os.path.basename(file_name)}")
            else:
                df_old = pd.read_excel(file_name)
                df_final = pd.concat([df_old, df_new], ignore_index=True)
                df_final.to_excel(file_name, index=False)
                self.log(f"Excel数据已追加: {os.path.basename(file_name)}")
        except Exception as e:
            self.log(f"Excel保存失败: {e}")

    def save_history(self):
        """保存数据到JSON文件"""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        history_file = os.path.join(OUTPUT_DIR, "history.json")
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self.all_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存历史数据失败: {e}")

    # ── 最低价邮件提醒 ────────────────────────────────────────

    def send_low_price_alert(self, new_lows):
        """发送新低票价邮件提醒"""
        email_config = self.config.get("email", {})
        if not email_config.get("enabled", False):
            self.log("邮件提醒未启用，跳过发送")
            return

        if not all([email_config.get("smtp_server"), email_config.get("username"),
                     email_config.get("password"), email_config.get("recipient")]):
            self.log("邮件配置不完整，跳过发送")
            return

        # 在后台线程发送邮件
        def _send():
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"✈ 机票最低价提醒 - {len(new_lows)}个航班创历史新低"
                msg["From"] = email_config["username"]
                msg["To"] = email_config["recipient"]

                # 构建HTML邮件内容
                rows_html = ""
                for r in new_lows:
                    src_name, _ = SOURCE_MAP.get(r["source"], (r["source"], "#000"))
                    rows_html += f"""
                    <tr>
                        <td style="padding:8px;border:1px solid #ddd;">{r['flightNo']}</td>
                        <td style="padding:8px;border:1px solid #ddd;color:#e74c3c;font-weight:bold;">¥{r['price']}</td>
                        <td style="padding:8px;border:1px solid #ddd;">{src_name}</td>
                        <td style="padding:8px;border:1px solid #ddd;">{r['time']}</td>
                    </tr>"""

                html = f"""
                <html>
                <body style="font-family:'Microsoft YaHei',Arial,sans-serif;padding:20px;">
                    <h2 style="color:#e74c3c;">🎉 机票最低价提醒</h2>
                    <p>以下航班票价创历史新低，建议立即关注：</p>
                    <table style="border-collapse:collapse;width:100%;max-width:600px;">
                        <tr style="background:#f5f5f5;">
                            <th style="padding:8px;border:1px solid #ddd;">航班号</th>
                            <th style="padding:8px;border:1px solid #ddd;">最低票价</th>
                            <th style="padding:8px;border:1px solid #ddd;">数据源</th>
                            <th style="padding:8px;border:1px solid #ddd;">采集时间</th>
                        </tr>
                        {rows_html}
                    </table>
                    <p style="color:#888;margin-top:20px;">航线程: {self.config.get('depart')} → {self.config.get('arrive')}</p>
                    <p style="color:#888;">出发日期: {self.config.get('year')}-{self.config.get('month')}-{self.config.get('day')}</p>
                    <p style="color:#aaa;font-size:12px;">此邮件由机票监控系统自动发送</p>
                </body>
                </html>
                """

                msg.attach(MIMEText(html, "html", "utf-8"))

                server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"], timeout=30)
                server.starttls()
                server.login(email_config["username"], email_config["password"])
                server.sendmail(email_config["username"], email_config["recipient"], msg.as_string())
                server.quit()

                self.root.after(0, lambda: self.log(f"📧 邮件已发送至 {email_config['recipient']}"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"邮件发送失败: {e}"))

        t = threading.Thread(target=_send, daemon=True)
        t.start()

    # ── 监控循环 ──────────────────────────────────────────────

    def monitoring_loop(self):
        """后台监控循环"""
        interval = self.config.get("interval_seconds", 7200)
        self.log(f"监控已启动，间隔 {interval} 秒")

        while not self.stop_event.is_set():
            try:
                self.root.after(0, lambda: self.status_label.config(
                    text="● 采集中...", foreground="orange"))
                data = self.fetch_from_best_source()
                self.root.after(0, lambda d=data: self.process_and_record(d))
                self.root.after(0, self.save_history)
                self.root.after(0, lambda: self.status_label.config(
                    text=f"● 监控中 | 下次采集: {interval}秒后", foreground="green"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"监控循环异常: {e}"))
                self.root.after(0, lambda: self.status_label.config(
                    text="● 异常 | 等待重试...", foreground="red"))

            # 分段等待，以便能响应停止事件
            for _ in range(interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

        self.root.after(0, lambda: self.status_label.config(text="● 已停止", foreground="gray"))

    def start_monitoring(self):
        """开始后台监控"""
        if self.monitoring:
            return
        self.monitoring = True
        self.stop_event.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_fetch.config(state=tk.DISABLED)
        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """停止后台监控"""
        self.monitoring = False
        self.stop_event.set()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_fetch.config(state=tk.NORMAL)
        self.log("监控已停止")

    def manual_fetch(self):
        """手动采集一次"""
        self.btn_fetch.config(state=tk.DISABLED, text="采集中...")
        self.status_label.config(text="● 手动采集中...", foreground="orange")

        def _fetch():
            try:
                data = self.fetch_from_best_source()
                self.root.after(0, lambda d=data: self.process_and_record(d))
                self.root.after(0, self.save_history)
            except Exception as e:
                self.root.after(0, lambda: self.log(f"手动采集异常: {e}"))
            finally:
                self.root.after(0, lambda: self.btn_fetch.config(state=tk.NORMAL, text="▶ 立即采集"))
                self.root.after(0, lambda: self.status_label.config(text="● 就绪", foreground="gray"))

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

    # ── 表格操作 ──────────────────────────────────────────────

    def clear_table(self):
        if messagebox.askyesno("确认", "确定要清空所有采集数据吗？此操作不可恢复。"):
            self.tree.delete(*self.tree.get_children())
            self.all_records.clear()
            self.price_lowest.clear()
            self.count_label.config(text="记录数: 0")
            self.save_history()
            self.log("表格数据已清空")

    def export_excel(self):
        """导出全部历史数据到Excel（宽表格式：采集时间+数据源+各航班列）"""
        import pandas as pd

        if not self.all_records:
            messagebox.showinfo("提示", "无数据可导出")
            return

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        depart = self.config.get("depart", "XXX")
        arrive = self.config.get("arrive", "XXX")
        year = self.config.get("year", "2026")
        month = self.config.get("month", "01")
        day = self.config.get("day", "01")
        file_path = os.path.join(
            OUTPUT_DIR,
            f"flight_{depart}_to_{arrive}_{year}{month}{day}_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )

        try:
            # 将长表 pivoted 为宽表: 每行=一次采集, 每列=一个航班
            df = pd.DataFrame(self.all_records)
            df["数据源名称"] = df["source"].map(lambda s: SOURCE_MAP.get(s, (s,))[0])

            # 按 (采集时间, 数据源) 分组，pivot 航班号为列
            pivoted = df.pivot_table(
                index=["time", "数据源名称"],
                columns="flightNo",
                values="price",
                aggfunc="first",
            ).reset_index()

            # 重命名列
            pivoted.columns.name = None
            pivoted.rename(columns={"time": "采集时间", "数据源名称": "数据源"}, inplace=True)

            pivoted.to_excel(file_path, index=False)
            self.log(f"全部数据已导出: {os.path.basename(file_path)}")
            messagebox.showinfo("导出成功", f"数据已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def show_row_detail(self, event):
        """双击表格行查看详情"""
        selection = self.tree.selection()
        if selection:
            values = self.tree.item(selection[0], "values")
            detail = f"采集时间: {values[0]}\n航班号: {values[1]}\n票价: {values[2]}\n数据源: {values[3]}"
            messagebox.showinfo("记录详情", detail)

    # ── 日志 ────────────────────────────────────────────────────

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_area.see(tk.END)

    # ── 关闭 ────────────────────────────────────────────────────

    def on_close(self):
        if self.monitoring:
            if messagebox.askyesno("确认", "监控正在运行中，确定要退出吗？"):
                self.stop_monitoring()
                self.save_history()
                self.root.destroy()
        else:
            self.save_history()
            self.root.destroy()


# ── 程序入口 ──────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = AirfareMonitorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
