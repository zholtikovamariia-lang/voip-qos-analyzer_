import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

DELAY_IDEAL   = 150
DELAY_LIMIT   = 400

IE_G711  = 0
IE_G729  = 11
IE_G722  = 0
IE_OPUS  = 5
BPL      = 25

MOS_EXCELLENT = 4.0
MOS_GOOD      = 3.5
MOS_FAIR      = 2.5
MOS_POOR      = 1.5

COLORS = {
    "Відмінно":   "#2ecc71",
    "Добре":      "#27ae60",
    "Задовільно": "#f39c12",
    "Погано":     "#e74c3c",
    "Жахливо":    "#922b21",
}

CODECS = {
    "G.711": (IE_G711, 64), 
    "G.729": (IE_G729, 8),
    "G.722": (IE_G722, 48),
    "OPUS":  (IE_OPUS, 32),
}

def calc_id(delay_ms):
    d = delay_ms
    heaviside = max(0, d - 177.3)
    return 0.024 * d + 0.11 * heaviside

def calc_ie_eff(ie, loss_percent):
    if loss_percent <= 0:
        return ie
    return ie + (95 - ie) * loss_percent / (loss_percent + BPL)

def calc_r_factor(delay_ms, jitter_ms, loss_percent, codec):
    ie, _ = CODECS.get(codec.upper(), (IE_G711, 64))

    id_val    = calc_id(delay_ms + jitter_ms * 0.5)
    ie_eff    = calc_ie_eff(ie, loss_percent)

    r = 93.2 - id_val - ie_eff
    return max(0.0, min(100.0, r))

def r_to_mos(r):
    if r <= 0:
        return 1.0
    if r >= 100:
        return 4.5
    mos = 1 + 0.035 * r + r * (r - 60) * (100 - r) * 7e-6
    return round(max(1.0, min(4.5, mos)), 2)

def calculate_mos(delay_ms, jitter_ms, loss_percent, codec):
    r = calc_r_factor(delay_ms, jitter_ms, loss_percent, codec)
    return r_to_mos(r)

def get_quality(mos):
    if mos >= MOS_EXCELLENT:
        return "Відмінно",   COLORS["Відмінно"]
    elif mos >= MOS_GOOD:
        return "Добре",      COLORS["Добре"]
    elif mos >= MOS_FAIR:
        return "Задовільно", COLORS["Задовільно"]
    elif mos >= MOS_POOR:
        return "Погано",     COLORS["Погано"]
    else:
        return "Жахливо",    COLORS["Жахливо"]

def get_recommendation(call):
    tips = []
    if call["delay_ms"] > DELAY_IDEAL:
        tips.append(f"Затримка {call['delay_ms']:.0f}мс перевищує норму (150мс) — перевірте маршрутизацію")
    if call["jitter_ms"] > 30:
        tips.append(f"Джиттер {call['jitter_ms']:.0f}мс > 30мс — налаштуйте dejitter-буфер")
    if call["loss_percent"] > 1:
        tips.append(f"Втрати {call['loss_percent']:.1f}% > 1% — перевірте навантаження каналу")
    return " | ".join(tips) if tips else "Параметри в нормі ✓"

