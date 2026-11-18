import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta, date
import calendar as pycalendar
import io
import base64
import tempfile
import webbrowser
import os
from PIL import Image, ImageTk, ImageOps

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

DB_NAME = "database.db"

# ==================== SHOP CONFIGURATION (Easily Editable) ====================
SHOP_NAME = "HUSSAIN MOBILE SHOP KHANEWAL"
SHOP_ADDRESS = "Khanewal Plaza, Main Bazaar, Khanewal"
SHOP_PHONE = "03040772399"
SHOP_EMAIL = "srzaibi@gmail.com"
LOGO_PATH = "Logo.png"  # Place your 200x200 Logo.png in this folder

# Image compression settings (attachments)
IMG_MAX_HEIGHT = 720          # max height in pixels
IMG_JPEG_QUALITY = 35         # ~35% quality JPEG compression


def _pil_resample():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def compress_image_bytes(raw_bytes, max_height=IMG_MAX_HEIGHT, quality=IMG_JPEG_QUALITY):
    """Resize image so height <= max_height and compress as JPEG at given quality. Returns JPEG bytes."""
    if not raw_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        try:
            img = ImageOps.exif_transpose(img)  # fix orientation from phone cameras
        except Exception:
            pass
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            background.paste(img, mask=mask)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if h > max_height:
            ratio = max_height / float(h)
            new_size = (max(1, int(w * ratio)), max_height)
            img = img.resize(new_size, _pil_resample())

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        # If anything fails, return original bytes so data is not lost
        return raw_bytes


