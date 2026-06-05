import tkinter as tk
from tkinter import messagebox
import threading
import subprocess
import time
import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright


CDP_URL = "http://localhost:9222"
TARGET_URL = "https://platform.xiaomimimo.com/console/plan-manage"
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(records):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def check_cdp_available():
    """检查 Edge CDP 调试端口是否可用"""
    import urllib.request
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2)
        return True
    except Exception:
        return False


def check_target_page_open():
    """检查目标页面是否已打开"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            for ctx in browser.contexts:
                for page in ctx.pages:
                    if "xiaomimimo.com" in page.url:
                        return True
            return False
    except Exception:
        return False


def ensure_edge_running():
    """确保 Edge 运行并打开目标页面"""
    import urllib.request

    # 如果 Edge 未运行，直接启动并打开目标页面
    if not check_cdp_available():
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        local_app = os.environ.get("LOCALAPPDATA", "")
        user_data = os.path.join(local_app, "Microsoft", "Edge", "User Data")
        try:
            subprocess.Popen([
                edge_path,
                f"--remote-debugging-port=9222",
                f"--user-data-dir={user_data}",
                TARGET_URL,
            ])
            time.sleep(3)
        except Exception:
            return False

    # 检查目标页面是否已打开，未打开则在新标签页打开
    if not check_target_page_open():
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        except Exception:
            return False

    return True


def scrape_token_value(refresh=False):
    # 确保 Edge 运行并打开目标页面
    ensure_edge_running()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        contexts = browser.contexts
        if not contexts:
            raise Exception("未找到浏览器上下文，请确认 Edge 已打开")

        target_page = None
        for ctx in contexts:
            for page in ctx.pages:
                if "xiaomimimo.com" in page.url:
                    target_page = page
                    break
            if target_page:
                break

        if not target_page:
            raise Exception("未找到 MiMo 控制台页面，请在 Edge 中打开:\n" + TARGET_URL)

        if refresh:
            target_page.reload(wait_until="networkidle", timeout=30000)

        selector = '[class*="usageFigure"]'
        target_page.wait_for_selector(selector, timeout=10000)
        element = target_page.locator(selector).first
        text = element.get_attribute("title") or element.inner_text()

        part = text.split("/")[0].strip()
        value = int(part.replace(",", "").replace(" ", ""))

        return value


class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class TokenTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("API Token 消耗追踪器")
        self.root.geometry("520x520")
        self.root.minsize(400, 350)

        self.start_value = None
        self.font_size = 9
        self.rows = []
        self.display_to_record = []

        # ── 顶部控制区 ──
        top = tk.Frame(root)
        top.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Label(top, text="API Token 消耗追踪器", font=("Microsoft YaHei", 14, "bold")).pack()

        self.status_var = tk.StringVar(value="状态: 空闲")
        tk.Label(top, textvariable=self.status_var, font=("Microsoft YaHei", 9)).pack(pady=2)

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=4)

        self.btn_start = tk.Button(
            btn_frame, text="开始记录", width=10, height=2,
            font=("Microsoft YaHei", 9), command=self.on_start
        )
        self.btn_start.pack(side=tk.LEFT, padx=4)

        self.btn_stop = tk.Button(
            btn_frame, text="结束记录", width=10, height=2,
            font=("Microsoft YaHei", 9), command=self.on_stop, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        self.btn_oneclick = tk.Button(
            btn_frame, text="一键记录", width=10, height=2,
            font=("Microsoft YaHei", 9), command=self.on_oneclick
        )
        self.btn_oneclick.pack(side=tk.LEFT, padx=4)

        tk.Label(top, text="══════ 本次消耗 ══════", font=("Microsoft YaHei", 9)).pack(pady=(5, 2))
        self.result_var = tk.StringVar(value="token 消耗: —")
        tk.Label(top, textvariable=self.result_var, font=("Microsoft YaHei", 11)).pack(pady=2)

        # ── 历史记录区标题栏 ──
        hist_header = tk.Frame(root)
        hist_header.pack(fill=tk.X, padx=10, pady=(8, 2))

        tk.Label(hist_header, text="══════ 历史记录 ══════", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)

        tk.Button(hist_header, text="A+", width=3, font=("Microsoft YaHei", 8),
                  command=lambda: self._change_font(1)).pack(side=tk.RIGHT, padx=1)
        tk.Button(hist_header, text="A-", width=3, font=("Microsoft YaHei", 8),
                  command=lambda: self._change_font(-1)).pack(side=tk.RIGHT, padx=1)
        tk.Button(hist_header, text="删除选中", font=("Microsoft YaHei", 8),
                  command=self._delete_selected).pack(side=tk.RIGHT, padx=4)

        # ── 可滚动历史列表 ──
        self.scroll_frame = ScrollableFrame(root)
        self.scroll_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        self._refresh_list()

    def _get_font(self):
        return ("Consolas", self.font_size)

    def _change_font(self, delta):
        self.font_size = max(7, min(20, self.font_size + delta))
        self._refresh_list()

    def _refresh_list(self):
        for row in self.rows:
            row[0].destroy()
        self.rows.clear()
        self.display_to_record.clear()

        records = load_history()
        font = self._get_font()

        order = list(reversed(range(len(records))))
        for display_idx, record_idx in enumerate(order):
            r = records[record_idx]
            self.display_to_record.append(record_idx)

            row_frame = tk.Frame(self.scroll_frame.inner)
            row_frame.pack(fill=tk.X, pady=1)

            var = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(row_frame, variable=var, font=font)
            cb.pack(side=tk.LEFT)

            note = r.get("note", "")
            note_part = f"  [{note}]" if note else ""
            label_text = f"{r['time']}  消耗:{r['consumed']:,}{note_part}"
            lbl = tk.Label(row_frame, text=label_text, font=font, anchor="w")
            lbl.pack(side=tk.LEFT, padx=(2, 5))

            entry = tk.Entry(row_frame, font=font, width=18)
            entry.pack(side=tk.RIGHT, padx=(2, 4))
            if note:
                entry.insert(0, note)

            save_btn = tk.Button(row_frame, text="✓", font=("Microsoft YaHei", 7),
                                 width=2, command=lambda idx=record_idx, e=entry: self._save_note(idx, e))
            save_btn.pack(side=tk.RIGHT, padx=1)

            self.rows.append((row_frame, var, entry, save_btn))

    def _save_note(self, idx, entry):
        records = load_history()
        if idx >= len(records):
            return
        records[idx]["note"] = entry.get().strip()
        save_history(records)

    def _delete_selected(self):
        records = load_history()
        to_delete = []
        for display_idx, (_, var, _, _) in enumerate(self.rows):
            if var.get():
                to_delete.append(self.display_to_record[display_idx])
        if not to_delete:
            messagebox.showinfo("提示", "请先勾选要删除的记录")
            return
        if not messagebox.askyesno("确认", f"确定删除 {len(to_delete)} 条记录？"):
            return
        for i in sorted(set(to_delete), reverse=True):
            if i < len(records):
                records.pop(i)
        save_history(records)
        self._refresh_list()

    # ── 抓取逻辑 ──
    def on_start(self):
        self.btn_start.config(state=tk.DISABLED)
        self.status_var.set("状态: 正在连接...")
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        try:
            value = scrape_token_value(refresh=False)
            self.start_value = value
            self.root.after(0, lambda: self.status_var.set(f"状态: 已记录起点 ({value:,})"))
            self.root.after(0, lambda: self.btn_stop.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.result_var.set("token 消耗: —"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.status_var.set("状态: 连接失败"))

    def on_stop(self):
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("状态: 正在刷新页面并抓取...")
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        try:
            end_value = scrape_token_value(refresh=True)
            consumed = end_value - self.start_value

            record = {
                "id": int(time.time() * 1000),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "start": self.start_value,
                "end": end_value,
                "consumed": consumed,
                "note": "",
            }
            records = load_history()
            records.append(record)
            save_history(records)

            self.root.after(0, lambda: self.result_var.set(f"token 消耗: {consumed:,}"))
            self.root.after(0, lambda: self.status_var.set(
                f"状态: 已完成 ({self.start_value:,} → {end_value:,})"
            ))
            self.root.after(0, self._refresh_list)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))

    def on_oneclick(self):
        self.btn_oneclick.config(state=tk.DISABLED)
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("状态: 正在一键记录...")
        threading.Thread(target=self._do_oneclick, daemon=True).start()

    def _do_oneclick(self):
        try:
            if self.start_value is None:
                self.start_value = scrape_token_value(refresh=False)
                self.root.after(0, lambda: self.status_var.set("状态: 已获取起点，正在刷新..."))

            end_value = scrape_token_value(refresh=True)
            consumed = end_value - self.start_value

            record = {
                "id": int(time.time() * 1000),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "start": self.start_value,
                "end": end_value,
                "consumed": consumed,
                "note": "",
            }
            records = load_history()
            records.append(record)
            save_history(records)

            self.start_value = None
            self.root.after(0, lambda: self.result_var.set(f"token 消耗: {consumed:,}"))
            self.root.after(0, lambda: self.status_var.set(
                f"状态: 一键完成 ({record['start']:,} → {end_value:,})"
            ))
            self.root.after(0, self._refresh_list)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.btn_oneclick.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))


def main():
    root = tk.Tk()
    TokenTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
