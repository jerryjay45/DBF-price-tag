"""
price_tag_printer.py — Standalone Price Tag Printer (reads DBF directly)
"""
from __future__ import annotations
import sys, os, json

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QCheckBox, QMessageBox, QFileDialog, QProgressBar,
)
from PyQt6.QtCore import Qt, QRectF, QSizeF, QMarginsF, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPageSize, QPageLayout

AMBER="#F59E0B"; AMBER_DARK="#B45309"; AMBER_BG="#FFFBEB"
DARK="#1C1A17"; DARK_2="#242220"; DARK_4="#3D3A35"; DARK_CARD="#2C2A27"
WHITE="#FFFFFF"; WARM_WHITE="#FAFAF8"; BORDER="#E5E2DC"; BORDER_LIGHT="#F0EDE8"
MUTED="#9C9890"; LABEL_TEXT="#6B6860"; GREEN="#16A34A"; GREEN_LIGHT="#DCFCE7"

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tag_settings.json")
def _load_settings():
    try: return json.load(open(_SETTINGS_FILE))
    except: return {}
def _save_settings(data):
    try:
        cur = _load_settings(); cur.update(data)
        json.dump(cur, open(_SETTINGS_FILE,"w"), indent=2)
    except: pass

_LABEL_SIZES = [
    ("Letter", None, "Letter  (216 × 279 mm)", True),
    ("A4",     None, "A4  (210 × 297 mm)",     True),
    ("Legal",  None, "Legal  (216 × 356 mm)",  True),
]
_PAGE_COLS  = {"A4":3,"Letter":3,"Legal":3}

class _DBFLoader(QThread):
    progress = pyqtSignal(int,int)
    done     = pyqtSignal(list)
    error    = pyqtSignal(str)
    def __init__(self, path, parent=None):
        super().__init__(parent); self.path = path
    def run(self):
        try:
            from dbfread import DBF
        except ImportError:
            self.error.emit("dbfread not installed.\nRun: pip install dbfread"); return
        try:
            recs = list(DBF(self.path, lowernames=True, ignore_missing_memofile=True))
            result = []
            for i,rec in enumerate(recs):
                self.progress.emit(i+1, len(recs))
                r = dict(rec)
                name = (r.get("descrip") or "").strip()
                barcode = str(r.get("code") or "").strip()
                if not name or not barcode: continue
                price = float(r.get("price") or r.get("priceg") or 0)
                gct   = bool(r.get("gct", False))
                disc_rows_raw = []
                for qi,pi in [("quan1","percent1"),("quan2","percent2"),("quan3","percent3")]:
                    qty = float(r.get(qi) or 0)
                    pct = float(r.get(pi) or 0)
                    if qty > 0 and pct > 0:
                        disc_rows_raw.append((int(round(qty)),
                                              round(price*(1-pct/100),2),
                                              f"{round(pct,1):.1f}%"))
                # Deduplicate and sort by min_qty (matches price_tag_tab behaviour)
                seen = set(); disc_rows = []
                for row in sorted(disc_rows_raw, key=lambda r: r[0]):
                    if row[0] not in seen:
                        seen.add(row[0]); disc_rows.append(row)
                result.append({"name":name,"barcode":barcode,"price":price,
                               "gct_applicable":gct,"disc_rows":disc_rows,
                               "group":(r.get("group") or r.get("category") or "").strip()})
            self.done.emit(result)
        except Exception as e:
            self.error.emit(f"Could not read DBF:\n{e}")