def init_db():
    """Initializes database.db, creates tables if missing, and safely migrates columns if an old database exists."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS mobiles
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       model
                       TEXT,
                       brand
                       TEXT,
                       imei
                       TEXT,
                       price
                       REAL,
                       color
                       TEXT,
                       storage
                       TEXT,
                       ram
                       TEXT,
                       battery
                       TEXT,
                       with_box
                       INTEGER
                       DEFAULT
                       0,
                       with_charger
                       INTEGER
                       DEFAULT
                       0,
                       condition
                       TEXT
                       DEFAULT
                       'Brand New',
                       quantity
                       INTEGER
                       DEFAULT
                       1,
                       seller_name
                       TEXT,
                       seller_cnic
                       TEXT,
                       seller_address
                       TEXT,
                       seller_phone
                       TEXT,
                       is_sold
                       INTEGER
                       DEFAULT
                       0,
                       img_seller_person
                       BLOB,
                       img_cnic_back
                       BLOB,
                       img_cnic_front
                       BLOB,
                       img_phone_acc
                       BLOB,
                       capture_date
                       TEXT
                   )
                   ''')

    # Automatic schema check & migration for existing databases
    cursor.execute("PRAGMA table_info(mobiles)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    required_columns = [
        ("quantity", "INTEGER DEFAULT 1"),
        ("img_seller_person", "BLOB"),
        ("img_cnic_back", "BLOB"),
        ("img_cnic_front", "BLOB"),
        ("img_phone_acc", "BLOB")
    ]
    for col_name, col_type in required_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE mobiles ADD COLUMN {col_name} {col_type}")

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS sales
                   (
                       sale_id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       mobile_id
                       INTEGER,
                       purchaser_name
                       TEXT,
                       purchaser_cnic
                       TEXT,
                       purchaser_phone
                       TEXT,
                       sold_price
                       REAL,
                       sold_date
                       TEXT,
                       FOREIGN
                       KEY
                   (
                       mobile_id
                   ) REFERENCES mobiles
                   (
                       id
                   )
                       )
                   ''')
    conn.commit()
    conn.close()


class MobileShopApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{SHOP_NAME} - Management System")
        self.root.minsize(1000, 700)
        self.root.geometry("1280x860")
        # Open maximized (Windows / Linux / macOS fallbacks)
        try:
            self.root.state('zoomed')
        except tk.TclError:
            try:
                self.root.attributes('-zoomed', True)
            except tk.TclError:
                try:
                    self.root.attributes('-fullscreen', False)
                    sw = self.root.winfo_screenwidth()
                    sh = self.root.winfo_screenheight()
                    self.root.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TNotebook.Tab', font=('Helvetica', 11, 'bold'), padding=[14, 8])
        self.style.configure('Treeview.Heading', font=('Helvetica', 10, 'bold'), background="#2C5282", foreground="white")
        self.style.map('Treeview.Heading', background=[('active', '#2B6CB0')])
        self.style.configure('Treeview', font=('Helvetica', 9), rowheight=26)
        self.style.configure('TButton', font=('Helvetica', 10), padding=4)
        self.style.configure('Accent.TButton', font=('Helvetica', 10, 'bold'))
        self.style.configure('TLabelframe.Label', font=('Helvetica', 10, 'bold'), foreground="#1A365D")
        self.style.configure('TLabelframe', padding=8)
        self.style.configure('Header.TLabel', background="#1A365D", foreground="white")
        self._header_photo = None  # keep reference so logo is not garbage-collected

        # SHOP BRANDING HEADER (Top Banner) with logo
        header_frame = tk.Frame(root, bg="#1A365D", pady=8)
        header_frame.pack(fill='x', side='top')

        header_inner = tk.Frame(header_frame, bg="#1A365D")
        header_inner.pack(fill='x', padx=12)

        # Logo on the left
        logo_container = tk.Frame(header_inner, bg="#1A365D")
        logo_container.pack(side='left', padx=(0, 12))
        if os.path.exists(LOGO_PATH):
            try:
                logo_img = Image.open(LOGO_PATH)
                logo_img = logo_img.convert("RGBA")
                logo_img.thumbnail((56, 56), _pil_resample())
                self._header_photo = ImageTk.PhotoImage(logo_img)
                tk.Label(logo_container, image=self._header_photo, bg="#1A365D").pack()
            except Exception:
                tk.Label(logo_container, text="📱", font=('Helvetica', 28), fg="white", bg="#1A365D").pack()
        else:
            tk.Label(logo_container, text="📱", font=('Helvetica', 28), fg="white", bg="#1A365D").pack()

        text_container = tk.Frame(header_inner, bg="#1A365D")
        text_container.pack(side='left', fill='x', expand=True)

        lbl_shop = tk.Label(text_container, text=SHOP_NAME, font=('Helvetica', 17, 'bold'),
                            fg="white", bg="#1A365D", anchor='w')
        lbl_shop.pack(fill='x')

        lbl_details = tk.Label(text_container,
                               text=f"📍 {SHOP_ADDRESS}   |   📞 {SHOP_PHONE}   |   ✉️ {SHOP_EMAIL}",
                               font=('Helvetica', 10), fg="#E2E8F0", bg="#1A365D", anchor='w')
        lbl_details.pack(fill='x', pady=(2, 0))

        # Main Notebook (Tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=(6, 10))

        # Create Tabs
        self.tab_inventory = ttk.Frame(self.notebook)
        self.tab_add_mobile = ttk.Frame(self.notebook)
        self.tab_sales = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_inventory, text="📦 Inventory / Mobiles")
        self.tab_inventory_content()

        self.notebook.add(self.tab_add_mobile, text="➕ Add Mobile Entry")
        self.tab_add_mobile_content()

        self.notebook.add(self.tab_sales, text="💰 Sales & Reports")
        self.tab_sales_content()

        init_db()
        self.load_inventory()
        self.load_sales()

    # ==================== TAB 1: INVENTORY ====================
    def tab_inventory_content(self):
        frame = self.tab_inventory

        action_frame = ttk.Frame(frame, padding=10)
        action_frame.pack(fill='x', side='top')

        ttk.Button(action_frame, text="🔄 Refresh List", command=self.load_inventory).pack(side='left', padx=4)
        ttk.Button(action_frame, text="🏷️ Sell Selected Mobile", command=self.open_sell_dialog).pack(side='left', padx=4)
        ttk.Button(action_frame, text="📄 View Complete Details", command=self.view_inventory_details).pack(side='left', padx=4)
        ttk.Button(action_frame, text="🗑️ Delete Mobile", command=self.delete_mobile).pack(side='left', padx=4)

        ttk.Label(action_frame, text="🔍 Search Brand / Model / IMEI:").pack(side='left', padx=(18, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter_inventory())
        search_entry = ttk.Entry(action_frame, textvariable=self.search_var, width=24)
        search_entry.pack(side='left', padx=4)

        table_frame = ttk.Frame(frame, padding=10)
        table_frame.pack(fill='both', expand=True)

        columns = ("ID", "Brand", "Model", "IMEI", "Price", "Qty", "Storage", "RAM", "Condition", "Seller")
        self.inv_tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')

        col_widths = [50, 100, 120, 140, 90, 55, 80, 70, 100, 130]
        for col, width in zip(columns, col_widths):
            self.inv_tree.heading(col, text=col)
            self.inv_tree.column(col, width=width, anchor='center')

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=scrollbar.set)

        self.inv_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def load_inventory(self):
        for row in self.inv_tree.get_children():
            self.inv_tree.delete(row)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, brand, model, imei, price, quantity, storage, ram, condition, seller_name FROM mobiles WHERE quantity > 0")
        for row in cursor.fetchall():
            seller_val = row[9] if row[9] else "N/A (Brand New)"
            formatted_row = (row[0], row[1], row[2], row[3], f"Rs. {row[4]:,.0f}" if row[4] else "Rs. 0", row[5], row[6],
                             row[7], row[8], seller_val)
            self.inv_tree.insert("", "end", values=formatted_row)
        conn.close()

    def filter_inventory(self):
        query = self.search_var.get().lower()
        for row in self.inv_tree.get_children():
            self.inv_tree.delete(row)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, brand, model, imei, price, quantity, storage, ram, condition, seller_name FROM mobiles WHERE quantity > 0")
        for row in cursor.fetchall():
            if query in row[1].lower() or query in row[2].lower() or query in row[3].lower():
                seller_val = row[9] if row[9] else "N/A (Brand New)"
                formatted_row = (row[0], row[1], row[2], row[3], f"Rs. {row[4]:,.0f}" if row[4] else "Rs. 0", row[5], row[6],
                                 row[7], row[8], seller_val)
                self.inv_tree.insert("", "end", values=formatted_row)
        conn.close()

    def delete_mobile(self):
        selected = self.inv_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a mobile to delete.")
            return

        mobile_id = self.inv_tree.item(selected)['values'][0]
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete mobile ID {mobile_id}?"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mobiles WHERE id = ?", (mobile_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Mobile deleted successfully.")
            self.load_inventory()

    # ==================== TAB 2: ADD MOBILE ENTRY ====================
    def tab_add_mobile_content(self):
        frame = self.tab_add_mobile

        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=15)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Form Fields variables
        self.entry_vars = {}
        fields = [
            ("Brand", "brand"), ("Model", "model"), ("IMEI", "imei"),
            ("Price (Rs.)", "price"), ("Quantity", "quantity"), ("Color", "color"),
            ("Storage", "storage"), ("RAM", "ram"), ("Battery (%)", "battery"), ("Condition", "condition")
        ]

        form_grid = ttk.LabelFrame(scrollable_frame, text=" Mobile Information ", padding=15)
        form_grid.pack(fill='x', expand=True, padx=5, pady=5)

        for idx, (label_text, key) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2

            lbl = ttk.Label(form_grid, text=f"{label_text}:", font=('Helvetica', 9, 'bold'))
            lbl.grid(row=row, column=col, sticky='w', padx=5, pady=8)

            if key == "condition":
                var = tk.StringVar(value="Brand New")
                combo = ttk.Combobox(form_grid, textvariable=var, values=["Brand New", "Used"], width=22,
                                     state="readonly")
                combo.grid(row=row, column=col + 1, sticky='ew', padx=5, pady=8)
                combo.bind("<<ComboboxSelected>>", self.toggle_condition_fields)
                self.entry_vars[key] = var
            elif key == "quantity":
                var = tk.StringVar(value="1")
                ent = ttk.Entry(form_grid, textvariable=var, width=25)
                ent.grid(row=row, column=col + 1, sticky='ew', padx=5, pady=8)
                self.entry_vars[key] = var
            else:
                var = tk.StringVar()
                ent = ttk.Entry(form_grid, textvariable=var, width=25)
                ent.grid(row=row, column=col + 1, sticky='ew', padx=5, pady=8)
                self.entry_vars[key] = var

        # Seller Information Frame (Only for Used Phones)
        self.seller_frame = ttk.LabelFrame(scrollable_frame, text=" Seller Information (Required for Used Phones) ",
                                           padding=15)
        self.seller_frame.pack(fill='x', expand=True, padx=5, pady=5)

        seller_fields = [
            ("Seller Name", "seller_name"), ("Seller CNIC", "seller_cnic"),
            ("Seller Phone", "seller_phone"), ("Seller Address", "seller_address")
        ]
        for idx, (label_text, key) in enumerate(seller_fields):
            row = idx // 2
            col = (idx % 2) * 2

            lbl = ttk.Label(self.seller_frame, text=f"{label_text}:", font=('Helvetica', 9, 'bold'))
            lbl.grid(row=row, column=col, sticky='w', padx=5, pady=8)
            var = tk.StringVar()
            ent = ttk.Entry(self.seller_frame, textvariable=var, width=25)
            ent.grid(row=row, column=col + 1, sticky='ew', padx=5, pady=8)
            self.entry_vars[key] = var

        # Checkboxes
        chk_frame = ttk.LabelFrame(scrollable_frame, text=" Accessories Included ", padding=10)
        chk_frame.pack(fill='x', expand=True, padx=5, pady=10)

        self.box_var = tk.IntVar(value=0)
        self.charger_var = tk.IntVar(value=0)

        ttk.Checkbutton(chk_frame, text="Original Box", variable=self.box_var).pack(side='left', padx=20)
        ttk.Checkbutton(chk_frame, text="Original Charger", variable=self.charger_var).pack(side='left', padx=20)

        # Image Attachments Frame (4 Optional Images + Webcam)
        self.img_attach_frame = ttk.LabelFrame(scrollable_frame, text=" Image Attachments & Webcam Capture ",
                                               padding=10)
        self.img_attach_frame.pack(fill='x', expand=True, padx=5, pady=5)

        self.images_data = {
            "seller_person": None,
            "cnic_back": None,
            "cnic_front": None,
            "phone_acc": None
        }

        self.img_labels = {}
        attachment_configs = [
            ("1. Seller Person / Owner", "seller_person", True),
            ("2. CNIC Back", "cnic_back", True),
            ("3. CNIC Front", "cnic_front", True),
            ("4. Phone with Accessories", "phone_acc", False)
        ]

        for title, key, is_used_only in attachment_configs:
            row_f = ttk.Frame(self.img_attach_frame, padding=5)
            row_f.pack(fill='x', pady=2)

            lbl_title = ttk.Label(row_f, text=f"{title}:", width=26, font=('Helvetica', 9, 'bold'))
            lbl_title.pack(side='left', padx=5)

            lbl_status = ttk.Label(row_f, text="No image", font=('Helvetica', 8, 'italic'), width=20)
            lbl_status.pack(side='left', padx=5)
            self.img_labels[key] = (lbl_status, is_used_only)

            btn_cam = ttk.Button(row_f, text="📷 Webcam", command=lambda k=key: self.capture_webcam(k))
            btn_cam.pack(side='right', padx=2)

            btn_browse = ttk.Button(row_f, text="📁 Browse", command=lambda k=key: self.load_image_file(k))
            btn_browse.pack(side='right', padx=2)

        # Save Button
        ttk.Button(scrollable_frame, text="💾 Save Mobile Entry", command=self.save_mobile_entry).pack(pady=20, ipadx=10,
                                                                                                      ipady=5)

        self.toggle_condition_fields()

    def toggle_condition_fields(self, event=None):
        condition = self.entry_vars["condition"].get()
        if condition == "Brand New":
            for widget in self.seller_frame.winfo_children():
                widget.configure(state='disabled')
            for key, (lbl, is_used_only) in self.img_labels.items():
                if is_used_only:
                    self.images_data[key] = None
                    lbl.config(text="Disabled (New)")
        else:
            for widget in self.seller_frame.winfo_children():
                widget.configure(state='normal')
            for key, (lbl, is_used_only) in self.img_labels.items():
                if is_used_only:
                    lbl.config(text="No image" if not self.images_data[key] else "Attached ✓")

    def load_image_file(self, key):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.png *.jpeg *.bmp *.webp")])
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    raw = f.read()
                compressed = compress_image_bytes(raw)
                self.images_data[key] = compressed
                size_kb = len(compressed) / 1024 if compressed else 0
                name = file_path.replace("\\", "/").split("/")[-1]
                self.img_labels[key][0].config(text=f"{name} ({size_kb:.0f} KB ✓)")
            except Exception as e:
                messagebox.showerror("Image Error", f"Could not process image:\n{e}")

    def capture_webcam(self, key):
        """Webcam capture with on-screen Capture / Cancel buttons (no keyboard required)."""
        try:
            import cv2
        except ImportError:
            messagebox.showerror("Webcam Error",
                                 "OpenCV (cv2) is not installed.\nPlease install it via terminal using: pip install opencv-python")
            self.load_image_file(key)
            return

        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise Exception("Could not initialize webcam device (Index 0).")
        except Exception as e:
            messagebox.showwarning("Webcam Notice",
                                   f"Webcam error: {str(e)}\nPlease use 'Browse' to upload an image instead.")
            self.load_image_file(key)
            return

        win = tk.Toplevel(self.root)
        win.title(f"Webcam Capture - {SHOP_NAME}")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        try:
            win.geometry(f"+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 60}")
        except Exception:
            pass

        preview_label = ttk.Label(win)
        preview_label.pack(padx=10, pady=10)

        status_lbl = ttk.Label(win, text="Position the subject, then click Capture Photo", font=('Helvetica', 9))
        status_lbl.pack(pady=(0, 6))

        btn_frame = ttk.Frame(win, padding=8)
        btn_frame.pack(fill='x')

        state = {"running": True, "photo": None, "last_frame": None}

        def update_preview():
            if not state["running"]:
                return
            ret, frame = cap.read()
            if ret:
                state["last_frame"] = frame
                # BGR -> RGB for Tk
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Scale preview to max width ~640
                h, w = rgb.shape[:2]
                max_w = 640
                if w > max_w:
                    scale = max_w / float(w)
                    rgb = cv2.resize(rgb, (max_w, int(h * scale)))
                img = Image.fromarray(rgb)
                tk_img = ImageTk.PhotoImage(img)
                preview_label.configure(image=tk_img)
                preview_label.image = tk_img  # keep reference
            win.after(30, update_preview)

        def do_capture():
            frame = state["last_frame"]
            if frame is None:
                messagebox.showwarning("Capture", "No frame available yet. Please wait a moment.", parent=win)
                return
            success, encoded_img = cv2.imencode('.jpg', frame)
            if not success:
                messagebox.showerror("Capture", "Failed to encode image.", parent=win)
                return
            state["photo"] = encoded_img.tobytes()
            state["running"] = False
            try:
                cap.release()
            except Exception:
                pass
            win.destroy()

        def do_cancel():
            state["running"] = False
            state["photo"] = None
            try:
                cap.release()
            except Exception:
                pass
            win.destroy()

        ttk.Button(btn_frame, text="📷 Capture Photo", command=do_capture).pack(side='left', expand=True, padx=6, ipady=4)
        ttk.Button(btn_frame, text="❌ Cancel", command=do_cancel).pack(side='right', expand=True, padx=6, ipady=4)

        win.protocol("WM_DELETE_WINDOW", do_cancel)
        update_preview()
        win.wait_window()

        # Ensure camera is released if window closed unexpectedly
        try:
            if cap.isOpened():
                cap.release()
        except Exception:
            pass

        if state["photo"]:
            compressed = compress_image_bytes(state["photo"])
            self.images_data[key] = compressed
            size_kb = len(compressed) / 1024 if compressed else 0
            self.img_labels[key][0].config(text=f"Webcam ✓ ({size_kb:.0f} KB)")
            messagebox.showinfo("Success", f"Webcam image captured & compressed ({size_kb:.0f} KB).")

    def save_mobile_entry(self):
        try:
            data = {k: v.get().strip() for k, v in self.entry_vars.items()}

            if not data['brand'] or not data['model'] or not data['imei'] or not data['price']:
                messagebox.showerror("Error", "Brand, Model, IMEI, and Price are required fields!")
                return

            if data['condition'] == "Used" and not data['seller_name']:
                messagebox.showerror("Error", "Seller Name is required for Used phones!")
                return

            price = float(data['price'])
            quantity = int(data['quantity']) if data['quantity'].isdigit() else 1
            capture_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO mobiles (model, brand, imei, price, quantity, color, storage, ram, battery,
                                                with_box, with_charger, condition, seller_name, seller_cnic,
                                                seller_address, seller_phone, is_sold,
                                                img_seller_person, img_cnic_back, img_cnic_front, img_phone_acc,
                                                capture_date)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                           ''', (
                               data['model'], data['brand'], data['imei'], price, quantity, data['color'],
                               data['storage'], data['ram'], data['battery'], self.box_var.get(),
                               self.charger_var.get(), data['condition'], data['seller_name'],
                               data['seller_cnic'], data['seller_address'], data['seller_phone'],
                               self.images_data['seller_person'], self.images_data['cnic_back'],
                               self.images_data['cnic_front'], self.images_data['phone_acc'], capture_date
                           ))
            conn.commit()
            conn.close()

            messagebox.showinfo("Success", "Mobile successfully recorded into inventory!")
            self.load_inventory()

            # Reset form
            for var in self.entry_vars.values():
                var.set("")
            self.entry_vars["condition"].set("Brand New")
            self.entry_vars["quantity"].set("1")
            self.box_var.set(0)
            self.charger_var.set(0)
            for k in self.images_data:
                self.images_data[k] = None
                self.img_labels[k][0].config(text="No image")
            self.toggle_condition_fields()

        except ValueError:
            messagebox.showerror("Error", "Price and Quantity must be valid numbers.")

    # ==================== TAB 3: SALES & REPORTS ====================
    def open_date_picker(self, date_var, title="Select Date"):
        """Simple calendar popup to pick a date (YYYY-MM-DD) into date_var."""
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)

        # Position near cursor / center of parent
        try:
            popup.geometry(f"+{self.root.winfo_rootx() + 200}+{self.root.winfo_rooty() + 120}")
        except Exception:
            pass

        # Parse current value
        try:
            current = datetime.strptime(date_var.get().strip()[:10], "%Y-%m-%d").date()
        except Exception:
            current = date.today()

        year_var = tk.IntVar(value=current.year)
        month_var = tk.IntVar(value=current.month)
        selected = {"day": current.day}

        top = ttk.Frame(popup, padding=8)
        top.pack(fill='x')

        def shift_month(delta):
            m = month_var.get() + delta
            y = year_var.get()
            if m < 1:
                m = 12
                y -= 1
            elif m > 12:
                m = 1
                y += 1
            month_var.set(m)
            year_var.set(y)
            build_days()

        ttk.Button(top, text="◀", width=3, command=lambda: shift_month(-1)).pack(side='left')
        lbl_ym = ttk.Label(top, font=('Helvetica', 11, 'bold'))
        lbl_ym.pack(side='left', expand=True, padx=8)
        ttk.Button(top, text="▶", width=3, command=lambda: shift_month(1)).pack(side='right')

        days_frame = ttk.Frame(popup, padding=6)
        days_frame.pack()

        for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            ttk.Label(days_frame, text=name, width=4, anchor='center',
                      font=('Helvetica', 8, 'bold')).grid(row=0, column=i, padx=1, pady=2)

        day_buttons = []

        def choose_day(d):
            selected["day"] = d
            chosen = date(year_var.get(), month_var.get(), d)
            date_var.set(chosen.strftime("%Y-%m-%d"))
            popup.destroy()
            self.load_sales()

        def build_days():
            for b in day_buttons:
                b.destroy()
            day_buttons.clear()
            y, m = year_var.get(), month_var.get()
            lbl_ym.config(text=f"{pycalendar.month_name[m]} {y}")
            month_cal = pycalendar.Calendar(firstweekday=0).monthdayscalendar(y, m)
            for r, week in enumerate(month_cal, start=1):
                for c, day in enumerate(week):
                    if day == 0:
                        ttk.Label(days_frame, text="", width=4).grid(row=r, column=c, padx=1, pady=1)
                    else:
                        is_sel = (day == selected["day"] and m == current.month and y == current.year)
                        btn = tk.Button(
                            days_frame, text=str(day), width=3,
                            relief='flat' if not is_sel else 'solid',
                            bg="#2B6CB0" if is_sel else "#EDF2F7",
                            fg="white" if is_sel else "#1A202C",
                            activebackground="#3182CE",
                            font=('Helvetica', 9, 'bold' if is_sel else 'normal'),
                            command=lambda d=day: choose_day(d)
                        )
                        btn.grid(row=r, column=c, padx=1, pady=1)
                        day_buttons.append(btn)

        footer = ttk.Frame(popup, padding=6)
        footer.pack(fill='x')

        def set_today():
            today = date.today()
            date_var.set(today.strftime("%Y-%m-%d"))
            popup.destroy()
            self.load_sales()

        def clear_and_close():
            popup.destroy()

        ttk.Button(footer, text="Today", command=set_today).pack(side='left', padx=4)
        ttk.Button(footer, text="Cancel", command=clear_and_close).pack(side='right', padx=4)

        build_days()
        popup.wait_window()

    def tab_sales_content(self):
        frame = self.tab_sales

        # 1. Action & Filter Frame (Top) - two rows for cleaner layout
        action_outer = ttk.Frame(frame, padding=(10, 8))
        action_outer.pack(fill='x', side='top')

        row1 = ttk.Frame(action_outer)
        row1.pack(fill='x', pady=(0, 6))

        ttk.Button(row1, text="🔄 Refresh", command=self.load_sales).pack(side='left', padx=3)
        ttk.Button(row1, text="📄 Complete Details", command=self.view_sales_details).pack(side='left', padx=3)
        ttk.Button(row1, text="📄 Export PDF Report", command=self.export_filtered_sales_pdf).pack(side='left', padx=3)
        ttk.Button(row1, text="📊 Export Excel Report", command=self.export_filtered_sales_excel).pack(side='left', padx=3)

        # Search on the right of row 1
        ttk.Label(row1, text="Search:").pack(side='left', padx=(16, 4))
        self.sales_search_var = tk.StringVar()
        self.sales_search_var.trace("w", lambda *args: self.filter_sales())
        sales_search_entry = ttk.Entry(row1, textvariable=self.sales_search_var, width=18)
        sales_search_entry.pack(side='left', padx=2)

        # Date filter row
        row2 = ttk.LabelFrame(action_outer, text=" 📅 Report Date Filter ", padding=8)
        row2.pack(fill='x')

        default_start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        default_end = datetime.now().strftime("%Y-%m-%d")
        self.start_date_var = tk.StringVar(value=default_start)
        self.end_date_var = tk.StringVar(value=default_end)

        ttk.Label(row2, text="From:", font=('Helvetica', 9, 'bold')).pack(side='left', padx=(4, 2))
        start_entry = ttk.Entry(row2, textvariable=self.start_date_var, width=12)
        start_entry.pack(side='left', padx=2)
        ttk.Button(row2, text="📆", width=3,
                   command=lambda: self.open_date_picker(self.start_date_var, "Select From Date")).pack(side='left', padx=(0, 10))

        ttk.Label(row2, text="To:", font=('Helvetica', 9, 'bold')).pack(side='left', padx=(4, 2))
        end_entry = ttk.Entry(row2, textvariable=self.end_date_var, width=12)
        end_entry.pack(side='left', padx=2)
        ttk.Button(row2, text="📆", width=3,
                   command=lambda: self.open_date_picker(self.end_date_var, "Select To Date")).pack(side='left', padx=(0, 10))

        ttk.Button(row2, text="🔍 Apply Filter", command=self.load_sales).pack(side='left', padx=6)
        ttk.Button(row2, text="Last 7 Days",
                   command=lambda: self._set_date_range(7)).pack(side='left', padx=2)
        ttk.Button(row2, text="Last 30 Days",
                   command=lambda: self._set_date_range(30)).pack(side='left', padx=2)
        ttk.Button(row2, text="This Month",
                   command=self._set_this_month).pack(side='left', padx=2)
        ttk.Button(row2, text="All Time",
                   command=self._set_all_time).pack(side='left', padx=2)

        # 2. Financial Summary Banner (Middle)
        summary_frame = ttk.LabelFrame(frame, text=" 📊 Financial Report Summary (Filtered Period) ", padding=12)
        summary_frame.pack(fill='x', padx=10, pady=6)

        summary_inner = ttk.Frame(summary_frame)
        summary_inner.pack(fill='x')

        self.lbl_total_sales = ttk.Label(summary_inner, text="Total Sales: Rs. 0", font=('Helvetica', 12, 'bold'), foreground="#2B6CB0")
        self.lbl_total_sales.pack(side='left', expand=True)

        self.lbl_total_inv = ttk.Label(summary_inner, text="Total Investment: Rs. 0", font=('Helvetica', 12, 'bold'), foreground="#4A5568")
        self.lbl_total_inv.pack(side='left', expand=True)

        self.lbl_total_profit = ttk.Label(summary_inner, text="Total Profit: Rs. 0", font=('Helvetica', 12, 'bold'), foreground="#2F855A")
        self.lbl_total_profit.pack(side='left', expand=True)

        # 3. Sales Table (Bottom)
        table_frame = ttk.Frame(frame, padding=10)
        table_frame.pack(fill='both', expand=True)

        columns = ("Sale ID", "Mobile ID", "Brand & Model", "Purchaser Name", "Phone", "CNIC", "Sold Price", "Sold Date")
        self.sales_tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')

        col_widths = [70, 80, 150, 140, 110, 120, 110, 140]
        for col, width in zip(columns, col_widths):
            self.sales_tree.heading(col, text=col)
            self.sales_tree.column(col, width=width, anchor='center')

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=scrollbar.set)

        self.sales_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def _set_date_range(self, days):
        self.end_date_var.set(date.today().strftime("%Y-%m-%d"))
        self.start_date_var.set((date.today() - timedelta(days=days)).strftime("%Y-%m-%d"))
        self.load_sales()

    def _set_this_month(self):
        today = date.today()
        self.start_date_var.set(today.replace(day=1).strftime("%Y-%m-%d"))
        self.end_date_var.set(today.strftime("%Y-%m-%d"))
        self.load_sales()

    def _set_all_time(self):
        self.start_date_var.set("2000-01-01")
        self.end_date_var.set(date.today().strftime("%Y-%m-%d"))
        self.load_sales()

    def get_filtered_sales_data(self):
        """Helper method to query the database using current date filters and search term."""
        start_date = self.start_date_var.get().strip() or "2000-01-01"
        end_date = self.end_date_var.get().strip() or "2099-12-31"

        end_date_query = end_date + " 23:59:59" if len(end_date) == 10 else end_date
        start_date_query = start_date + " 00:00:00" if len(start_date) == 10 else start_date
        search_query = self.sales_search_var.get().strip().lower()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT s.sale_id,
                              s.mobile_id,
                              m.brand || ' ' || m.model,
                              s.purchaser_name,
                              s.purchaser_phone,
                              s.purchaser_cnic,
                              s.sold_price,
                              s.sold_date,
                              m.price
                       FROM sales s
                                JOIN mobiles m ON s.mobile_id = m.id
                       WHERE s.sold_date BETWEEN ? AND ?
                       ''', (start_date_query, end_date_query))

        raw_rows = cursor.fetchall()
        conn.close()

        filtered_rows = []
        for row in raw_rows:
            sale_id, mobile_id, brand_model, p_name, p_phone, p_cnic, sold_price, sold_date, purchase_price = row

            if search_query:
                combined_str = f"{sale_id} {mobile_id} {brand_model} {p_name} {p_phone} {p_cnic} {sold_date}".lower()
                if search_query not in combined_str:
                    continue

            filtered_rows.append(row)
        return filtered_rows

    def load_sales(self):
        for row in self.sales_tree.get_children():
            self.sales_tree.delete(row)

        rows = self.get_filtered_sales_data()
        total_sales = 0.0
        total_investment = 0.0

        for row in rows:
            sold_price = row[6] if row[6] else 0.0
            purchase_price = row[8] if row[8] else 0.0

            total_sales += sold_price
            total_investment += purchase_price

            formatted_row = (row[0], row[1], row[2], row[3], row[4], row[5],
                             f"Rs. {sold_price:,.0f}", row[7])
            self.sales_tree.insert("", "end", values=formatted_row)

        total_profit = total_sales - total_investment

        self.lbl_total_sales.config(text=f"Total Sales: Rs. {total_sales:,.0f}")
        self.lbl_total_inv.config(text=f"Total Investment: Rs. {total_investment:,.0f}")
        self.lbl_total_profit.config(text=f"Total Profit: Rs. {total_profit:,.0f}")

    def filter_sales(self):
        self.load_sales()

    # ==================== EXPORT FILTERED REPORTS (PDF & EXCEL) ====================
    def export_filtered_sales_pdf(self):
        rows = self.get_filtered_sales_data()
        if not rows:
            messagebox.showwarning("Warning", "No sales records found for the selected filter criteria.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
                                                 initialfile=f"Sales_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            elements = []

            if os.path.exists(LOGO_PATH):
                try:
                    elements.append(RLImage(LOGO_PATH, width=60, height=60))
                    elements.append(Spacer(1, 4))
                except Exception:
                    pass

            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor("#1A365D"), alignment=1, spaceAfter=2)
            subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#4A5568"), alignment=1, spaceAfter=10)

            elements.append(Paragraph(SHOP_NAME, title_style))
            elements.append(Paragraph(f"📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}", subtitle_style))
            elements.append(Paragraph("<b>FILTERED SALES & FINANCIAL REPORT</b>", ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=8)))

            period_str = f"Period: {self.start_date_var.get()} to {self.end_date_var.get()}"
            elements.append(Paragraph(f"<b>{period_str}</b> &nbsp;&nbsp;|&nbsp;&nbsp; <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", ParagraphStyle('Sub', alignment=1, fontSize=8.5, spaceAfter=10)))

            tot_sales = sum([r[6] if r[6] else 0.0 for r in rows])
            tot_inv = sum([r[8] if r[8] else 0.0 for r in rows])
            tot_profit = tot_sales - tot_inv

            summary_data = [
                [Paragraph("<b>Total Sales</b>", styles['Normal']), Paragraph("<b>Total Investment</b>", styles['Normal']), Paragraph("<b>Total Net Profit</b>", styles['Normal'])],
                [f"Rs. {tot_sales:,.0f}", f"Rs. {tot_inv:,.0f}", f"Rs. {tot_profit:,.0f}"]
            ]
            t_sum = Table(summary_data, colWidths=[180, 180, 180])
            t_sum.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            elements.append(t_sum)
            elements.append(Spacer(1, 15))

            table_data = [[
                Paragraph("<b>ID</b>", styles['Normal']),
                Paragraph("<b>Model</b>", styles['Normal']),
                Paragraph("<b>Purchaser</b>", styles['Normal']),
                Paragraph("<b>Phone</b>", styles['Normal']),
                Paragraph("<b>Sold Price</b>", styles['Normal']),
                Paragraph("<b>Date</b>", styles['Normal'])
            ]]

            for r in rows:
                table_data.append([
                    str(r[0]),
                    str(r[2]),
                    str(r[3]),
                    str(r[4]),
                    f"Rs. {r[6]:,.0f}" if r[6] else "Rs. 0",
                    str(r[7])
                ])

            t = Table(table_data, colWidths=[35, 130, 110, 85, 85, 95])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0"))
            ]))
            elements.append(t)

            doc.build(elements)
            messagebox.showinfo("Success", f"Sales PDF report exported successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF report: {str(e)}")

    def export_filtered_sales_excel(self):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            messagebox.showerror("Excel Error", "openpyxl is not installed.\nPlease install it via terminal using: pip install openpyxl")
            return

        rows = self.get_filtered_sales_data()
        if not rows:
            messagebox.showwarning("Warning", "No sales records found for the selected filter criteria.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")],
                                                 initialfile=f"Sales_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        if not file_path:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Sales Report"

            header_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")
            header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
            title_font = Font(name="Arial", size=14, bold=True, color="1A365D")
            bold_font = Font(name="Arial", size=10, bold=True)
            regular_font = Font(name="Arial", size=10)
            thin_border = Border(
                left=Side(style='thin', color='CBD5E0'),
                right=Side(style='thin', color='CBD5E0'),
                top=Side(style='thin', color='CBD5E0'),
                bottom=Side(style='thin', color='CBD5E0')
            )

            ws.append([SHOP_NAME])
            ws.cell(row=1, column=1).font = title_font
            ws.append([f"Sales & Financial Report (Period: {self.start_date_var.get()} to {self.end_date_var.get()})"])
            ws.append([f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
            ws.append([])

            tot_sales = sum([r[6] if r[6] else 0.0 for r in rows])
            tot_inv = sum([r[8] if r[8] else 0.0 for r in rows])
            tot_profit = tot_sales - tot_inv

            ws.append(["Summary Metric", "Amount (PKR)"])
            ws.append(["Total Sales", tot_sales])
            ws.append(["Total Investment", tot_inv])
            ws.append(["Total Net Profit", tot_profit])
            ws.append([])

            for r in range(5, 9):
                for c in range(1, 3):
                    cell = ws.cell(row=r, column=c)
                    cell.font = bold_font if r == 5 or c == 1 else regular_font
                    cell.border = thin_border
                    if r == 5:
                        cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

            headers = ["Sale ID", "Mobile ID", "Brand & Model", "Purchaser Name", "Phone", "CNIC", "Sold Price (Rs.)", "Purchase Price (Rs.)", "Profit (Rs.)", "Sold Date"]
            ws.append(headers)

            header_row_idx = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=header_row_idx, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            for r in rows:
                sale_id, mobile_id, brand_model, p_name, p_phone, p_cnic, sold_price, sold_date, purchase_price = r
                profit = (sold_price or 0.0) - (purchase_price or 0.0)

                row_data = [
                    sale_id,
                    mobile_id,
                    brand_model,
                    p_name,
                    p_phone,
                    p_cnic,
                    sold_price or 0.0,
                    purchase_price or 0.0,
                    profit,
                    sold_date
                ]
                ws.append(row_data)

            for row in ws.iter_rows(min_row=header_row_idx + 1, max_row=ws.max_row, min_col=1, max_col=len(headers)):
                for cell in row:
                    cell.font = regular_font
                    cell.border = thin_border
                    if cell.column in [7, 8, 9]:
                        cell.number_format = '#,##0'

            wb.save(file_path)
            messagebox.showinfo("Success", f"Sales Excel report exported successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Excel Error", f"Failed to generate Excel report: {str(e)}")

    def open_sell_dialog(self):
        selected = self.inv_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an available mobile from the inventory first.")
            return

        mobile_data = self.inv_tree.item(selected)['values']
        mobile_id = mobile_data[0]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT quantity FROM mobiles WHERE id = ?", (mobile_id,))
        res = cursor.fetchone()
        conn.close()

        current_qty = res[0] if res else int(mobile_data[5])

        if current_qty <= 0:
            messagebox.showerror("Error", "This mobile is out of stock!")
            return

        sell_win = tk.Toplevel(self.root)
        sell_win.title(f"Sell Mobile (ID: {mobile_id})")
        sell_win.geometry("400x380")
        sell_win.grab_set()

        ttk.Label(sell_win, text=f"Complete Sale Transaction (Stock Qty: {current_qty})", font=('Helvetica', 11, 'bold')).pack(pady=10)

        form_frame = ttk.Frame(sell_win, padding=10)
        form_frame.pack(fill='both', expand=True)

        ttk.Label(form_frame, text="Purchaser Name:").grid(row=0, column=0, sticky='w', pady=5)
        p_name = ttk.Entry(form_frame, width=25)
        p_name.grid(row=0, column=1, pady=5)

        ttk.Label(form_frame, text="Purchaser CNIC:").grid(row=1, column=0, sticky='w', pady=5)
        p_cnic = ttk.Entry(form_frame, width=25)
        p_cnic.grid(row=1, column=1, pady=5)

        ttk.Label(form_frame, text="Purchaser Phone:").grid(row=2, column=0, sticky='w', pady=5)
        p_phone = ttk.Entry(form_frame, width=25)
        p_phone.grid(row=2, column=1, pady=5)

        ttk.Label(form_frame, text="Final Sold Price (Rs.):").grid(row=3, column=0, sticky='w', pady=5)
        p_price = ttk.Entry(form_frame, width=25)
        p_price.insert(0, str(mobile_data[4]).replace("Rs.", "").replace(",", "").strip())
        p_price.grid(row=3, column=1, pady=5)

        ttk.Label(form_frame, text="Quantity to Sell:").grid(row=4, column=0, sticky='w', pady=5)
        p_qty = ttk.Entry(form_frame, width=25)
        p_qty.insert(0, "1")
        p_qty.grid(row=4, column=1, pady=5)

        def confirm_sale():
            name = p_name.get().strip()
            cnic = p_cnic.get().strip()
            phone = p_phone.get().strip()
            s_price_val = p_price.get().strip()
            qty_val = p_qty.get().strip()

            if not name or not s_price_val or not qty_val:
                messagebox.showerror("Error", "Purchaser Name, Sold Price, and Quantity are required!")
                return

            try:
                sold_price = float(s_price_val)
                sell_qty = int(qty_val)

                if sell_qty <= 0 or sell_qty > current_qty:
                    messagebox.showerror("Error", f"Invalid quantity! Available stock is {current_qty}.")
                    return

                sold_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()

                new_sale_ids = []
                for _ in range(sell_qty):
                    cursor.execute('''
                                   INSERT INTO sales (mobile_id, purchaser_name, purchaser_cnic, purchaser_phone,
                                                      sold_price, sold_date)
                                   VALUES (?, ?, ?, ?, ?, ?)
                                   ''', (mobile_id, name, cnic, phone, sold_price, sold_date))
                    new_sale_ids.append(cursor.lastrowid)

                new_qty = current_qty - sell_qty
                is_sold_flag = 1 if new_qty <= 0 else 0

                cursor.execute('UPDATE mobiles SET quantity = ?, is_sold = ? WHERE id = ?', (new_qty, is_sold_flag, mobile_id))

                conn.commit()
                conn.close()

                messagebox.showinfo("Success", f"Mobile sale recorded successfully! Remaining stock: {new_qty}")
                sell_win.destroy()
                self.load_inventory()
                self.load_sales()

                # Automatically open receipt in browser and prompt print for the latest sale
                if new_sale_ids:
                    self.print_record_in_browser(sale_id=new_sale_ids[0])

            except ValueError:
                messagebox.showerror("Error", "Invalid numeric format for price or quantity.")

        ttk.Button(sell_win, text="Confirm & Complete Sale", command=confirm_sale).pack(pady=15)

    # ==================== COMPLETE DETAILS WINDOW & PRINT/PDF ====================
    def view_inventory_details(self):
        selected = self.inv_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a mobile from inventory.")
            return
        mobile_id = self.inv_tree.item(selected)['values'][0]
        self.open_complete_details_window(mobile_id=mobile_id)

    def view_sales_details(self):
        selected = self.sales_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a sale record.")
            return
        sale_data = self.sales_tree.item(selected)['values']
        sale_id = sale_data[0]
        self.open_complete_details_window(sale_id=sale_id)

    def open_complete_details_window(self, mobile_id=None, sale_id=None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        if sale_id:
            cursor.execute('''
                SELECT s.sale_id, s.purchaser_name, s.purchaser_cnic, s.purchaser_phone, s.sold_price, s.sold_date,
                       m.id, m.brand, m.model, m.imei, m.price, m.quantity, m.color, m.storage, m.ram, m.battery,
                       m.with_box, m.with_charger, m.condition, m.seller_name, m.seller_cnic, m.seller_phone, m.seller_address,
                       m.img_seller_person, m.img_cnic_back, m.img_cnic_front, m.img_phone_acc
                FROM sales s JOIN mobiles m ON s.mobile_id = m.id
                WHERE s.sale_id = ?
            ''', (sale_id,))
            record = cursor.fetchone()
            is_sale = True
        else:
            cursor.execute('''
                SELECT id, brand, model, imei, price, quantity, color, storage, ram, battery,
                       with_box, with_charger, condition, seller_name, seller_cnic, seller_phone, seller_address,
                       img_seller_person, img_cnic_back, img_cnic_front, img_phone_acc
                FROM mobiles WHERE id = ?
            ''', (mobile_id,))
            record = cursor.fetchone()
            is_sale = False
        conn.close()

        if not record:
            messagebox.showerror("Error", "Record details not found.")
            return

        detail_win = tk.Toplevel(self.root)
        detail_win.title("Complete Mobile & Transaction Details")
        detail_win.geometry("800x700")

        canvas = tk.Canvas(detail_win)
        scrollbar = ttk.Scrollbar(detail_win, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas, padding=15)

        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(content_frame, text=f"📱 {SHOP_NAME}", font=('Helvetica', 14, 'bold'), foreground="#1A365D").pack(pady=5)
        ttk.Label(content_frame, text="Comprehensive Inventory & Transaction Details", font=('Helvetica', 10, 'italic')).pack(pady=2)

        if is_sale:
            s_id, p_name, p_cnic, p_phone, s_price, s_date, m_id, brand, model, imei, price, qty, color, storage, ram, battery, box, charger, condition, s_name, s_cnic, s_phone, s_address, img_s_pers, img_c_back, img_c_front, img_p_acc = record

            info_rows = [
                ("--- SALE RECORD INFORMATION ---", ""),
                ("Sale ID:", f"#{s_id}"),
                ("Sold Date:", str(s_date)),
                ("Purchaser Name:", str(p_name)),
                ("Purchaser CNIC:", str(p_cnic)),
                ("Purchaser Phone:", str(p_phone)),
                ("Final Sold Price:", f"Rs. {s_price:,.0f}" if s_price else "Rs. 0"),
                ("--- MOBILE SPECIFICATIONS ---", ""),
                ("Mobile ID:", f"#{m_id}"),
                ("Brand:", str(brand)),
                ("Model:", str(model)),
                ("IMEI Number:", str(imei)),
                ("Purchase / Base Price:", f"Rs. {price:,.0f}" if price else "Rs. 0"),
                ("Stock Quantity:", str(qty)),
                ("Condition:", str(condition)),
                ("Color:", str(color)),
                ("Storage:", str(storage)),
                ("RAM:", str(ram)),
                ("Battery Health:", f"{battery}%" if battery else "N/A"),
                ("Original Box Included:", "Yes" if box else "No"),
                ("Original Charger Included:", "Yes" if charger else "No"),
                ("--- SELLER INFORMATION (Used Phone) ---", ""),
                ("Seller Name:", str(s_name) if s_name else "N/A (Brand New)"),
                ("Seller CNIC:", str(s_cnic) if s_cnic else "N/A"),
                ("Seller Phone:", str(s_phone) if s_phone else "N/A"),
                ("Seller Address:", str(s_address) if s_address else "N/A")
            ]
        else:
            m_id, brand, model, imei, price, qty, color, storage, ram, battery, box, charger, condition, s_name, s_cnic, s_phone, s_address, img_s_pers, img_c_back, img_c_front, img_p_acc = record

            info_rows = [
                ("--- MOBILE SPECIFICATIONS ---", ""),
                ("Mobile ID:", f"#{m_id}"),
                ("Brand:", str(brand)),
                ("Model:", str(model)),
                ("IMEI Number:", str(imei)),
                ("Purchase Price:", f"Rs. {price:,.0f}" if price else "Rs. 0"),
                ("Stock Quantity:", str(qty)),
                ("Condition:", str(condition)),
                ("Color:", str(color)),
                ("Storage:", str(storage)),
                ("RAM:", str(ram)),
                ("Battery Health:", f"{battery}%" if battery else "N/A"),
                ("Original Box Included:", "Yes" if box else "No"),
                ("Original Charger Included:", "Yes" if charger else "No"),
                ("--- SELLER INFORMATION (Used Phone) ---", ""),
                ("Seller Name:", str(s_name) if s_name else "N/A (Brand New)"),
                ("Seller CNIC:", str(s_cnic) if s_cnic else "N/A"),
                ("Seller Phone:", str(s_phone) if s_phone else "N/A"),
                ("Seller Address:", str(s_address) if s_address else "N/A")
            ]

        txt_widget = tk.Text(content_frame, height=20, width=85, font=('Courier', 9), bg="#F7FAFC", relief='solid', bd=1)
        formatted_text = "\n".join([f"{k:<30} {v}" if v else f"\n{k}" for k, v in info_rows])
        txt_widget.insert('1.0', formatted_text.strip())
        txt_widget.config(state='disabled')
        txt_widget.pack(pady=10)

        ttk.Label(content_frame, text="Attached Verification Images:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=5)
        img_frame = ttk.Frame(content_frame)
        img_frame.pack(fill='x', pady=5)

        images_to_show = [
            ("Seller Person / Owner", img_s_pers),
            ("CNIC Front", img_c_front),
            ("CNIC Back", img_c_back),
            ("Phone with Accessories", img_p_acc)
        ]

        self.loaded_tk_images = []
        for title, img_blob in images_to_show:
            if img_blob:
                try:
                    pil_img = Image.open(io.BytesIO(img_blob))
                    pil_img.thumbnail((150, 110))
                    tk_img = ImageTk.PhotoImage(pil_img)
                    self.loaded_tk_images.append(tk_img)

                    f_box = ttk.LabelFrame(img_frame, text=title, padding=5)
                    f_box.pack(side='left', padx=5, pady=5)
                    lbl_img = ttk.Label(f_box, image=tk_img)
                    lbl_img.pack()
                except Exception:
                    pass

        btn_action_frame = ttk.Frame(content_frame, padding=10)
        btn_action_frame.pack(pady=15)

        if is_sale:
            ttk.Button(btn_action_frame, text="🖨️ Print (Browser)", command=lambda: self.print_record_in_browser(sale_id=sale_id)).pack(side='left', padx=10, ipadx=8, ipady=4)
            ttk.Button(btn_action_frame, text="📄 Save Complete PDF", command=lambda: self.export_complete_sale_pdf_by_id(sale_id)).pack(side='left', padx=10, ipadx=8, ipady=4)
        else:
            ttk.Button(btn_action_frame, text="🖨️ Print (Browser)", command=lambda: self.print_record_in_browser(mobile_id=mobile_id)).pack(side='left', padx=10, ipadx=8, ipady=4)
            ttk.Button(btn_action_frame, text="📄 Save Complete PDF", command=lambda: self.export_complete_inventory_pdf_by_id(mobile_id)).pack(side='left', padx=10, ipadx=8, ipady=4)

        ttk.Button(btn_action_frame, text="❌ Close", command=detail_win.destroy).pack(side='left', padx=10, ipadx=8, ipady=4)

    def print_record_in_browser(self, mobile_id=None, sale_id=None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        if sale_id:
            cursor.execute('''
                SELECT s.sale_id, s.purchaser_name, s.purchaser_cnic, s.purchaser_phone, s.sold_price, s.sold_date,
                       m.id, m.brand, m.model, m.imei, m.price, m.quantity, m.color, m.storage, m.ram, m.battery,
                       m.with_box, m.with_charger, m.condition,
                       m.seller_name, m.seller_cnic, m.seller_phone, m.seller_address,
                       m.img_seller_person, m.img_cnic_back, m.img_cnic_front, m.img_phone_acc
                FROM sales s JOIN mobiles m ON s.mobile_id = m.id
                WHERE s.sale_id = ?
            ''', (sale_id,))
            record = cursor.fetchone()
            is_sale = True
        else:
            cursor.execute('''
                SELECT id, brand, model, imei, price, quantity, color, storage, ram, battery,
                       with_box, with_charger, condition,
                       seller_name, seller_cnic, seller_phone, seller_address,
                       img_seller_person, img_cnic_back, img_cnic_front, img_phone_acc
                FROM mobiles WHERE id = ?
            ''', (mobile_id,))
            record = cursor.fetchone()
            is_sale = False
        conn.close()

        if not record:
            messagebox.showerror("Error", "Record not found.")
            return

        if is_sale:
            (s_id, p_name, p_cnic, p_phone, s_price, s_date,
             m_id, brand, model, imei, price, qty, color, storage, ram, battery,
             box, charger, condition,
             s_name, s_cnic, s_phone, s_address,
             img_s_pers, img_c_back, img_c_front, img_p_acc) = record
            title_str = f"Sales Invoice #{s_id}"
        else:
            (m_id, brand, model, imei, price, qty, color, storage, ram, battery,
             box, charger, condition,
             s_name, s_cnic, s_phone, s_address,
             img_s_pers, img_c_back, img_c_front, img_p_acc) = record
            title_str = f"Inventory Report - Mobile #{m_id}"

        def blob_to_img_html(blob, alt_text, max_w=160, max_h=120):
            if not blob:
                return ""
            try:
                encoded = base64.b64encode(blob).decode('utf-8')
                # Detect simple image type from magic bytes
                mime = "image/jpeg"
                if blob[:8] == b'\x89PNG\r\n\x1a\n':
                    mime = "image/png"
                elif blob[:2] == b'BM':
                    mime = "image/bmp"
                return (
                    f'<div style="display:inline-block; margin:8px; text-align:center; vertical-align:top;">'
                    f'<div style="font-size:11px; font-weight:bold; margin-bottom:4px;">{alt_text}</div>'
                    f'<img src="data:{mime};base64,{encoded}" '
                    f'style="max-width:{max_w}px; max-height:{max_h}px; border:1px solid #cbd5e0;" />'
                    f'</div>'
                )
            except Exception:
                return ""

        logo_html = ""
        if os.path.exists(LOGO_PATH):
            try:
                with open(LOGO_PATH, "rb") as lf:
                    encoded_logo = base64.b64encode(lf.read()).decode('utf-8')
                    logo_html = f'<img src="data:image/png;base64,{encoded_logo}" style="width: 80px; height: 80px; margin-bottom: 6px;" /><br/>'
            except Exception:
                pass

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title_str} - {SHOP_NAME}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
                .header {{ text-align: center; border-bottom: 2px solid #1A365D; padding-bottom: 10px; margin-bottom: 20px; }}
                .header h1 {{ color: #1A365D; margin: 0; font-size: 22px; }}
                .header p {{ margin: 4px 0; font-size: 13px; color: #555; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #cbd5e0; padding: 8px 12px; font-size: 13px; text-align: left; }}
                th {{ background-color: #f7fafc; color: #1a202c; }}
                .section-title {{ font-weight: bold; background-color: #edf2f7; }}
                .images-section {{ margin-top: 16px; page-break-inside: avoid; }}
                .images-section h3 {{ color: #1A365D; font-size: 14px; margin-bottom: 8px; }}
                @media print {{
                    body {{ margin: 0; }}
                    .no-print {{ display: none; }}
                }}
            </style>
        </head>
        <body onload="window.print()">
            <div class="header">
                {logo_html}
                <h1>{SHOP_NAME}</h1>
                <p>📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}</p>
                <h3>{title_str}</h3>
            </div>
            <table>
        """

        if is_sale:
            html_content += f"""
                <tr class="section-title"><td colspan="2">Sale & Purchaser Information</td></tr>
                <tr><td>Sale ID</td><td>#{s_id}</td></tr>
                <tr><td>Sold Date</td><td>{s_date}</td></tr>
                <tr><td>Purchaser Name</td><td>{p_name or 'N/A'}</td></tr>
                <tr><td>Purchaser CNIC</td><td>{p_cnic or 'N/A'}</td></tr>
                <tr><td>Purchaser Phone</td><td>{p_phone or 'N/A'}</td></tr>
                <tr><td>Final Sold Price</td><td><b>Rs. {s_price:,.0f}</b></td></tr>
            """

        html_content += f"""
                <tr class="section-title"><td colspan="2">Mobile Specifications</td></tr>
                <tr><td>Mobile ID</td><td>#{m_id}</td></tr>
                <tr><td>Brand & Model</td><td>{brand} {model}</td></tr>
                <tr><td>IMEI Number</td><td>{imei}</td></tr>
                <tr><td>Purchase Price</td><td>Rs. {price:,.0f}</td></tr>
                <tr><td>Stock Quantity</td><td>{qty}</td></tr>
                <tr><td>Condition</td><td>{condition}</td></tr>
                <tr><td>Color / Storage / RAM</td><td>{color or 'N/A'} / {storage or 'N/A'} / {ram or 'N/A'}</td></tr>
                <tr><td>Battery Health</td><td>{battery if battery else 'N/A'}%</td></tr>
                <tr><td>Accessories Included</td><td>Box: {'Yes' if box else 'No'}, Charger: {'Yes' if charger else 'No'}</td></tr>
            """

        # Seller details + attachments: only on inventory print, NEVER on sales receipt
        if not is_sale:
            html_content += f"""
                <tr class="section-title"><td colspan="2">Seller Information (Used Phone)</td></tr>
                <tr><td>Seller Name</td><td>{s_name if s_name else 'N/A (Brand New)'}</td></tr>
                <tr><td>Seller CNIC</td><td>{s_cnic if s_cnic else 'N/A'}</td></tr>
                <tr><td>Seller Phone</td><td>{s_phone if s_phone else 'N/A'}</td></tr>
                <tr><td>Seller Address</td><td>{s_address if s_address else 'N/A'}</td></tr>
            """

        html_content += """
            </table>
        """

        # Attachments only for inventory (not for sales receipt)
        if not is_sale:
            images_html = (
                blob_to_img_html(img_s_pers, "Seller Person / Owner") +
                blob_to_img_html(img_c_front, "CNIC Front") +
                blob_to_img_html(img_c_back, "CNIC Back") +
                blob_to_img_html(img_p_acc, "Phone with Accessories")
            )
            if images_html.strip():
                html_content += f"""
                <div class="images-section">
                    <h3>Attached Verification Images</h3>
                    {images_html}
                </div>
                """

        html_content += """
        </body>
        </html>
        """

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as f:
                f.write(html_content)
                temp_path = f.name
            webbrowser.open('file://' + temp_path)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to open browser print preview: {str(e)}")

    def export_sale_pdf_by_id(self, sale_id):
        """Standard clean receipt PDF (used for quick automated sales printing)."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT s.sale_id, s.purchaser_name, s.purchaser_cnic, s.purchaser_phone, s.sold_price, s.sold_date,
                              m.brand, m.model, m.imei, m.color, m.storage, m.ram, m.battery, m.condition,
                              m.with_box, m.with_charger
                       FROM sales s JOIN mobiles m ON s.mobile_id = m.id
                       WHERE s.sale_id = ?
                       ''', (sale_id,))
        record = cursor.fetchone()
        conn.close()

        if not record:
            messagebox.showerror("Error", "Sale record not found.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
                                                 initialfile=f"Receipt_Sale_{sale_id}.pdf")
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            elements = []

            if os.path.exists(LOGO_PATH):
                try:
                    elements.append(RLImage(LOGO_PATH, width=60, height=60))
                    elements.append(Spacer(1, 4))
                except Exception:
                    pass

            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor("#1A365D"), alignment=1, spaceAfter=2)
            subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#4A5568"), alignment=1, spaceAfter=10)

            elements.append(Paragraph(SHOP_NAME, title_style))
            elements.append(Paragraph(f"📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}", subtitle_style))
            elements.append(Paragraph("<b>SALES INVOICE & RECEIPT</b>", ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=8)))
            elements.append(Paragraph(f"<b>Receipt ID:</b> #{record[0]} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {record[5]}", ParagraphStyle('Sub', alignment=1, fontSize=8.5, spaceAfter=10)))

            table_data = [
                [Paragraph("<b>Specification / Detail</b>", styles['Normal']), Paragraph("<b>Value</b>", styles['Normal'])],
                ["Brand & Model", f"{record[6]} {record[7]}"],
                ["IMEI Number", str(record[8])],
                ["Color / Storage / RAM", f"{record[9]} / {record[10]} / {record[11]}"],
                ["Battery Health & Condition", f"{record[12]}% ({record[13]})"],
                ["Accessories Included", f"Box: {'Yes' if record[14] else 'No'}, Charger: {'Yes' if record[15] else 'No'}"],
                ["Purchaser Name", record[1]],
                ["Purchaser CNIC", record[2]],
                ["Purchaser Phone", record[3]],
                ["Final Sold Price", f"Rs. {record[4]:,.0f}"]
            ]

            t = Table(table_data, colWidths=[200, 340])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (1,0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0"))
            ]))
            elements.append(t)

            doc.build(elements)
            messagebox.showinfo("Success", f"PDF receipt saved successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF: {str(e)}")

    def export_complete_sale_pdf_by_id(self, sale_id):
        """Comprehensive PDF export from Complete Details including Seller info and attached images."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT s.sale_id,s.purchaser_name,s.purchaser_cnic,s.purchaser_phone,s.sold_price,s.sold_date,
                              m.brand,m.model,m.imei,m.color,m.storage,m.ram,m.battery,m.condition,
                              m.with_box,m.with_charger,m.seller_name,m.seller_phone,m.seller_cnic,m.seller_address,
                              m.img_seller_person,m.img_cnic_back,m.img_cnic_front,m.img_phone_acc
                       FROM sales s JOIN mobiles m ON s.mobile_id = m.id
                       WHERE s.sale_id = ?
                       ''', (sale_id,))
        record = cursor.fetchone()
        conn.close()

        if not record:
            messagebox.showerror("Error", "Sale record not found.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
                                                 initialfile=f"Complete_Sale_Details_{sale_id}.pdf")
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            elements = []

            if os.path.exists(LOGO_PATH):
                try:
                    elements.append(RLImage(LOGO_PATH, width=60, height=60))
                    elements.append(Spacer(1, 4))
                except Exception:
                    pass

            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor("#1A365D"), alignment=1, spaceAfter=2)
            subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#4A5568"), alignment=1, spaceAfter=10)

            elements.append(Paragraph(SHOP_NAME, title_style))
            elements.append(Paragraph(f"📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}", subtitle_style))
            elements.append(Paragraph("<b>COMPLETE SALES & VERIFICATION REPORT</b>", ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=8)))
            elements.append(Paragraph(f"<b>Sale ID:</b> #{record[0]} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {record[5]}", ParagraphStyle('Sub', alignment=1, fontSize=8.5, spaceAfter=10)))

            section_style = ParagraphStyle('SecHead', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#1A365D"), spaceBefore=4, spaceAfter=2)

            table_data = [
                [Paragraph("<b>Specification / Detail</b>", styles['Normal']), Paragraph("<b>Value</b>", styles['Normal'])],
                [Paragraph("<b>--- MOBILE SPECIFICATIONS ---</b>", section_style), ""],
                ["Brand & Model", f"{record[6]} {record[7]}"],
                ["IMEI Number", str(record[8])],
                ["Color / Storage / RAM", f"{record[9] or 'N/A'} / {record[10] or 'N/A'} / {record[11] or 'N/A'}"],
                ["Battery Health & Condition", f"{record[12] if record[12] else 'N/A'}% ({record[13]})"],
                ["Accessories Included", f"Box: {'Yes' if record[14] else 'No'}, Charger: {'Yes' if record[15] else 'No'}"],
                [Paragraph("<b>--- SELLER INFORMATION (Used Phone) ---</b>", section_style), ""],
                ["Seller Name", str(record[16]) if record[16] else "N/A (Brand New)"],
                ["Seller Phone", str(record[17]) if record[17] else "N/A"],
                ["Seller CNIC", str(record[18]) if record[18] else "N/A"],
                ["Seller Address", str(record[19]) if record[19] else "N/A"],
                [Paragraph("<b>--- PURCHASER / SALE INFORMATION ---</b>", section_style), ""],
                ["Purchaser Name", str(record[1]) if record[1] else "N/A"],
                ["Purchaser CNIC", str(record[2]) if record[2] else "N/A"],
                ["Purchaser Phone", str(record[3]) if record[3] else "N/A"],
                ["Final Sold Price", f"Rs. {record[4]:,.0f}" if record[4] else "Rs. 0"]
            ]

            t = Table(table_data, colWidths=[200, 340])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (1, 0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                ('SPAN', (0, 1), (1, 1)),
                ('SPAN', (0, 7), (1, 7)),
                ('SPAN', (0, 12), (1, 12)),
                ('BACKGROUND', (0, 1), (1, 1), colors.HexColor("#EDF2F7")),
                ('BACKGROUND', (0, 7), (1, 7), colors.HexColor("#EDF2F7")),
                ('BACKGROUND', (0, 12), (1, 12), colors.HexColor("#EDF2F7")),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 12))

            elements.append(Paragraph("<b>Attached Verification Images</b>", ParagraphStyle('ImgHead', parent=styles['Heading3'], fontSize=11, textColor=colors.HexColor("#1A365D"), spaceAfter=6)))

            img_blobs = [
                ("Seller Person / Owner", record[20]),
                ("CNIC Front", record[22]),
                ("CNIC Back", record[21]),
                ("Phone with Accessories", record[23])
            ]
            any_img = False
            for img_title, img_data in img_blobs:
                if img_data:
                    try:
                        elements.append(Paragraph(f"• <b>{img_title}:</b>", ParagraphStyle('It', fontSize=8, spaceBefore=4)))
                        img_io = io.BytesIO(img_data)
                        elements.append(RLImage(img_io, width=140, height=100))
                        elements.append(Spacer(1, 4))
                        any_img = True
                    except Exception:
                        pass
            if not any_img:
                elements.append(Paragraph("<i>No verification images attached for this record.</i>", ParagraphStyle('NoneImg', fontSize=8, textColor=colors.HexColor("#718096"))))

            doc.build(elements)
            messagebox.showinfo("Success", f"Complete sales PDF saved successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF: {str(e)}")

    def export_inventory_pdf_by_id(self, mobile_id):
        """Standard inventory PDF report."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT id, brand, model, imei, price, quantity, color, storage, ram, battery,
                              with_box, with_charger, condition
                       FROM mobiles WHERE id = ?
                       ''', (mobile_id,))
        record = cursor.fetchone()
        conn.close()

        if not record:
            messagebox.showerror("Error", "Mobile record not found.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
                                                 initialfile=f"Inventory_Mobile_{mobile_id}.pdf")
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            elements = []

            if os.path.exists(LOGO_PATH):
                try:
                    elements.append(RLImage(LOGO_PATH, width=60, height=60))
                    elements.append(Spacer(1, 4))
                except Exception:
                    pass

            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor("#1A365D"), alignment=1, spaceAfter=2)
            subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#4A5568"), alignment=1, spaceAfter=10)

            elements.append(Paragraph(SHOP_NAME, title_style))
            elements.append(Paragraph(f"📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}", subtitle_style))
            elements.append(Paragraph("<b>INVENTORY ITEM REPORT</b>", ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=8)))
            elements.append(Paragraph(f"<b>Mobile ID:</b> #{record[0]} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", ParagraphStyle('Sub', alignment=1, fontSize=8.5, spaceAfter=10)))

            table_data = [
                [Paragraph("<b>Specification / Detail</b>", styles['Normal']), Paragraph("<b>Value</b>", styles['Normal'])],
                ["Brand & Model", f"{record[1]} {record[2]}"],
                ["IMEI Number", str(record[3])],
                ["Purchase Price", f"Rs. {record[4]:,.0f}"],
                ["Stock Quantity", str(record[5])],
                ["Color / Storage / RAM", f"{record[6]} / {record[7]} / {record[8]}"],
                ["Battery Health & Condition", f"{record[9]}% ({record[12]})"],
                ["Accessories Included", f"Box: {'Yes' if record[10] else 'No'}, Charger: {'Yes' if record[11] else 'No'}"]
            ]

            t = Table(table_data, colWidths=[200, 340])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (1,0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0"))
            ]))
            elements.append(t)

            doc.build(elements)
            messagebox.showinfo("Success", f"Inventory PDF report saved successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF: {str(e)}")

    def export_complete_inventory_pdf_by_id(self, mobile_id):
        """Comprehensive inventory PDF export including Seller info and attached images."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT id, brand, model, imei, price, quantity, color, storage, ram, battery,
                              with_box, with_charger, condition, seller_name, seller_phone, seller_cnic, seller_address,
                              img_seller_person, img_cnic_back, img_cnic_front, img_phone_acc
                       FROM mobiles WHERE id = ?
                       ''', (mobile_id,))
        record = cursor.fetchone()
        conn.close()

        if not record:
            messagebox.showerror("Error", "Mobile record not found.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
                                                 initialfile=f"Complete_Inventory_Mobile_{mobile_id}.pdf")
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            elements = []

            if os.path.exists(LOGO_PATH):
                try:
                    elements.append(RLImage(LOGO_PATH, width=60, height=60))
                    elements.append(Spacer(1, 4))
                except Exception:
                    pass

            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor("#1A365D"), alignment=1, spaceAfter=2)
            subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#4A5568"), alignment=1, spaceAfter=10)

            elements.append(Paragraph(SHOP_NAME, title_style))
            elements.append(Paragraph(f"📍 {SHOP_ADDRESS} | 📞 Phone: {SHOP_PHONE} | ✉️ Email: {SHOP_EMAIL}", subtitle_style))
            elements.append(Paragraph("<b>COMPLETE INVENTORY & VERIFICATION REPORT</b>", ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=8)))
            elements.append(Paragraph(f"<b>Mobile ID:</b> #{record[0]} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", ParagraphStyle('Sub', alignment=1, fontSize=8.5, spaceAfter=10)))

            table_data = [
                [Paragraph("<b>Specification / Detail</b>", styles['Normal']), Paragraph("<b>Value</b>", styles['Normal'])],
                ["Brand & Model", f"{record[1]} {record[2]}"],
                ["IMEI Number", str(record[3])],
                ["Purchase Price", f"Rs. {record[4]:,.0f}"],
                ["Stock Quantity", str(record[5])],
                ["Color / Storage / RAM", f"{record[6]} / {record[7]} / {record[8]}"],
                ["Battery Health & Condition", f"{record[9]}% ({record[12]})"],
                ["Accessories Included", f"Box: {'Yes' if record[10] else 'No'}, Charger: {'Yes' if record[11] else 'No'}"],
                ["Seller Name", str(record[13]) if record[13] else "N/A (Brand New)"],
                ["Seller Phone", str(record[14]) if record[14] else "N/A"],
                ["Seller CNIC", str(record[15]) if record[15] else "N/A"],
                ["Seller Address", str(record[16]) if record[16] else "N/A"]
            ]

            t = Table(table_data, colWidths=[200, 340])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (1,0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0"))
            ]))
            elements.append(t)
            elements.append(Spacer(1, 10))

            img_blobs = [("Seller Person", record[17]), ("CNIC Back", record[18]), ("CNIC Front", record[19]), ("Phone & Acc", record[20])]
            for img_title, img_data in img_blobs:
                if img_data:
                    try:
                        elements.append(Paragraph(f"• <b>{img_title}:</b>", ParagraphStyle('It', fontSize=8)))
                        img_io = io.BytesIO(img_data)
                        elements.append(RLImage(img_io, width=130, height=90))
                        elements.append(Spacer(1, 4))
                    except Exception:
                        pass

            doc.build(elements)
            messagebox.showinfo("Success", f"Complete inventory PDF saved successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MobileShopApp(root)
    root.mainloop()