def generate_test_csv(filename="voip_calls.csv"):
    rows = [
        ["id", "delay_ms", "jitter_ms", "loss_percent", "codec"],
        [1,  45,  5,  0.1, "G.711"],
        [2,  80,  8,  0.3, "G.711"],
        [3,  120, 10, 0.5, "G.722"],
        [4,  160, 12, 1.2, "G.711"],
        [5,  50,  6,  0.2, "G.729"],
        [6,  200, 18, 2.0, "G.729"],
        [7,  250, 25, 2.8, "G.711"],
        [8,  180, 38, 1.5, "OPUS"],
        [9,  300, 20, 3.5, "G.729"],
        [10, 270, 42, 5.0, "G.711"],
        [11, 90,  9,  0.4, "OPUS"],
        [12, 350, 50, 8.0, "G.711"],
        [13, 95,  7,  0.2, "G.722"],
        [14, 220, 22, 3.8, "G.729"],
        [15, 150, 11, 1.0, "G.711"],
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return filename

class VoIPQoSAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("VoIP QoS Analyzer")
        self.root.geometry("1000x640")

        self.data     = []
        self.filename = None
        self.sort_col = None
        self.sort_asc = True

        self._build_ui()
        self._startup_dialog()

    def _build_ui(self):
        filter_frame = tk.LabelFrame(self.root, text=" Фільтр та сортування ", font=("Arial", 9))
        filter_frame.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Label(filter_frame, text="Кодек:").pack(side=tk.LEFT, padx=(8, 2))
        self.filter_codec = ttk.Combobox(filter_frame, values=["Усі", "G.711", "G.729", "G.722", "OPUS"],
                                         width=8, state="readonly")
        self.filter_codec.set("Усі")
        self.filter_codec.pack(side=tk.LEFT, padx=(0, 10))
        self.filter_codec.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        tk.Label(filter_frame, text="Якість:").pack(side=tk.LEFT, padx=(0, 2))
        self.filter_quality = ttk.Combobox(filter_frame,
                                           values=["Усі", "Відмінно", "Добре", "Задовільно", "Погано", "Жахливо"],
                                           width=12, state="readonly")
        self.filter_quality.set("Усі")
        self.filter_quality.pack(side=tk.LEFT, padx=(0, 10))
        self.filter_quality.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        tk.Button(filter_frame, text="✖ Скинути", command=self._reset_filter).pack(side=tk.LEFT)

        cols = ("ID", "Затримка (мс)", "Джиттер (мс)", "Втрати (%)", "Кодек", "MOS", "Якість")
        table_frame = tk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=14)
        widths = [45, 120, 115, 95, 75, 75, 110]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor="center")

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<ButtonRelease-1>", self._on_row_click)

        self.detail_var = tk.StringVar(value="↑ Оберіть рядок для деталей")
        detail = tk.Label(self.root, textvariable=self.detail_var, anchor="w",
                          font=("Courier", 9), relief=tk.GROOVE, bd=1)
        detail.pack(fill=tk.X, padx=10, pady=(0, 4))

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        buttons = [
            ("📂 Відкрити файл",    self._open_file),
            ("🔄 Перерахувати MOS", self._recalculate),
            ("💾 Зберегти звіт",   self._save_report),
            ("📊 Статистика",      self._show_stats),
            ("📈 Графіки",         self._show_charts),
        ]
        for text, cmd in buttons:
            tk.Button(btn_frame, text=text, command=cmd, width=16).pack(side=tk.LEFT, padx=4)

    def _startup_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Вітання")
        dlg.geometry("380x210")
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="VoIP QoS Analyzer", font=("Arial", 15, "bold")).pack(pady=12)
        tk.Label(dlg, text="Аналізатор якості голосу в IP-мережах", font=("Arial", 10)).pack()

        def load_test():
            self._load_file(generate_test_csv())
            dlg.destroy()

        def open_own():
            dlg.destroy()
            self._open_file()

        tk.Button(dlg, text="📁 Завантажити тестові дані", command=load_test,
                  width=28, height=2).pack(pady=6)
        tk.Button(dlg, text="📂 Відкрити власний CSV-файл", command=open_own,
                  width=28, height=2).pack()

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Оберіть CSV-файл",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self._load_file(path)

    def _load_file(self, filename):
        self.filename = filename
        self.data = []
        errors = 0

        try:
            with open(filename, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        call = {
                            "id":           int(row["id"]),
                            "delay_ms":     float(row["delay_ms"]),
                            "jitter_ms":    float(row["jitter_ms"]),
                            "loss_percent": float(row["loss_percent"]),
                            "codec":        row["codec"].strip().upper(),
                        }
                        call["mos"]              = calculate_mos(**{k: call[k] for k in
                                                    ["delay_ms", "jitter_ms", "loss_percent", "codec"]})
                        call["quality"], call["color"] = get_quality(call["mos"])
                        self.data.append(call)
                    except (ValueError, KeyError):
                        errors += 1

            self._refresh_table(self.data)
            self.root.title(f"VoIP QoS Analyzer — {os.path.basename(filename)}")
            msg = f"Завантажено {len(self.data)} дзвінків."
            if errors:
                msg += f"\n⚠ Пропущено рядків з помилками: {errors}"
            messagebox.showinfo("Файл завантажено", msg)

        except Exception as e:
            messagebox.showerror("Помилка читання файлу", str(e))

    def _save_report(self):
        if not self.data:
            messagebox.showwarning("Попередження", "Немає даних для збереження")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")]
        )
        if not path:
            return
        try:
            mos_vals = [c["mos"] for c in self.data]
            cats = {}
            for c in self.data:
                cats[c["quality"]] = cats.get(c["quality"], 0) + 1

            with open(path, "w", encoding="utf-8") as f:
                sep = "═" * 68
                f.write(f"{sep}\n  ЗВІТ АНАЛІЗУ ЯКОСТІ VoIP (QoS) — E-model ITU-T G.107\n{sep}\n\n")
                f.write(f"Файл даних : {self.filename}\n")
                f.write(f"Дзвінків   : {len(self.data)}\n\n")
                f.write(f"{'ID':>4}  {'Затримка':>10}  {'Джиттер':>9}  {'Втрати':>8}  "
                        f"{'Кодек':>6}  {'MOS':>6}  Якість\n")
                f.write("─" * 68 + "\n")
                for c in self.data:
                    f.write(f"{c['id']:>4}  {c['delay_ms']:>9.1f}м  {c['jitter_ms']:>8.1f}м  "
                            f"{c['loss_percent']:>7.2f}%  {c['codec']:>6}  {c['mos']:>6.2f}  {c['quality']}\n")
                f.write("─" * 68 + "\n\n")
                f.write(f"Середній MOS : {sum(mos_vals)/len(mos_vals):.2f}\n")
                f.write(f"Макс. MOS    : {max(mos_vals):.2f}\n")
                f.write(f"Мін. MOS     : {min(mos_vals):.2f}\n\n")
                f.write("Розподіл за якістю:\n")
                for cat, cnt in cats.items():
                    f.write(f"  {cat:12} — {cnt} ({cnt/len(self.data)*100:.1f}%)\n")

            messagebox.showinfo("Збережено", f"Звіт збережено:\n{path}")
        except Exception as e:
            messagebox.showerror("Помилка запису", str(e))

    def _refresh_table(self, dataset):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for c in dataset:
            tag = f"q_{c['id']}"
            self.tree.tag_configure(tag, background=c["color"])
            self.tree.insert("", tk.END, tags=(tag,), values=(
                c["id"],
                f"{c['delay_ms']:.1f}",
                f"{c['jitter_ms']:.1f}",
                f"{c['loss_percent']:.2f}",
                c["codec"],
                f"{c['mos']:.2f}",
                c["quality"],
            ))

    def _sort_by(self, col):
        key_map = {
            "ID": "id", "Затримка (мс)": "delay_ms", "Джиттер (мс)": "jitter_ms",
            "Втрати (%)": "loss_percent", "Кодек": "codec", "MOS": "mos", "Якість": "quality"
        }
        key = key_map.get(col, "id")
        if self.sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col, self.sort_asc = col, True
        visible = self._filtered_data()
        visible.sort(key=lambda x: x[key], reverse=not self.sort_asc)
        self._refresh_table(visible)

    def _apply_filter(self):
        self._refresh_table(self._filtered_data())

    def _reset_filter(self):
        self.filter_codec.set("Усі")
        self.filter_quality.set("Усі")
        self._refresh_table(self.data)

    def _filtered_data(self):
        codec   = self.filter_codec.get()
        quality = self.filter_quality.get()
        result  = self.data
        if codec != "Усі":
            result = [c for c in result if c["codec"] == codec]
        if quality != "Усі":
            result = [c for c in result if c["quality"] == quality]
        return result

    def _on_row_click(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        call_id = int(self.tree.item(sel[0], "values")[0])
        call = next((c for c in self.data if c["id"] == call_id), None)
        if call:
            self.detail_var.set(
                f"  #{call['id']}  |  Затримка: {call['delay_ms']:.1f}мс  "
                f"Джиттер: {call['jitter_ms']:.1f}мс  Втрати: {call['loss_percent']:.2f}%  "
                f"Кодек: {call['codec']}  MOS: {call['mos']:.2f}  [{call['quality']}]  "
                f"→ {get_recommendation(call)}"
            )

    def _recalculate(self):
        for c in self.data:
            c["mos"] = calculate_mos(c["delay_ms"], c["jitter_ms"], c["loss_percent"], c["codec"])
            c["quality"], c["color"] = get_quality(c["mos"])
        self._refresh_table(self.data)
        messagebox.showinfo("Готово", "MOS перераховано для всіх дзвінків")

    def _show_stats(self):
        if not self.data:
            messagebox.showwarning("Попередження", "Немає даних")
            return
        win = tk.Toplevel(self.root)
        win.title("Статистика QoS")
        win.geometry("480x360")
        win.transient(self.root)

        mos  = [c["mos"] for c in self.data]
        cats = {}
        for c in self.data:
            cats[c["quality"]] = cats.get(c["quality"], 0) + 1

        flags = []
        if max(c["delay_ms"] for c in self.data) > DELAY_IDEAL:
            flags.append("Є дзвінки із затримкою понад 150 мс")
        if max(c["jitter_ms"] for c in self.data) > 30:
            flags.append("Є дзвінки із джиттером понад 30 мс")
        if max(c["loss_percent"] for c in self.data) > 1:
            flags.append("Є дзвінки із втратами понад 1%")

        text  = f"  Всього дзвінків : {len(self.data)}\n"
        text += f"  Середній MOS    : {sum(mos)/len(mos):.2f}\n"
        text += f"  Максимум MOS    : {max(mos):.2f}\n"
        text += f"  Мінімум MOS     : {min(mos):.2f}\n\n"
        text += "  Розподіл за якістю:\n"
        for cat, cnt in cats.items():
            bar = "█" * int(cnt / len(self.data) * 20)
            text += f"    {cat:12} {cnt:2}  {bar}\n"
        if flags:
            text += "\n  Попередження:\n"
            for f in flags:
                text += f"    {f}\n"

        t = tk.Text(win, font=("Courier", 10), wrap=tk.WORD)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        t.insert(tk.END, text)
        t.config(state=tk.DISABLED)
        tk.Button(win, text="Закрити", command=win.destroy).pack(pady=6)

    def _show_charts(self):
        if not self.data:
            messagebox.showwarning("Попередження", "Немає даних для графіків")
            return

        win = tk.Toplevel(self.root)
        win.title("Графіки QoS")
        win.geometry("950x540")

        fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
        fig.patch.set_facecolor("#f5f5f5")

        ids      = [c["id"] for c in self.data]
        mos_vals = [c["mos"] for c in self.data]
        loss_vals = [c["loss_percent"] for c in self.data]
        bar_colors = [c["color"] for c in self.data]

        ax1 = axes[0]
        ax1.bar(ids, mos_vals, color=bar_colors, edgecolor="gray", linewidth=0.5)
        ax1.axhline(MOS_EXCELLENT, color="#27ae60", linestyle="--", linewidth=1, label="Відмінно (4.0)")
        ax1.axhline(MOS_GOOD,      color="#f39c12", linestyle="--", linewidth=1, label="Добре (3.5)")
        ax1.axhline(MOS_FAIR,      color="#e74c3c", linestyle="--", linewidth=1, label="Задовільно (2.5)")
        ax1.set_title("MOS по дзвінках", fontsize=11, fontweight="bold")
        ax1.set_xlabel("ID дзвінка")
        ax1.set_ylabel("MOS (1–4.5)")
        ax1.set_ylim(0, 5)
        ax1.legend(fontsize=7)
        ax1.set_facecolor("#fafafa")

        ax2 = axes[1]
        cats = {}
        for c in self.data:
            cats[c["quality"]] = cats.get(c["quality"], 0) + 1
        labels  = list(cats.keys())
        sizes   = list(cats.values())
        colors2 = [COLORS.get(l, "#aaa") for l in labels]
        wedges, texts, autotexts = ax2.pie(
            sizes, labels=labels, colors=colors2,
            autopct="%1.0f%%", startangle=140,
            textprops={"fontsize": 9}
        )
        ax2.set_title("Розподіл за якістю", fontsize=11, fontweight="bold")

        ax3 = axes[2]
        loss_colors = ["#e74c3c" if l > 5 else "#f39c12" if l > 1 else "#2ecc71" for l in loss_vals]
        ax3.bar(ids, loss_vals, color=loss_colors, edgecolor="gray", linewidth=0.5)
        ax3.axhline(1, color="#f39c12", linestyle="--", linewidth=1, label="Поріг 1%")
        ax3.axhline(5, color="#e74c3c", linestyle="--", linewidth=1, label="Поріг 5%")
        ax3.set_title("Втрати пакетів (%)", fontsize=11, fontweight="bold")
        ax3.set_xlabel("ID дзвінка")
        ax3.set_ylabel("Втрати (%)")
        ax3.legend(fontsize=8)
        ax3.set_facecolor("#fafafa")

        fig.tight_layout(pad=2.0)

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        tk.Button(win, text="Закрити", command=win.destroy).pack(pady=6)

if __name__ == "__main__":
    root = tk.Tk()
    app = VoIPQoSAnalyzer(root)
    root.mainloop()