def _draw_label(painter, rect, product, options, preview=False):
    show_name=options.get("show_name",True); show_price=options.get("show_price",True)
    name=product.get("name",""); price=product.get("price",0.0)
    gct_ok=product.get("gct_applicable",False)
    disc_rows=product.get("disc_rows",[])
    x=rect.x(); y=rect.y(); w=rect.width(); h=rect.height()
    w_mm=options.get("label_w_mm",50); h_mm=options.get("label_h_mm",30)
    px_per_mm=w/max(w_mm,1)

    name_pt  = max(h_mm*0.38, 7.0)
    price_pt = 15.0
    gct_pt   = max(h_mm*0.28, 5.5)
    disc_pt  = max(h_mm*0.28, 10.5)
    pad=max(2.0*px_per_mm,2.0)

    painter.save(); painter.setClipRect(rect)
    pen_w=max(0.35*px_per_mm,0.8)
    painter.setPen(QPen(QColor("#000000"),pen_w)); painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawRoundedRect(rect.adjusted(pen_w,pen_w,-pen_w,-pen_w),max(1.5*px_per_mm,3.0),max(1.5*px_per_mm,3.0))

    shown_disc  = disc_rows[:2]
    disc_h_each = h * 0.22
    disc_h      = disc_h_each*len(shown_disc) if (show_price and shown_disc) else 0
    name_avail_w = w - pad*2

    name_font = QFont("Arial"); name_font.setPointSizeF(name_pt); name_font.setBold(True)
    painter.setFont(name_font)

    if show_name and name:
        needed_name_h = painter.boundingRect(
            QRectF(0,0,name_avail_w,h*2),
            Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,
            name
        ).height() + pad*0.5
    else:
        needed_name_h = 0

    remaining = h - disc_h - pad*2
    name_h    = min(needed_name_h, remaining*0.45) if show_name else 0
    price_h   = remaining - name_h if show_price else 0

    cur_y = y + pad

    if show_name and name:
        painter.setPen(QColor("#000000"))
        painter.drawText(QRectF(x+pad,cur_y,name_avail_w,name_h),
            Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,name)
        cur_y += name_h

    if show_price:
        price_str=f"${price:.2f}"
        font=QFont("Arial"); font.setPointSizeF(price_pt); font.setBold(True)
        painter.setFont(font); painter.setPen(QColor("#000000"))
        price_px=painter.fontMetrics().horizontalAdvance(price_str)
        painter.drawText(QRectF(x+pad,cur_y,w-pad*2,price_h),
            Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,price_str)
        if gct_ok:
            gf=QFont("Arial"); gf.setPointSizeF(gct_pt); gf.setBold(True)
            painter.setFont(gf); painter.setPen(QColor("#555555"))
            painter.drawText(QRectF(x+pad+price_px+pad*0.4,cur_y+price_h*0.20,
                w-pad*2-price_px-pad,price_h*0.65),
                Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,"+GCT")
        cur_y += price_h

        for (min_qty,disc_price,pct_str) in shown_disc:
            font=QFont("Arial"); font.setPointSizeF(disc_pt); font.setBold(True)
            painter.setFont(font)
            tr=QRectF(x+pad,cur_y,w-pad*2,disc_h_each)
            painter.setPen(QColor("#222222"))
            painter.drawText(tr,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                             f"{min_qty} \u2192 ${disc_price:.2f}")
            painter.setPen(QColor("#444444"))
            painter.drawText(tr,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,
                             f"Discount {pct_str}")
            cur_y += disc_h_each

    painter.restore()


def _draw_barcode_bars(painter,rect,text,preview=False,num_pt=5.0):
    painter.save(); painter.setClipRect(rect)
    bar_h=rect.height()*0.76; num_y=rect.y()+bar_h+rect.height()*0.03
    num_h=rect.height()-bar_h-rect.height()*0.03
    _DB={"0":[1,3,0,2,1,1,0,1,1,1],"1":[1,2,0,2,1,2,0,1,1,1],"2":[1,2,0,2,1,1,0,1,1,2],
         "3":[1,1,0,4,1,1,0,1,1,1],"4":[1,1,0,1,1,3,0,2,1,1],"5":[1,1,0,2,1,2,0,2,1,1],
         "6":[1,1,0,1,1,1,0,4,1,1],"7":[1,1,0,3,1,1,0,1,1,2],"8":[1,1,0,2,1,1,0,3,1,1],
         "9":[1,3,0,1,1,1,0,1,1,2]}
    guard=[1,1,0,1,1,1]; bars=guard[:]
    for ch in text:
        pat=_DB.get(ch,[1,1,0,1,1,1,0,1,1,1])
        for ib,uw in zip(pat[::2],pat[1::2]): bars.append(ib); bars.append(uw)
    bars+=guard
    pairs=list(zip(bars[::2],bars[1::2])); total=sum(u for _,u in pairs)
    unit_w=rect.width()/max(total,1); painter.setPen(Qt.PenStyle.NoPen); cur_x=rect.x()
    for is_bar,units in pairs:
        bw=units*unit_w
        if is_bar:
            painter.setBrush(QBrush(QColor("#000000")))
            painter.drawRect(QRectF(cur_x,rect.y(),max(bw-0.3,0.5),bar_h))
        cur_x+=bw
    nf=QFont("Courier New"); nf.setPointSizeF(num_pt); painter.setFont(nf)
    painter.setPen(QColor("#000000"))
    painter.drawText(QRectF(rect.x(),num_y,rect.width(),num_h),
                     Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,text)
    painter.restore()

class _Preview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self._p=None
        self._o={"show_name":True,"show_price":True,"show_barcode":True,"label_w_mm":50,"label_h_mm":30}
        self.setStyleSheet(f"background:{WARM_WHITE};border:1px solid {BORDER};border-radius:8px;")
        self.setMinimumHeight(170)
    def set_product(self,d): self._p=d; self.update()
    def set_options(self,o):  self._o=o; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._p:
            p.setPen(QColor(MUTED)); p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Select a product to preview"); return
        wm=self._o.get("label_w_mm",50); hm=self._o.get("label_h_mm",30); asp=wm/max(hm,1)
        mg=16; aw=self.width()-mg*2; ah=self.height()-mg*2
        if aw/asp<=ah: lw=aw; lh=aw/asp
        else: lh=ah; lw=ah*asp
        lx=(self.width()-lw)/2; ly=(self.height()-lh)/2
        rect=QRectF(lx,ly,lw,lh)
        p.setBrush(QBrush(QColor(WHITE))); p.setPen(QPen(QColor(AMBER),1.5))
        p.drawRoundedRect(rect,6,6); _draw_label(p,rect,self._p,self._o,preview=True)

def _sec(t):
    l=QLabel(t.upper()); l.setStyleSheet(f"color:{MUTED};font-size:10px;font-weight:700;letter-spacing:1px;"); return l
def _fl(t):
    l=QLabel(t); l.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;"); return l
def _dv():
    d=QFrame(); d.setFrameShape(QFrame.Shape.HLine); d.setStyleSheet(f"background:{BORDER_LIGHT};max-height:1px;border:none;"); return d
def _tog(lbl,chk=True):
    cb=QCheckBox(lbl); cb.setChecked(chk)
    cb.setStyleSheet(f"QCheckBox{{color:{DARK_CARD};font-size:12px;}}QCheckBox::indicator{{width:15px;height:15px;border:1px solid {BORDER};border-radius:3px;background:{WHITE};}}QCheckBox::indicator:checked{{background:{AMBER};border-color:{AMBER};}}")
    return cb
def _abtn(t,h=34):
    b=QPushButton(t); b.setFixedHeight(h); b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"QPushButton{{background:{AMBER};color:white;border:none;border-radius:8px;font-size:12px;font-weight:600;padding:0 16px;}}QPushButton:hover{{background:{AMBER_DARK};}}QPushButton:disabled{{background:{MUTED};color:#aaa;}}"); return b
def _obtn(t,h=32):
    b=QPushButton(t); b.setFixedHeight(h); b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{LABEL_TEXT};border:1.5px solid {BORDER};border-radius:16px;font-size:11px;font-weight:600;padding:0 12px;}}QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}QPushButton:disabled{{color:{MUTED};border-color:{BORDER_LIGHT};}}"); return b
def _tbl():
    return (f"QTableWidget{{background:{WHITE};border:none;font-size:12px;color:{DARK_CARD};}}"
            f"QTableWidget::item{{padding:6px 8px;border-bottom:1px solid {BORDER_LIGHT};}}"
            f"QTableWidget::item:selected{{background:{AMBER_BG};color:{DARK_CARD};}}"
            f"QHeaderView::section{{background:{DARK};color:{AMBER};font-size:11px;font-weight:700;padding:6px 8px;border:none;border-right:1px solid {DARK_4};}}")

class PriceTagPrinter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Price Tag Printer — DBF Edition")
        self.setMinimumSize(1100,680)
        self._all=[]; self._filtered=[]; self._selected=set(); self._map={}
        self._page=0; self._per_page=100; self._total=0
        self._settings=_load_settings(); self._loader=None
        self._build()
        last=self._settings.get("last_dbf_path","")
        if last and os.path.isfile(last): self._load_dbf(last)

    def _build(self):
        cw=QWidget(); self.setCentralWidget(cw); cw.setStyleSheet(f"background:{WARM_WHITE};")
        root=QVBoxLayout(cw); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        # Top bar
        top=QFrame(); top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DARK};border-bottom:2px solid {AMBER};")
        tl=QHBoxLayout(top); tl.setContentsMargins(16,0,16,0); tl.setSpacing(12)
        tl.addWidget(QLabel("🏷  Price Tag Printer",styleSheet="color:white;font-size:16px;font-weight:700;"))
        tl.addStretch()
        self.file_lbl=QLineEdit(); self.file_lbl.setReadOnly(True)
        self.file_lbl.setFixedHeight(32); self.file_lbl.setFixedWidth(400)
        self.file_lbl.setPlaceholderText("No DBF file loaded…")
        self.file_lbl.setStyleSheet(f"QLineEdit{{background:{DARK_2};color:{MUTED};border:1px solid {DARK_4};border-radius:7px;padding:0 10px;font-size:12px;}}")
        tl.addWidget(self.file_lbl)
        br=_abtn("📂  Open DBF",h=32); br.clicked.connect(self._browse); tl.addWidget(br)
        root.addWidget(top)
        self.prog=QProgressBar(); self.prog.setFixedHeight(3); self.prog.setTextVisible(False)
        self.prog.setStyleSheet(f"QProgressBar{{background:{DARK_2};border:none;}}QProgressBar::chunk{{background:{AMBER};}}")
        self.prog.setVisible(False); root.addWidget(self.prog)
        body=QWidget(); bl=QHBoxLayout(body); bl.setContentsMargins(8,8,8,8); bl.setSpacing(8)
        root.addWidget(body,stretch=1)
        split=QSplitter(Qt.Orientation.Horizontal); split.setHandleWidth(4)
        split.setStyleSheet(f"QSplitter::handle{{background:{BORDER};}}"); bl.addWidget(split)
        split.addWidget(self._left()); split.addWidget(self._right()); split.setSizes([700,320])

    def _left(self):
        card=QFrame(); card.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        lay=QVBoxLayout(card); lay.setContentsMargins(12,12,12,12); lay.setSpacing(8)
        lay.addWidget(_sec("Products"))
        # Search with clear button
        sb=QHBoxLayout(); sb.setSpacing(4)
        self.search=QLineEdit(); self.search.setPlaceholderText("🔍  Search by name or barcode…"); self.search.setFixedHeight(34)
        self.search.setStyleSheet(f"QLineEdit{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};border-radius:7px;padding:0 10px;font-size:12px;}}QLineEdit:focus{{border-color:{AMBER};}}")
        self.search.textChanged.connect(self._filter)
        clr_search=QPushButton("✕"); clr_search.setFixedSize(34,34)
        clr_search.setCursor(Qt.CursorShape.PointingHandCursor)
        clr_search.setToolTip("Clear search")
        clr_search.setStyleSheet(f"QPushButton{{background:{BORDER};color:{DARK_CARD};border:none;border-radius:7px;font-size:13px;font-weight:700;}}QPushButton:hover{{background:{AMBER};color:white;}}")
        clr_search.clicked.connect(lambda:(self.search.clear(),self.search.setFocus()))
        sb.addWidget(self.search,stretch=1); sb.addWidget(clr_search)
        lay.addLayout(sb)
        sr=QHBoxLayout(); sr.setSpacing(6)
        sa=_obtn("☑  Select All"); sa.clicked.connect(self._sel_all)
        cl=_obtn("☐  Clear"); cl.clicked.connect(self._clear_sel)
        self.sel_lbl=QLabel("0 selected",styleSheet=f"color:{AMBER_DARK};font-size:12px;font-weight:600;")
        sr.addWidget(sa); sr.addWidget(cl); sr.addStretch(); sr.addWidget(self.sel_lbl); lay.addLayout(sr)
        self.tbl=QTableWidget(); self.tbl.setColumnCount(4)
        self.tbl.setHorizontalHeaderLabels(["","Product","Price","Discounts"])
        hh=self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed); self.tbl.setColumnWidth(0,32)
        hh.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False); self.tbl.setShowGrid(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet(
            f"QTableWidget{{background:{WHITE};border:none;font-size:12px;color:{DARK_CARD};}}"
            f"QTableWidget{{alternate-background-color:#F7F6F3;}}"
            f"QTableWidget::item{{padding:6px 8px;border-bottom:1px solid {BORDER_LIGHT};}}"
            f"QTableWidget::item:selected{{background:{AMBER_BG};color:{DARK_CARD};}}"
            f"QHeaderView::section{{background:{DARK_CARD};color:{AMBER};font-size:11px;"
            f"font-weight:700;padding:6px 8px;border:none;border-right:1px solid #444;}}")
        self.tbl.currentItemChanged.connect(self._row_changed)
        self.tbl.itemChanged.connect(self._chk_changed); lay.addWidget(self.tbl,stretch=1)

        # Pagination
        self._page = 0; self._per_page = 100; self._total = 0
        pg=QHBoxLayout(); pg.setSpacing(8)
        self._pg_prev=_obtn("← Prev"); self._pg_prev.setFixedWidth(80)
        self._pg_prev.clicked.connect(self._prev_page)
        self._pg_lbl=QLabel("",styleSheet=f"color:{MUTED};font-size:10px;")
        self._pg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pg_next=_obtn("Next →"); self._pg_next.setFixedWidth(80)
        self._pg_next.clicked.connect(self._next_page)
        pg.addStretch(); pg.addWidget(self._pg_prev); pg.addWidget(self._pg_lbl)
        pg.addWidget(self._pg_next); pg.addStretch()
        lay.addLayout(pg)
        return card

    def _right(self):
        card=QFrame(); card.setFixedWidth(320)
        card.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        lay=QVBoxLayout(card); lay.setContentsMargins(14,14,14,14); lay.setSpacing(10)
        lay.addWidget(_sec("Label Preview"))
        self.preview=_Preview(); self.preview.setFixedHeight(170); lay.addWidget(self.preview)
        lay.addWidget(_dv()); lay.addWidget(_sec("Label / Page Size"))
        self.size_combo=QComboBox(); self.size_combo.setFixedHeight(34)
        self.size_combo.setStyleSheet(f"QComboBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};border-radius:7px;padding:0 10px;font-size:12px;}}QComboBox:focus{{border-color:{AMBER};}}QComboBox::drop-down{{border:none;width:20px;}}")
        for e in _LABEL_SIZES: self.size_combo.addItem(e[2],e)
        self.size_combo.setCurrentIndex(self._settings.get("last_size_index",5))
        self.size_combo.currentIndexChanged.connect(self._upd_prev); lay.addWidget(self.size_combo)
        self.cols_row=QWidget(); self.cols_row.setVisible(False)
        cr=QHBoxLayout(self.cols_row); cr.setContentsMargins(0,0,0,0); cr.setSpacing(8)
        cr.addWidget(_fl("Labels per Row:"))
        self.cols_spin=QSpinBox(); self.cols_spin.setRange(1,6); self.cols_spin.setValue(self._settings.get("last_cols",3))
        self.cols_spin.setFixedHeight(32); self.cols_spin.setFixedWidth(60)
        self.cols_spin.setStyleSheet(f"QSpinBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};border-radius:7px;padding:0 8px;font-size:12px;}}QSpinBox:focus{{border-color:{AMBER};}}")
        cr.addWidget(self.cols_spin); cr.addStretch(); lay.addWidget(self.cols_row)
        lay.addWidget(_dv()); lay.addWidget(_sec("Show on Label"))
        self.chk_name=_tog("Product Name"); self.chk_price=_tog("Price")
        for c in (self.chk_name,self.chk_price):
            c.stateChanged.connect(self._upd_prev); lay.addWidget(c)
        note=QLabel("  GCT and discounts shown automatically when present in DBF.",styleSheet=f"color:{MUTED};font-size:10px;"); note.setWordWrap(True); lay.addWidget(note)
        lay.addWidget(_dv())
        cr2=QHBoxLayout(); cr2.setSpacing(8); cr2.addWidget(_fl("Copies per product:"))
        self.copies=QSpinBox(); self.copies.setRange(1,999); self.copies.setValue(1)
        self.copies.setFixedHeight(32); self.copies.setFixedWidth(70)
        self.copies.setStyleSheet(f"QSpinBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};border-radius:7px;padding:0 8px;font-size:12px;}}QSpinBox:focus{{border-color:{AMBER};}}")
        cr2.addWidget(self.copies); cr2.addStretch(); lay.addLayout(cr2); lay.addStretch()
        self.status=QLabel("",styleSheet=f"color:{GREEN};font-size:11px;"); self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(self.status)
        self.print_btn=QPushButton("🖨  Preview && Print"); self.print_btn.setFixedHeight(42)
        self.print_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.print_btn.setEnabled(False)
        self.print_btn.setStyleSheet(f"QPushButton{{background:{AMBER};color:white;border:none;border-radius:8px;font-size:14px;font-weight:700;}}QPushButton:hover{{background:{AMBER_DARK};}}QPushButton:disabled{{background:{MUTED};color:white;}}")
        self.print_btn.clicked.connect(lambda:self._do_print(False)); lay.addWidget(self.print_btn)
        self.pdf_btn=QPushButton("💾  Save as PDF"); self.pdf_btn.setFixedHeight(34)
        self.pdf_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.pdf_btn.setEnabled(False)
        self.pdf_btn.setStyleSheet(f"QPushButton{{background:{GREEN_LIGHT};color:{GREEN};border:none;border-radius:7px;font-size:12px;font-weight:600;}}QPushButton:hover{{background:{GREEN};color:white;}}QPushButton:disabled{{background:{WARM_WHITE};color:{MUTED};}}")
        self.pdf_btn.clicked.connect(lambda:self._do_print(True)); lay.addWidget(self.pdf_btn)
        return card

    def _browse(self):
        last=self._settings.get("last_dbf_path","")
        path,_=QFileDialog.getOpenFileName(self,"Open DBF Stock File",os.path.dirname(last) if last else "","DBF Files (*.dbf *.DBF);;All Files (*)")
        if path: self._load_dbf(path)

    def _load_dbf(self,path):
        self.file_lbl.setText(os.path.basename(path))
        self.file_lbl.setStyleSheet(f"QLineEdit{{background:{DARK_2};color:{AMBER};border:1px solid {AMBER};border-radius:7px;padding:0 10px;font-size:12px;}}")
        self.prog.setVisible(True); self.prog.setValue(0); self.status.setText("Loading…")
        self._loader=_DBFLoader(path,self)
        self._loader.progress.connect(lambda d,t:(self.prog.setMaximum(t),self.prog.setValue(d)))
        self._loader.done.connect(self._loaded)
        self._loader.error.connect(lambda e:(self.prog.setVisible(False),self.status.setText(""),QMessageBox.critical(self,"Load Error",e)))
        self._loader.start(); _save_settings({"last_dbf_path":path})

    def _loaded(self,products):
        self._all=products; self._map={p["barcode"]:p for p in products}
        self._selected.clear(); self.prog.setVisible(False)
        self._page=0
        self.status.setText(f"Loaded {len(products):,} products"); self._filter()

    def _filter(self):
        q=self.search.text().strip().lower()
        self._filtered=[p for p in self._all if not q or q in p["name"].lower() or q in p["barcode"].lower()]
        self._total=len(self._filtered)
        self._page=0; self._fill_tbl()

    def _prev_page(self):
        if self._page > 0: self._page -= 1; self._fill_tbl()

    def _next_page(self):
        pages=max(1,(self._total+self._per_page-1)//self._per_page)
        if self._page < pages-1: self._page += 1; self._fill_tbl()

    def _fill_tbl(self):
        t=self.tbl; t.blockSignals(True); t.setRowCount(0)
        pages=max(1,(self._total+self._per_page-1)//self._per_page)
        start=self._page*self._per_page
        page_products=self._filtered[start:start+self._per_page]
        for row,p in enumerate(page_products):
            t.insertRow(row); t.setRowHeight(row,30)
            chk=QTableWidgetItem()
            chk.setData(Qt.ItemDataRole.UserRole,p["barcode"])
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Checked if p["barcode"] in self._selected else Qt.CheckState.Unchecked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter); t.setItem(row,0,chk)
            ni=QTableWidgetItem(p["name"]); ni.setData(Qt.ItemDataRole.UserRole+1,p["barcode"]); t.setItem(row,1,ni)
            pi=QTableWidgetItem(f"${p['price']:.2f}"+(" +GCT" if p["gct_applicable"] else ""))
            pi.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            pi.setForeground(QColor(AMBER_DARK)); t.setItem(row,2,pi)
            disc=p.get("disc_rows",[])
            di=QTableWidgetItem(f"{disc[0][0]}+ @ {disc[0][2]}" if disc else "—")
            di.setForeground(QColor(GREEN if disc else MUTED))
            di.setTextAlignment(Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter); t.setItem(row,3,di)
        t.blockSignals(False)
        self._pg_lbl.setText(f"Page {self._page+1} of {pages}  ({self._total:,})")
        self._pg_prev.setEnabled(self._page>0)
        self._pg_next.setEnabled(self._page<pages-1)
        self._upd_sel()

    def _chk_changed(self,item):
        if item.column()!=0: return
        bc=item.data(Qt.ItemDataRole.UserRole)
        if bc is None: return
        if item.checkState()==Qt.CheckState.Checked: self._selected.add(bc)
        else: self._selected.discard(bc)
        self._upd_sel()

    def _row_changed(self,cur,_prev):
        if not cur: return
        it=self.tbl.item(cur.row(),0)
        if not it: return
        p=self._map.get(it.data(Qt.ItemDataRole.UserRole))
        if p: self.preview.set_product(p); self._upd_prev()

    def _sel_all(self):
        t=self.tbl; t.blockSignals(True)
        for r in range(t.rowCount()):
            it=t.item(r,0)
            if it: self._selected.add(it.data(Qt.ItemDataRole.UserRole)); it.setCheckState(Qt.CheckState.Checked)
        t.blockSignals(False); self._upd_sel()

    def _clear_sel(self):
        t=self.tbl; t.blockSignals(True); self._selected.clear()
        for r in range(t.rowCount()):
            it=t.item(r,0)
            if it: it.setCheckState(Qt.CheckState.Unchecked)
        t.blockSignals(False); self._upd_sel()

    def _upd_sel(self):
        n=len(self._selected); self.sel_lbl.setText(f"{n} selected")
        self.print_btn.setEnabled(n>0); self.pdf_btn.setEnabled(n>0)

    def _upd_prev(self):
        entry=self.size_combo.currentData()
        if not entry: return
        w_val,h_val,_,is_page=entry
        w_mm=62 if is_page else w_val; h_mm=35 if is_page else h_val
        self.cols_row.setVisible(is_page)
        self.preview.set_options({"show_name":self.chk_name.isChecked(),"show_price":self.chk_price.isChecked(),
                                   "label_w_mm":w_mm,"label_h_mm":h_mm})
        _save_settings({"last_size_index":self.size_combo.currentIndex(),"last_cols":self.cols_spin.value()})

    def _do_print(self,save_pdf):
        if not self._selected: return
        job=[]; 
        for bc in self._selected:
            p=self._map.get(bc)
            if p:
                for _ in range(self.copies.value()): job.append(p)
        if not job: return
        entry=self.size_combo.currentData()
        if not entry: return
        w_val,h_val,_,is_page=entry
        opts={"show_name":self.chk_name.isChecked(),"show_price":self.chk_price.isChecked()}
        try:
            from PyQt6.QtPrintSupport import QPrinter,QPrintPreviewDialog
            printer=QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setColorMode(QPrinter.ColorMode.GrayScale)
            sm={"A4":QPageSize.PageSizeId.A4,"Letter":QPageSize.PageSizeId.Letter,"Legal":QPageSize.PageSizeId.Legal}
            printer.setPageLayout(QPageLayout(QPageSize(sm.get(str(w_val),QPageSize.PageSizeId.Letter)),QPageLayout.Orientation.Portrait,QMarginsF(8,8,8,8),QPageLayout.Unit.Millimeter))
            lw=62; lh=30; cols=self.cols_spin.value()
            do=dict(opts,label_w_mm=lw,label_h_mm=lh)
            if save_pdf:
                pp,_=QFileDialog.getSaveFileName(self,"Save Labels as PDF","labels.pdf","PDF Files (*.pdf)")
                if not pp: return
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat); printer.setOutputFileName(pp)
                self._render(printer,job,lw,lh,cols,is_page,do)
                self.status.setText(f"✅  Saved {len(job)} label(s) to PDF.")
            else:
                dlg=QPrintPreviewDialog(printer,self); dlg.setWindowTitle("Price Tag Preview")
                # paintRequested passes a QPainter, not QPrinter — capture printer separately
                def _paint(_printer=printer, _job=job, _lw=lw, _lh=lh,
                           _cols=cols, _is_page=is_page, _do=do):
                    self._render(_printer, _job, _lw, _lh, _cols, _is_page, _do)
                dlg.paintRequested.connect(lambda _: _paint())
                dlg.resize(1000,700); dlg.exec()
                self.status.setText(f"✅  Sent {len(job)} label(s) to printer.")
        except Exception as e:
            self.status.setText(f"❌  {e}"); import traceback; traceback.print_exc()

    def _render(self,printer,job,lw,lh,cols,is_page,opts):
        from PyQt6.QtPrintSupport import QPrinter
        painter = QPainter()
        if not painter.begin(printer):
            return
        try:
            pr=printer.pageRect(QPrinter.Unit.DevicePixel); dpi=printer.resolution(); ppm=dpi/25.4
            lw_px=lw*ppm; lh_px=lh*ppm; gap=3*ppm
            x0=pr.left(); y0=pr.top(); col=0; ry=y0
            for i,d in enumerate(job):
                _draw_label(painter,QRectF(x0+col*(lw_px+gap),ry,lw_px,lh_px),d,opts)
                col+=1
                if col>=cols:
                    col=0; ry+=lh_px+gap
                    if ry+lh_px>pr.bottom() and i<len(job)-1: printer.newPage(); ry=y0
        finally:
            painter.end()

def main():
    app=QApplication(sys.argv); app.setApplicationName("Price Tag Printer"); app.setStyle("Fusion")
    win=PriceTagPrinter(); win.show(); sys.exit(app.exec())

if __name__=="__main__": main()
