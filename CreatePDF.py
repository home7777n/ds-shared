# -*- coding: utf-8 -*-
"""
CreatePDF.py — 依舊版 AI_Agent.pdf 實測規格重寫
所有參數都來自 AI_Agent.md §2.2「舊版 PDF 實測規格」章節
"""
import re
import tempfile
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from fontTools.ttLib import TTFont as FTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import table__g_l_y_f
from fontTools.ttLib.tables._l_o_c_a import table__l_o_c_a
from fontTools.ttLib.tables._m_a_x_p import table__m_a_x_p

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (DictionaryObject, NameObject, NumberObject,
                           ArrayObject, FloatObject, NullObject)


# ═══════════════════════════════════════════════════════════════════════════════
# 三專案共用機制(v6.21 / 2026-06-28 新增)— 雙安企業共用系統
# ───────────────────────────────────────────────────────────────────────────────
# 本檔為三專案(超高壓導線延放線 / 預定施工進度表 / 圖片校正)共用正本。
# 渲染規則、驗證邏輯、字型、預設檔名三專案完全一致,直接共用;
# 唯一專案差異 = PDF metadata 的 Title 與 Subject 兩欄,改由同層設定檔讀取。
#
# 設定檔:pdf_meta.cfg(放在「被轉換的 md 檔同一個資料夾」)
#   格式(極簡,一行一欄,# 開頭為註解):
#       Title=AI_Agent
#       Subject=超高壓導線延放線計算系統
#   Author 三專案固定為「雙安企業有限公司」,不開放設定。
#
# 找不到設定檔 / 找不到某欄 → 自動 fallback 回超高壓專案原值,
# 確保超高壓專案行為與 v6.21 完全一致(零變動)。
# ═══════════════════════════════════════════════════════════════════════════════

# fallback 預設值(= 超高壓專案原本寫死的值)
_DEFAULT_PDF_TITLE = "AI_Agent"
_DEFAULT_PDF_AUTHOR = "雙安企業有限公司"
_DEFAULT_PDF_SUBJECT = "超高壓導線延放線計算系統"


def load_pdf_meta(near_path):
    """讀取 near_path 同層的 pdf_meta.cfg,回傳 (title, author, subject)。

    near_path 通常是 md 檔路徑;會找它所在資料夾的 pdf_meta.cfg。
    讀不到檔案或某欄缺漏 → 該欄 fallback 回超高壓專案預設值。
    Author 固定不從設定檔讀(三專案皆為雙安企業有限公司)。
    """
    import os
    title = _DEFAULT_PDF_TITLE
    subject = _DEFAULT_PDF_SUBJECT
    try:
        base_dir = os.path.dirname(os.path.abspath(near_path))
        cfg_path = os.path.join(base_dir, "pdf_meta.cfg")
        if os.path.isfile(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip().lower()
                    val = val.strip()
                    if not val:
                        continue
                    if key == "title":
                        title = val
                    elif key == "subject":
                        subject = val
    except Exception as e:
        # 設定檔讀取失敗不應中斷 PDF 產生,直接用預設值
        import sys
        sys.stderr.write(f"  [pdf_meta.cfg 讀取跳過,用預設值] {e}\n")
    return title, _DEFAULT_PDF_AUTHOR, subject


# ========== 頁面(實測舊版) ==========
PAGE_W, PAGE_H = A4
MARGIN_L = 50.0
MARGIN_R_X = 545.3        # 實測文字右緣
MARGIN_Y_H2_TOP = 781.9   # 實測 H2 上方分隔線 y
MARGIN_B = 37.0
USABLE_W = MARGIN_R_X - MARGIN_L
Y_TOP = PAGE_H - 60       # 內容從此開始(H2 上線於此)

# ========== 字級(實測) ==========
FONT_H1 = 17              # 封面主標(舊版第一頁大標)
FONT_H2 = 15              # 章節大標
FONT_H3 = 13              # 分節標題
FONT_H4 = 11              # 粗體小節
FONT_BODY = 10            # 內文 / bullet
FONT_CODE = 9             # 表格 / 程式碼 / 頁碼

# ========== 行距(實測) ==========
LINE_H_BODY = 15          # 內文、bullet
LINE_H_CODE = 13          # 程式碼
LINE_H_TABLE = 18         # 表格列高(固定)
H2_TOP_TO_TITLE = 18      # 上線到標題 baseline(舊版實測:上線→標題頂 4.8pt + 字高 15pt ≈ 19.8)
H2_TITLE_TO_BOT = 8       # 標題 baseline 到下線(舊版實測:標題底→下線 6.2pt)
H2_BOT_TO_BODY = 20       # 下線到首段
H3_TOP_GAP = 10           # H3 上方空間
H3_TO_BODY = 8            # H3 到內文
H4_TOP_GAP = 8
H4_TO_BODY = 6

# ========== 顏色(實測) ==========
COLOR_TEXT = (0, 0, 0)                     # 主文黑色
COLOR_H2_LINE = (0.6, 0.6, 0.6)           # H2 上下分隔線
COLOR_TABLE_HEADER_BG = (0.92, 0.92, 0.94)
COLOR_TABLE_HEADER_BORDER = (0.6, 0.6, 0.6)
COLOR_TABLE_BODY_BORDER = (0.7, 0.7, 0.75)
COLOR_CODE_BG = (0.95, 0.95, 0.96)
COLOR_LINK = (0.1, 0.3, 0.7)              # 連結藍(實測)
COLOR_FOOTER = (0.4, 0.4, 0.4)             # 頁碼灰(實測 0.4)


# ========== 字型轉換 ==========
def extract_and_convert(ttc_path, subfont_index=0):
    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
    tmp.close()
    ft = FTFont(ttc_path, fontNumber=subfont_index)
    if "CFF " in ft or "CFF2" in ft:
        glyph_order = ft.getGlyphOrder()
        cff_key = "CFF " if "CFF " in ft else "CFF2"
        cff = ft[cff_key].cff
        top_dict = cff[cff.fontNames[0]]
        char_strings = top_dict.CharStrings
        glyphs = {}
        for gn in glyph_order:
            pen = TTGlyphPen(None)
            char_strings[gn].draw(pen)
            glyphs[gn] = pen.glyph()
        glyf = table__g_l_y_f()
        glyf.glyphs = glyphs
        ft["glyf"] = glyf
        ft["loca"] = table__l_o_c_a()
        if "head" in ft:
            ft["head"].indexToLocFormat = 1
        maxp = table__m_a_x_p()
        maxp.tableVersion = 0x00010000
        maxp.numGlyphs = len(glyph_order)
        mp, mc, mcomp = 0, 0, 0
        for g in glyphs.values():
            if g.isComposite():
                if hasattr(g, "components"):
                    mcomp = max(mcomp, len(g.components))
            else:
                n = len(g.coordinates) if hasattr(g, "coordinates") and g.coordinates else 0
                mp = max(mp, n)
                c = g.numberOfContours if hasattr(g, "numberOfContours") else 0
                mc = max(mc, c)
        maxp.maxPoints = mp
        maxp.maxContours = mc
        maxp.maxCompositePoints = 0
        maxp.maxCompositeContours = 0
        maxp.maxZones = 2
        maxp.maxTwilightPoints = 0
        maxp.maxStorage = 0
        maxp.maxFunctionDefs = 0
        maxp.maxInstructionDefs = 0
        maxp.maxStackElements = 0
        maxp.maxSizeOfInstructions = 0
        maxp.maxComponentElements = mcomp
        maxp.maxComponentDepth = 0
        ft["maxp"] = maxp
        if "CFF " in ft:
            del ft["CFF "]
        if "CFF2" in ft:
            del ft["CFF2"]
        ft.sfntVersion = "\x00\x01\x00\x00"
        # v6.18 / 2026-05-15:確保 glyf.glyphOrder 跟 glyphs 一致(後續修補用)
        ft["glyf"].glyphOrder = list(ft.getGlyphOrder())

    # v6.18 / 2026-05-15:Yu Gothic 把 \\ (U+005C) glyph 畫成 ¥ 日圓符號歷史包袱
    # 直接覆寫 backslash glyph 形狀為 / 的水平鏡像
    # 注意:此修補在 CFF/TrueType 兩種字型都要做(Yu Gothic UI 是 TrueType)
    _fix_backslash_glyph(ft)

    ft.save(tmp.name)
    return tmp.name


def _fix_backslash_glyph(ft):
    """v6.18 / 2026-05-15:覆寫日系字型 backslash glyph 為真實反斜線

    Yu Gothic / MS Gothic / Meiryo 等日系字型把 U+005C glyph 畫成 ¥(日圓符號),
    這是 JIS X 0201 歷史包袱。在 CJK 路徑顯示時 C:\\Windows\\Fonts 變成 C:¥Windows¥Fonts。

    做法:直接覆寫該 glyph 形狀為 / 的水平鏡像(真實反斜線)

    副作用:¥ 字符(U+00A5)在此字型內也共用同一 glyph,會一起變成反斜線。
    對技術文件來說可接受(幾乎不會用到日圓符號)。
    """
    try:
        cmap = ft.getBestCmap()
        gn_bs = cmap.get(0x005C)
        gn_slash = cmap.get(0x002F)
        if not gn_bs or not gn_slash:
            return

        glyf = ft["glyf"]
        hmtx = ft["hmtx"]
        slash_g = glyf[gn_slash]
        slash_w, slash_lsb = hmtx[gn_slash]

        if slash_g.numberOfContours <= 0:
            return

        # 做 / 的水平鏡像
        import copy
        new_g = copy.deepcopy(slash_g)
        if new_g.coordinates is not None:
            coords = new_g.coordinates
            xs = [c[0] for c in coords]
            x_mid = (min(xs) + max(xs)) // 2
            for i in range(len(coords)):
                x, y = coords[i]
                coords[i] = (2 * x_mid - x, y)
            new_g.recalcBounds(glyf)

        # 直接覆寫(同時影響 \\ 跟 ¥,可接受)
        glyf[gn_bs] = new_g
        hmtx[gn_bs] = (slash_w, slash_lsb)
    except Exception as e:
        print(f"  [backslash glyph 修補] 跳過: {e}")


_fonts_registered = False
_yu_cmap = set()        # v6.19 / 2026-05-17:游黑體支援的 codepoint 集合(逐字 fallback 用)
_noto_cmap = set()      # v6.19 / 2026-05-17:Noto 補字型支援的 codepoint 集合
_has_noto_fallback = False  # v6.19 / 2026-05-17:是否有 Noto 補字型可用


def register_fonts():
    """v6.18 / 2026-05-14 改用游黑體(Yu Gothic)
    v6.19 / 2026-05-17 加 Noto fallback:主字型 cmap 沒的字符(查/踩/夠/值/啟 等繁體)
                       用 Noto Sans CJK TC 補渲染。Win10/11 2025-03 D 補丁起 Noto 內建。
    v6.21 / 2026-06-23 改用原漾黑丹體(源樣黑體 TC 丹版,GenYoGothic2TC,SIL OFL 1.1):
                       內文 = L 細體、標題/反白 = B 粗體(真體,不偽粗)。游黑體降為次選。

    主字型 alias:NotoCJK / NotoCJK-Bold(歷史命名,實際嵌原漾黑丹體)
    補字型 alias:NotoFallback / NotoFallback-Bold(實際嵌 Noto Sans CJK TC)
    """
    global _fonts_registered, _yu_cmap, _noto_cmap, _has_noto_fallback
    if _fonts_registered:
        return

    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _local_fonts = [
        os.path.join(_here, "fonts"),
        os.path.join(_here, "..", "fonts"),
        "/home/claude/fonts",        # v6.21 / 2026-06-28:對齊 AI_Agent.md 接手規則的 GitHub 抓取目標
        "/home/claude/work/fonts",
        "/mnt/user-data/uploads",
        "/mnt/project",              # v6.21 / 2026-06-28:知識庫若放字型也能直接讀
    ]

    # ===== 主字型(原漾黑丹體 = 源樣黑體 TC 丹版,v6.21 / 2026-06-23 改用)候選 =====
    # 內文 = GenYoGothic2TC-L(細體 L);標題/反白 = GenYoGothic2TC-B(粗體 B,真體,不偽粗)
    # SIL OFL 1.1 授權,可商用/可嵌入/可隨 EXE 散布。OTF/CFF 格式由 extract_and_convert 轉 TrueType。
    # 游黑體保留為次選(舊環境相容),Noto 為最終 fallback。
    candidates = []
    for fdir in _local_fonts:
        if os.path.isdir(fdir):
            for r_name, b_name in [
                # 原漾黑丹體(優先)
                ("GenYoGothic2TC-L.otf", "GenYoGothic2TC-B.otf"),
                # 游黑體(次選,舊環境相容)
                ("YUGOTHM.TTC", "YUGOTHB.TTC"),
                ("YuGothM.ttc", "YuGothB.ttc"),
                ("yugothm.ttc", "yugothb.ttc"),
                ("YUGOTHR.TTC", "YUGOTHB.TTC"),
                ("YuGothR.ttc", "YuGothB.ttc"),
                ("yugothr.ttc", "yugothb.ttc"),
            ]:
                candidates.append((
                    os.path.join(fdir, r_name),
                    os.path.join(fdir, b_name),
                ))
    candidates += [
        # 原漾黑丹體:工程師端隨程式帶字型資料夾(EXE 同層 原漾黑丹體\)
        (r"原漾黑丹體\GenYoGothic2TC-L.otf",  r"原漾黑丹體\GenYoGothic2TC-B.otf"),
        # 游黑體(次選,舊環境相容)
        (r"C:\Windows\Fonts\YuGothM.ttc",  r"C:\Windows\Fonts\YuGothB.ttc"),
        (r"C:\Windows\Fonts\yugothm.ttc",  r"C:\Windows\Fonts\yugothb.ttc"),
        (r"C:\Windows\Fonts\YuGothR.ttc",  r"C:\Windows\Fonts\YuGothB.ttc"),
        (r"C:\Windows\Fonts\yugothr.ttc",  r"C:\Windows\Fonts\yugothb.ttc"),
        ("/Library/Fonts/YuGothic.ttc", "/Library/Fonts/YuGothicBold.ttc"),
        # Linux 退化路徑:沒原漾黑/游黑體時直接用 Noto 當主字型(主+補同源,等於沒 fallback 但能跑)
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
    ]

    # v6.21 / 115/09/10:改為「內文字型存在即採用」,粗體檔缺席不整組退回下一候選。
    # 舊邏輯是 L+B 都在才採用,但工程師端 原漾黑丹體\ 只放 L 與等寬版
    # (115/06/28 裁示捨棄 B)→ 有 L 也會一路退到 Noto,整份文件失去原漾黑。
    # 對齊該裁示:B 缺席 → 粗體 alias 指向 L(標題不偽粗,靠字級區分)。
    sans_ttc = None
    bold_ttc = None
    for reg, bld in candidates:
        if os.path.exists(reg):
            sans_ttc = reg
            bold_ttc = bld if os.path.exists(bld) else reg
            if bold_ttc == reg:
                print(f"[CreatePDF] 粗體字型缺席 -> 標題改用內文字重(不偽粗)")
            break

    print(f"[CreatePDF] 主字型: {sans_ttc}")
    if sans_ttc is None:
        raise RuntimeError(
            "找不到可用字型!請安裝其中之一:\n"
            " - 原漾黑丹體(源樣黑體 TC 丹版 L+B,放程式同層 原漾黑丹體\\ 資料夾)\n"
            " - Windows: 游黑體(系統內建,Windows 10+)\n"
            " - macOS:  游黑體(系統內建)\n"
            " - Linux:  apt install fonts-noto-cjk")

    # ===== 補字型(Noto Sans CJK)候選 =====
    noto_reg_paths = []
    for fdir in _local_fonts:
        if os.path.isdir(fdir):
            for n in ["NotoSansCJK-Regular.ttc", "NotoSansTC-Regular.otf"]:
                noto_reg_paths.append(os.path.join(fdir, n))
    noto_reg_paths += [
        r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
        r"C:\Windows\Fonts\NotoSansTC-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    noto_bld_paths = []
    for fdir in _local_fonts:
        if os.path.isdir(fdir):
            for n in ["NotoSansCJK-Bold.ttc", "NotoSansTC-Bold.otf"]:
                noto_bld_paths.append(os.path.join(fdir, n))
    noto_bld_paths += [
        r"C:\Windows\Fonts\NotoSansCJK-Bold.ttc",
        r"C:\Windows\Fonts\NotoSansTC-Bold.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]

    noto_reg = next((p for p in noto_reg_paths if os.path.exists(p)), None)
    noto_bld = next((p for p in noto_bld_paths if os.path.exists(p)), None)

    # 主字型已退化到 Noto 時(Linux 沙箱),不重複當 fallback
    if noto_reg == sans_ttc:
        noto_reg = None
        noto_bld = None

    if noto_reg is None or noto_bld is None:
        print(f"[CreatePDF] Noto 補字型: 未找到 -> 游黑體不支援的字符會渲染為豆腐字")
        print(f"  Win10/11 需安裝 2025-03 D 補丁,或手動下載 Noto Sans CJK")
        _has_noto_fallback = False
    else:
        print(f"[CreatePDF] Noto 補字型: {noto_reg}")
        _has_noto_fallback = True

    def _find_subfont(ttc_path, want_bold, prefer_tc=False):
        """v6.19 / 2026-05-17 加 prefer_tc 參數:Noto 補字型優先找 TC subfont
        v6.21 / 2026-06-23:原漾黑為 OTF 單檔(非 .ttc),index 恆為 0。"""
        # 原漾黑丹體 = OTF 單一字型檔,沒有 subfont,直接回 0
        if str(ttc_path).lower().endswith(".otf"):
            return 0
        if prefer_tc:
            for i in range(30):
                try:
                    ft = FTFont(ttc_path, fontNumber=i)
                    name = (ft["name"].getDebugName(4) or "")
                    if "TC" in name:
                        if want_bold and "Bold" in name:
                            return i
                        if not want_bold and "Bold" not in name:
                            return i
                except Exception:
                    break
        for i in range(30):
            try:
                ft = FTFont(ttc_path, fontNumber=i)
                name = (ft["name"].getDebugName(4) or "")
                if "Yu Gothic UI" in name:
                    if want_bold and ("Bold" in name) and ("Semibold" not in name):
                        return i
                    if not want_bold and name == "Yu Gothic UI Regular":
                        return i
            except Exception:
                break
        for i in range(30):
            try:
                ft = FTFont(ttc_path, fontNumber=i)
                name = (ft["name"].getDebugName(4) or "")
                if "Yu Gothic" in name and "UI" not in name:
                    if want_bold and "Bold" in name:
                        return i
                    if not want_bold and "Regular" in name:
                        return i
                    if not want_bold and "Medium" in name:
                        return i
            except Exception:
                break
        for i in range(30):
            try:
                ft = FTFont(ttc_path, fontNumber=i)
                name = (ft["name"].getDebugName(4) or "")
                if "TC" in name:
                    return i
            except Exception:
                break
        return 0

    reg_idx = _find_subfont(sans_ttc, want_bold=False)
    bld_idx = _find_subfont(bold_ttc, want_bold=True)

    try:
        _r_ft = FTFont(sans_ttc, fontNumber=reg_idx)
        _b_ft = FTFont(bold_ttc, fontNumber=bld_idx)
        print(f"[CreatePDF 字型]")
        print(f"  Regular: {sans_ttc} [{reg_idx}] = {_r_ft['name'].getDebugName(4)}")
        print(f"  Bold   : {bold_ttc} [{bld_idx}] = {_b_ft['name'].getDebugName(4)}")
        _yu_cmap = set(_r_ft.getBestCmap().keys())
    except Exception:
        _yu_cmap = set()

    reg = extract_and_convert(sans_ttc, reg_idx)
    bld = extract_and_convert(bold_ttc, bld_idx)
    pdfmetrics.registerFont(TTFont("NotoCJK", reg))
    pdfmetrics.registerFont(TTFont("NotoCJK-Bold", bld))

    # ===== 註冊 Noto fallback 補字型 =====
    if _has_noto_fallback:
        noto_reg_idx = _find_subfont(noto_reg, want_bold=False, prefer_tc=True)
        noto_bld_idx = _find_subfont(noto_bld, want_bold=True, prefer_tc=True)
        try:
            _nr_ft = FTFont(noto_reg, fontNumber=noto_reg_idx)
            _nb_ft = FTFont(noto_bld, fontNumber=noto_bld_idx)
            print(f"  NotoFallback Regular: {noto_reg} [{noto_reg_idx}] = {_nr_ft['name'].getDebugName(4)}")
            print(f"  NotoFallback Bold   : {noto_bld} [{noto_bld_idx}] = {_nb_ft['name'].getDebugName(4)}")
            _noto_cmap = set(_nr_ft.getBestCmap().keys())
        except Exception:
            _noto_cmap = set()
        noto_reg_ttf = extract_and_convert(noto_reg, noto_reg_idx)
        noto_bld_ttf = extract_and_convert(noto_bld, noto_bld_idx)
        pdfmetrics.registerFont(TTFont("NotoFallback", noto_reg_ttf))
        pdfmetrics.registerFont(TTFont("NotoFallback-Bold", noto_bld_ttf))
    else:
        pdfmetrics.registerFont(TTFont("NotoFallback", reg))
        pdfmetrics.registerFont(TTFont("NotoFallback-Bold", bld))
        _noto_cmap = _yu_cmap

    _fonts_registered = True


# v6.19 / 2026-05-17:逐字 fallback 工具函式 ----------------------------------------
_FALLBACK_MAP = {
    "NotoCJK": "NotoFallback",
    "NotoCJK-Bold": "NotoFallback-Bold",
}

def _resolve_font_for_char(ch, current_font):
    """回傳渲染此字符應該用的字型 alias。
    若 current_font 不是游黑體系列(NotoCJK / NotoCJK-Bold),直接回傳 current_font。
    """
    if current_font not in _FALLBACK_MAP:
        return current_font
    if ord(ch) in _yu_cmap:
        return current_font
    # 游黑體沒,看 Noto 有沒
    if _has_noto_fallback and ord(ch) in _noto_cmap:
        return _FALLBACK_MAP[current_font]
    # 兩者都沒 → 維持游黑體渲染(會豆腐,由第 18 條規則源頭管制杜絕)
    return current_font

def draw_string_with_fallback(c, x, y, text, font, size):
    """v6.19 / 2026-05-17 逐字 fallback 繪字。
    - 若整段都在游黑體 cmap 內 → 等同 c.drawString(直接走快路徑)
    - 否則切成段,分別 setFont 後 drawString,維持字距正確
    使用此函式取代「setFont + drawString」組合。
    """
    if not text:
        return
    # 快路徑:非游黑體系列,或全部字符都在游黑體 cmap 內
    if font not in _FALLBACK_MAP or not _has_noto_fallback:
        c.setFont(font, size)
        c.drawString(x, y, text)
        return
    if all(ord(ch) in _yu_cmap for ch in text):
        c.setFont(font, size)
        c.drawString(x, y, text)
        return
    # 慢路徑:逐字切段,分別 setFont 繪
    cur_x = x
    seg_font = None
    seg_buf = []
    for ch in text:
        ch_font = _resolve_font_for_char(ch, font)
        if ch_font != seg_font and seg_buf:
            seg_text = "".join(seg_buf)
            c.setFont(seg_font, size)
            c.drawString(cur_x, y, seg_text)
            cur_x += pdfmetrics.stringWidth(seg_text, seg_font, size)
            seg_buf = []
        seg_font = ch_font
        seg_buf.append(ch)
    if seg_buf:
        seg_text = "".join(seg_buf)
        c.setFont(seg_font, size)
        c.drawString(cur_x, y, seg_text)

def string_width_with_fallback(text, font, size):
    """v6.19 / 2026-05-17 計算字寬時也要考慮 fallback。
    游黑體沒的字若用 Noto 渲染,寬度可能與游黑體不同,要分段算。
    """
    if not text:
        return 0
    if font not in _FALLBACK_MAP or not _has_noto_fallback:
        return pdfmetrics.stringWidth(text, font, size)
    if all(ord(ch) in _yu_cmap for ch in text):
        return pdfmetrics.stringWidth(text, font, size)
    total = 0
    seg_font = None
    seg_buf = []
    for ch in text:
        ch_font = _resolve_font_for_char(ch, font)
        if ch_font != seg_font and seg_buf:
            total += pdfmetrics.stringWidth("".join(seg_buf), seg_font, size)
            seg_buf = []
        seg_font = ch_font
        seg_buf.append(ch)
    if seg_buf:
        total += pdfmetrics.stringWidth("".join(seg_buf), seg_font, size)
    return total


def to_slug(heading):
    s = heading.strip().lower()
    s = s.replace(".", "")
    # v4.10.1 / 2026-04-24:加入 ★ ✓ ✗ ☆ 等裝飾符號,半形冒號、問號、驚嘆號
    # v6.18 / 2026-05-12:加 ⚠ ◆ ─ 等常見裝飾符號
    # v6.19 / 2026-05-16:加反引號 `(對齊 _strip_md 行為,讓 anchor 跟 link target 一致)
    #   不加會造成 bug:標題含反引號(如「`_split`」)時,anchor 保留反引號但
    #   md 內 link target 經 _strip_md 處理後被去掉反引號 → unresolved → 點下沒反應
    # 注意:不合併連續 -,因為舊 anchor(如「Phase A / B / C」的 `/` 刪後變雙 `-`)依賴此行為
    for c in "、,。,()(){}〔〕[]【】《》「」『』/\\:·:!?!?★☆✓✗⚠◆─`":
        s = s.replace(c, "")
    s = s.replace(" ", "-").replace("\t", "-")
    return s.strip("-")


def _patch_canvas_for_fallback(canvas_obj):
    """v6.19 / 2026-05-17 monkey-patch reportlab Canvas 的 drawString,
    讓所有現有 drawString 呼叫透明取得 Noto fallback 能力。

    機制:用閉包記住「最近一次 setFont 的字型 alias 與大小」,
    drawString 時若該字型是游黑體系列(NotoCJK / NotoCJK-Bold),
    走 draw_string_with_fallback 逐字檢查、分段繪字。
    """
    if getattr(canvas_obj, "_fallback_patched", False):
        return

    _state = {"font": "NotoCJK", "size": 10}

    orig_setFont = canvas_obj.setFont
    orig_drawString = canvas_obj.drawString

    def patched_setFont(font, size, leading=None):
        _state["font"] = font
        _state["size"] = size
        if leading is not None:
            return orig_setFont(font, size, leading)
        return orig_setFont(font, size)

    def patched_drawString(x, y, text, *args, **kwargs):
        font = _state["font"]
        size = _state["size"]
        if not _has_noto_fallback or font not in _FALLBACK_MAP:
            return orig_drawString(x, y, text, *args, **kwargs)
        # 快路徑:全在游黑體 cmap
        if not text or all(ord(ch) in _yu_cmap for ch in text):
            return orig_drawString(x, y, text, *args, **kwargs)
        # 慢路徑:逐字切段
        cur_x = x
        seg_font = None
        seg_buf = []
        for ch in text:
            ch_font = _resolve_font_for_char(ch, font)
            if ch_font != seg_font and seg_buf:
                seg_text = "".join(seg_buf)
                orig_setFont(seg_font, size)
                orig_drawString(cur_x, y, seg_text)
                cur_x += pdfmetrics.stringWidth(seg_text, seg_font, size)
                seg_buf = []
            seg_font = ch_font
            seg_buf.append(ch)
        if seg_buf:
            seg_text = "".join(seg_buf)
            orig_setFont(seg_font, size)
            orig_drawString(cur_x, y, seg_text)
        # 還原 caller 期望的字型(避免後續 caller 假設字型未變)
        orig_setFont(font, size)

    canvas_obj.setFont = patched_setFont
    canvas_obj.drawString = patched_drawString
    canvas_obj._fallback_patched = True


class PDFBuilder:
    def __init__(self, out_path, pdf_title=None, pdf_author=None, pdf_subject=None):
        self.c = canvas.Canvas(out_path, pagesize=A4)
        # v5.12 / 2026-05-03 新增 PDF metadata
        # v6.21 / 2026-06-28 改為參數傳入(三專案共用),未傳則 fallback 回超高壓原值
        self._pdf_title = pdf_title or _DEFAULT_PDF_TITLE
        self._pdf_author = pdf_author or _DEFAULT_PDF_AUTHOR
        self._pdf_subject = pdf_subject or _DEFAULT_PDF_SUBJECT
        self.c.setTitle(self._pdf_title)
        self.c.setAuthor(self._pdf_author)
        self.c.setSubject(self._pdf_subject)
        self.page_num = 1
        self.y = Y_TOP
        self.pending_links = {}
        self.anchors = {}
        self.is_first_page = True  # 第 1 頁是封面+目錄,不套章節換頁
        # v6.19 / 2026-05-17:目錄區緊湊行距 flag
        # 進入 "## 目錄" 後設 True,進入下一個 H2(速覽表)時清掉
        # 目錄內 H3 上方間距減半 + bullet 行距 15→12,讓目錄擠在 P1 同一頁
        self.in_toc = False
        # v6.19 / 2026-05-17:monkey-patch canvas drawString,讓所有呼叫透明取得 Noto fallback
        _patch_canvas_for_fallback(self.c)

    def tw(self, text, size, font="NotoCJK"):
        # v6.19 / 2026-05-17:用 fallback 版 stringWidth(游黑體沒的字用 Noto cmap 算寬度)
        return string_width_with_fallback(text, font, size)

    def new_page(self):
        self.c.showPage()
        self.page_num += 1
        self.y = Y_TOP

    def ensure(self, h):
        if self.y - h < MARGIN_B:
            self.new_page()

    def wrap(self, text, size, font, w):
        if not text:
            return [""]
        out, cur = [], ""
        for ch in text:
            if self.tw(cur + ch, size, font) > w:
                if cur:
                    out.append(cur)
                    cur = ch
                else:
                    out.append(ch)
                    cur = ""
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    # ========== 繪製區塊 ==========
    def draw_text_line(self, text, size=FONT_BODY, font="NotoCJK",
                       color=None, x=None, line_h=None, link_slug=None):
        if x is None:
            x = MARGIN_L
        if line_h is None:
            line_h = LINE_H_BODY
        if color is None:
            color = COLOR_TEXT
        avail = MARGIN_R_X - x
        lines = self.wrap(text, size, font, avail)
        for ln in lines:
            self.ensure(line_h)
            self.c.setFont(font, size)
            self.c.setFillColorRGB(*color)
            self.c.drawString(x, self.y, ln)
            if link_slug:
                w = self.tw(ln, size, font)
                rect = (x, self.y - 2, x + w, self.y + size + 2)
                self.pending_links.setdefault(self.page_num, []).append(
                    (rect, link_slug)
                )
            self.y -= line_h

    def draw_h1(self, text):
        """封面大標"""
        self.c.setFont("NotoCJK-Bold", FONT_H1)
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.c.drawString(MARGIN_L, self.y, text)
        self.y -= FONT_H1 + 6

    def draw_h2(self, text, slug=None, estimated_next_block_h=0):
        """H2:上下兩條分隔線,章節獨占頁首

        v4.10.2 / 2026-04-24 + v6.18 / 2026-05-13 重新確認:強制換頁
        - 原則:章節標題必須獨占頁首,不可「尾接頭」(前章尾 + 下章頭同頁)
        - 理由:章節邊界必須視覺明確,翻頁才清楚
        - estimated_next_block_h 參數保留(未使用),不破壞上層呼叫介面

        歷史教訓:v6.18 / 2026-05-12 21:00 一度改為「條件式換頁」(短章節合併同頁),
        但工程師指出此舉違反原則 — H2 章節邊界必須永遠在頁頂,不可塞在頁中段。
        2026-05-13 撤回,回到 v4.10.2 強制換頁邏輯。
        """
        is_toc = (text.strip() == "目錄")

        # v6.19 / 2026-05-17:目錄區緊湊行距 flag
        # 進入「目錄」設 True;進入其他 H2(速覽表等)清掉
        self.in_toc = is_toc

        # 強制換頁(除第一頁與目錄外)
        if not is_toc and not self.is_first_page:
            self.new_page()

        # 畫上線(目錄不畫,因為 H1 下方已有)
        if not is_toc:
            top_y = self.y
            self.c.setStrokeColorRGB(*COLOR_H2_LINE)
            self.c.setLineWidth(0.5)
            self.c.line(MARGIN_L, top_y, MARGIN_R_X, top_y)
            self.y -= H2_TOP_TO_TITLE

        # 錨點:h2 強制換頁後一定在頁首 → 固定用 791.89(整頁對齊視窗頂)
        if slug:
            self.anchors[slug] = (self.page_num, 791.89)

        # H2 標題
        self.c.setFont("NotoCJK-Bold", FONT_H2)
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.c.drawString(MARGIN_L, self.y, text)
        self.y -= H2_TITLE_TO_BOT

        # 下線
        self.c.setStrokeColorRGB(*COLOR_H2_LINE)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN_L, self.y, MARGIN_R_X, self.y)
        self.y -= H2_BOT_TO_BODY

        self.is_first_page = False

    def draw_h3(self, text, slug=None):
        # v6.19 / 2026-05-17:目錄區 H3 上方間距減半(10 → 3)讓目錄擠進 P1
        self.y -= 3 if self.in_toc else 10
        # orphan 檢查:若 h3 放下後至少留 120pt(約一個程式碼塊或表格)空間,不夠就先換頁
        # 目錄區跳過 orphan 檢查(整個目錄就是要塞同頁)
        if not self.in_toc and self.y - 120 < MARGIN_B:
            self.new_page()
        if slug:
            # v6.19 / 2026-05-16 修補:用真實 y(取標題上方一點當對齊頂)
            # 舊版 v6.18 用 791.89 → 同一頁多個 H3 全跳到頁面最頂,看到的是頁頂的別人
            # 工程師回報「13.11 跳到 13.8」就是這個 bug(p96 有 13.8/9/10/11 全 y=791.89)
            # 改:用 self.y + 18(標題上方 18pt,給 H3 字體 + 一點 padding,
            #     讓 viewer 滑到 H3 上方一點,H3 在視窗頂稍偏下,自然好看)
            # 邊界:若接近頁頂(y > 770)還是用頁頂 791.89(避免「明明在頁頂卻往下跳一點」)
            #      若接近頁底(y < 100)用 y + 18 上限不超過頁頂,讓 viewer 自然處理
            _anchor_y = 791.89 if self.y > 770 else min(791.89, self.y + 18)
            self.anchors[slug] = (self.page_num, _anchor_y)
            # 同時註冊短 slug「sec-N-M」讓 inline 「N.M 節」自動連結
            m_sec = re.match(r"^(\d+)\.(\d+)\s", text)
            if m_sec:
                short = f"sec-{m_sec.group(1)}-{m_sec.group(2)}"
                self.anchors[short] = (self.page_num, _anchor_y)
        self.c.setFont("NotoCJK-Bold", FONT_H3)
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.c.drawString(MARGIN_L, self.y, text)
        # v6.19 / 2026-05-17:目錄區 H3 下方間距減半(25→16)
        self.y -= (FONT_H3 + 3) if self.in_toc else (FONT_H3 + H3_TO_BODY + 4)

    def draw_h4(self, text, slug=None):
        self.y -= 3
        # H4 orphan 偵測:後面至少要塞 50pt 才在當前頁畫,否則先換頁
        if self.y - 50 < MARGIN_B:
            self.new_page()
        # v6.19 / 2026-05-16 同 draw_h3:用真實 y
        if slug:
            _anchor_y = 791.89 if self.y > 770 else min(791.89, self.y + 16)
            self.anchors[slug] = (self.page_num, _anchor_y)
            m_sec = re.match(r"^(\d+)\.(\d+)", text)
            if m_sec:
                short = f"sec-{m_sec.group(1)}-{m_sec.group(2)}"
                if short not in self.anchors:  # 不覆蓋已存在的 h3 sec
                    self.anchors[short] = (self.page_num, _anchor_y)
        self.c.setFont("NotoCJK-Bold", FONT_H4)
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.c.drawString(MARGIN_L, self.y, text)
        self.y -= FONT_H4 + H4_TO_BODY

    def draw_h5(self, text, slug=None):
        """H5 (#####) — v4.10.3 新增:略小於 h4,加 orphan 偵測"""
        self.y -= 2
        if self.y - 50 < MARGIN_B:
            self.new_page()
        # v6.19 / 2026-05-16 同 draw_h3:用真實 y
        if slug:
            _anchor_y = 791.89 if self.y > 770 else min(791.89, self.y + 14)
            self.anchors[slug] = (self.page_num, _anchor_y)
            m_sec = re.match(r"^(\d+)\.(\d+)", text)
            if m_sec:
                short = f"sec-{m_sec.group(1)}-{m_sec.group(2)}"
                if short not in self.anchors:
                    self.anchors[short] = (self.page_num, _anchor_y)
        self.c.setFont("NotoCJK-Bold", FONT_H4)  # 沿用 h4 字號(FONT_H4 = 12)
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.c.drawString(MARGIN_L, self.y, text)
        self.y -= FONT_H4 + H4_TO_BODY

    def draw_hr(self):
        """--- 水平分隔線(若緊接 h2 會被上層跳過)"""
        pass  # 舊版 md 的 --- 都與 h2 相鄰,不另畫(h2 自己有線)

    def _strip_md(self, text):
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        t = re.sub(r"`(.+?)`", r"\1", t)
        return t

    def _parse_inline_links(self, text):
        """抓出所有 [x](y) 連結,回傳 segments list
        每個 segment = ("text", 文字) 或 ("link", 文字, target_type, target)
        target_type: "anchor" (內部 #slug) 或 "url" (http...)

        特別處理:當出現「[章節](#chapter) N.M 節」模式時,
        章節連結的 target 改指向 sec-N-M(因為使用者意圖是跳到小節)
        """
        # 第一步:處理已寫好的 [x](y)
        segments = []
        pos = 0
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if m.start() > pos:
                segments.append(("text", text[pos:m.start()]))
            label = m.group(1)
            target = m.group(2)
            if target.startswith("#"):
                segments.append(("link", label, "anchor", target[1:]))
            elif target.startswith("http") or target.startswith("mailto:"):
                segments.append(("link", label, "url", target))
            else:
                segments.append(("text", label))
            pos = m.end()
        if pos < len(text):
            segments.append(("text", text[pos:]))

        # 第二步:偵測「[章節] N.M 節」組合模式
        # 若 link segment 後面緊跟 text 中含 "N.M 節",則該章節連結改指向 sec-N-M
        for i in range(len(segments)):
            if segments[i][0] != "link":
                continue
            # 看緊接的下一個 text segment(允許中間有純空白/標點)
            for j in range(i + 1, min(i + 3, len(segments))):
                if segments[j][0] != "text":
                    break
                # 在 j 的 text 開頭附近(最多 30 字內)找 "N.M 節"
                lookup_text = segments[j][1][:40]
                # v6.18 / 2026-05-12 同 L416:加 N.M.K 支援
                m_sec = re.search(r"(?<![\dA-Za-z])(\d+)\.(\d+)(?:\.\d+)?\s*節", lookup_text)
                if m_sec:
                    # 章節連結改指向 sec-N-M
                    link_tuple = segments[i]
                    segments[i] = (link_tuple[0], link_tuple[1], link_tuple[2],
                                   f"sec-{m_sec.group(1)}-{m_sec.group(2)}")
                    break

        # 第三步:對 text segment 內把「N.M 節」轉為自動 link
        new_segs = []
        for seg in segments:
            if seg[0] == "text":
                t = seg[1]
                last = 0
                # v6.18 / 2026-05-12 修補:支援 N.M.K 節 形式(如 8.4.4 節 → sec-8-4)
                # 之前 regex 從中間 match 會把「8.4.4 節」抓成「4.4 節」 → sec-4-4(錯)
                # 加 negative lookbehind (?<!\d) 確保 N 是整數起點
                for mm in re.finditer(r"(?<![\dA-Za-z])(\d+)\.(\d+)(?:\.\d+)?\s*節", t):
                    if mm.start() > last:
                        new_segs.append(("text", t[last:mm.start()]))
                    label = mm.group(0)
                    short_slug = f"sec-{mm.group(1)}-{mm.group(2)}"
                    new_segs.append(("link", label, "anchor", short_slug))
                    last = mm.end()
                if last < len(t):
                    new_segs.append(("text", t[last:]))
            else:
                new_segs.append(seg)
        return new_segs

    # 保留 _parse_inline 以相容
    def _parse_inline(self, text):
        m = re.search(r"\[([^\]]+)\]\(#([^)]+)\)", text)
        if m:
            return (text[:m.start()], m.group(1), m.group(2), text[m.end():])
        return None

    def draw_para(self, text):
        clean = self._strip_md(text)
        if not clean.strip():
            return
        segs = self._parse_inline_links(clean)
        self.draw_segments(segs)

    def _draw_text_with_link(self, prefix, link_text, slug, suffix):
        """繪 'prefix LINK suffix' 整行,LINK 藍色、帶熱區"""
        size, font = FONT_BODY, "NotoCJK"
        # 先 wrap 整段,遇到連結再分段畫
        # 簡化:不考慮 link 跨行,若 wrap 後 link 被拆,還是整塊畫
        avail = MARGIN_R_X - MARGIN_L
        full = prefix + link_text + suffix
        lines = self.wrap(full, size, font, avail)

        # 定位連結在哪幾行
        prefix_len = len(prefix)
        link_end = prefix_len + len(link_text)

        idx = 0
        for ln in lines:
            self.ensure(LINE_H_BODY)
            x = MARGIN_L
            line_start = idx
            line_end = idx + len(ln)
            # 畫 prefix 部分
            parts = []
            if line_start < prefix_len:
                end = min(prefix_len, line_end)
                parts.append(("text", ln[:end - line_start]))
                pos = end - line_start
            else:
                pos = 0
            # 畫 link 部分
            if line_start < link_end and line_end > prefix_len:
                link_s = max(0, prefix_len - line_start)
                link_e = min(len(ln), link_end - line_start)
                if link_e > link_s:
                    parts.append(("link", ln[link_s:link_e]))
                    pos = link_e
            # 畫 suffix 部分
            if line_end > link_end:
                suffix_s = max(0, link_end - line_start)
                parts.append(("text", ln[suffix_s:]))

            # 繪製
            self.c.setFont(font, size)
            for kind, s in parts:
                if kind == "text":
                    self.c.setFillColorRGB(*COLOR_TEXT)
                    self.c.drawString(x, self.y, s)
                else:
                    self.c.setFillColorRGB(*COLOR_LINK)
                    self.c.drawString(x, self.y, s)
                    w = self.tw(s, size, font)
                    rect = (x, self.y - 2, x + w, self.y + size + 2)
                    self.pending_links.setdefault(self.page_num, []).append(
                        (rect, slug)
                    )
                x += self.tw(s, size, font)

            self.y -= LINE_H_BODY
            idx = line_end

    def draw_segments(self, segments, prefix_str="", line_h=None):
        """繪製段落含多個內嵌 [x](#y) 或 [x](http..) 連結,自動 wrap"""
        if line_h is None:
            # v6.19 / 2026-05-17:目錄區行距 15→12,讓目錄擠進 P1 同頁
            line_h = 12 if self.in_toc else LINE_H_BODY
        size = FONT_BODY
        font = "NotoCJK"
        x_start = MARGIN_L
        avail_w = MARGIN_R_X - x_start

        # 串全文,記錄 link 範圍
        full = prefix_str
        link_ranges = []  # [(start, end, type, target)]
        for seg in segments:
            if seg[0] == "text":
                full += seg[1]
            else:
                s = len(full)
                full += seg[1]
                e = len(full)
                link_ranges.append((s, e, seg[2], seg[3]))

        lines = self.wrap(full, size, font, avail_w)
        pos = 0
        for ln in lines:
            self.ensure(line_h)
            line_start = pos
            line_end = pos + len(ln)
            self.c.setFont(font, size)
            x = x_start
            j = line_start
            while j < line_end:
                # 當前字元是否在某個 link 中?
                in_link = None
                for (ls, le, lt, tg) in link_ranges:
                    if ls <= j < le:
                        in_link = (ls, le, lt, tg)
                        break
                if in_link:
                    ls, le, lt, tg = in_link
                    seg_end = min(line_end, le)
                    seg_text = full[j:seg_end]
                    # v4.10 / 2026-04-25:判斷是否為「真實可點」link
                    # - URL 類型:用 c.linkURL() 做外部跳轉(藍色 + 可點)
                    # - anchor 為範例文字(xxx / 章節slug / ... / 新-anchor / text / 文字 等):不上色
                    is_example = (lt == "anchor" and (
                        tg in ('xxx', 'y', 'ch', '章節slug', 'sec', 'anchor', '21-...', '新-anchor')
                        or '...' in tg or tg.startswith('新-')
                    )) or (lt == "url" and '...' in tg)  # URL 含 ... 也是範例
                    is_example_text = full[ls:le] in ('章節', '章節名', 'x', 'text', '文字')
                    if is_example or is_example_text:
                        # 範例文字不上色
                        self.c.setFillColorRGB(*COLOR_TEXT)
                        self.c.drawString(x, self.y, seg_text)
                    else:
                        # 真實 link(anchor 或 URL)→ 藍色
                        self.c.setFillColorRGB(*COLOR_LINK)
                        self.c.drawString(x, self.y, seg_text)
                    w = self.tw(seg_text, size, font)
                    if lt == "anchor" and not is_example and not is_example_text:
                        rect = (x, self.y - 2, x + w, self.y + size + 2)
                        self.pending_links.setdefault(self.page_num, []).append(
                            (rect, tg)
                        )
                    elif lt == "url" and not is_example:
                        # URL 用 reportlab 的 linkURL 做外部跳轉(範例 URL 不做)
                        rect = (x, self.y - 2, x + w, self.y + size + 2)
                        self.c.linkURL(tg, rect, relative=0)
                    x += w
                    j = seg_end
                else:
                    # 找下一個 link 起點
                    next_ls = line_end
                    for (ls, le, lt, tg) in link_ranges:
                        if j < ls < next_ls:
                            next_ls = ls
                    seg_end = min(line_end, next_ls)
                    seg_text = full[j:seg_end]
                    self.c.setFillColorRGB(*COLOR_TEXT)
                    self.c.drawString(x, self.y, seg_text)
                    x += self.tw(seg_text, size, font)
                    j = seg_end
            self.y -= line_h
            pos = line_end

    def draw_bullet(self, text, level=0):
        """bullet:支援多個內嵌連結(含 URL)"""
        clean = self._strip_md(text)
        prefix_str = " " * (level * 4) + "• "
        segs = self._parse_inline_links(clean)
        self.draw_segments(segs, prefix_str=prefix_str)

    def draw_numbered(self, text):
        clean = self._strip_md(text)
        if not clean.strip():
            return
        segs = self._parse_inline_links(clean)
        self.draw_segments(segs)

    def draw_quote(self, text):
        """引言:舊版實測為普通段落呈現(無灰底、無縮排),只是 md 用 > 標示"""
        clean = self._strip_md(text)
        if not clean.strip():
            return
        # 走 segments 確保有連結時也能上色
        segs = self._parse_inline_links(clean)
        self.draw_segments(segs)

    def draw_code(self, lines):
        """程式碼區塊:全寬淺灰底
        舊版實測:灰底比內文 y 範圍大 — 上 6、下 5 padding

        2026-05-16 補丁:超寬行自動 wrap(原本直接 drawString 不檢查寬度,
                         markdown 內若有長連續字元如 60 個「─」會延伸到頁面外)
        來源:雙安企業 / 預定施工進度表系統 v1.0 修補(同 CreatePDF.py 變體)

        2026-05-17 修補:超大 code block(> 一頁)分段繪製,避免 P130 整頁空白
        - 舊邏輯:`if self.y - box_h < MARGIN_B: new_page()` 對超大 block 永遠成立 →
          即使剛換新頁也再換 → 前頁留大白
        - 新邏輯:超過一頁時改為「逐段繪製」,每段最多塞滿當前頁可用空間,跨頁時
          各自畫自己的灰底
        """
        # ── 預處理:把超寬行 wrap 成多行 ──
        # 可用寬 = USABLE_W - 8(扣左右各 4pt padding)
        max_line_w = USABLE_W - 8
        wrapped = []
        for orig in lines:
            if not orig:
                wrapped.append("")
                continue
            # 逐字累加寬度,超寬就斷
            line = ""
            cur_w = 0.0
            for ch in orig:
                ch_w = pdfmetrics.stringWidth(ch, "NotoCJK", FONT_CODE)
                if cur_w + ch_w > max_line_w and line:
                    wrapped.append(line)
                    line = ch
                    cur_w = ch_w
                else:
                    line += ch
                    cur_w += ch_w
            wrapped.append(line)
        lines = wrapped

        self.y -= 2
        n = len(lines)
        content_h = n * LINE_H_CODE
        box_h = content_h + 11
        page_avail = Y_TOP - MARGIN_B  # 一整頁可用高 ≈ 683pt

        # v6.19 / 2026-05-17:超大 code block 走分段路徑
        if box_h > page_avail:
            self._draw_code_paginated(lines)
            return

        # 一般 code block(舊邏輯)
        if self.y - box_h < MARGIN_B:
            self.new_page()
        # 內文第一行 baseline 在 self.y,字高 9
        top = self.y + FONT_CODE + 1
        bot = self.y - (n - 1) * LINE_H_CODE - 5
        self.c.setFillColorRGB(*COLOR_CODE_BG)
        self.c.rect(MARGIN_L, bot, USABLE_W, top - bot, fill=1, stroke=0)
        self.c.setFont("NotoCJK", FONT_CODE)
        self.c.setFillColorRGB(*COLOR_TEXT)
        for cl in lines:
            if self.y < MARGIN_B + LINE_H_CODE:
                self.new_page()
                self.c.setFont("NotoCJK", FONT_CODE)
                self.c.setFillColorRGB(*COLOR_TEXT)
            self.c.drawString(MARGIN_L + 4, self.y, cl)
            self.y -= LINE_H_CODE
        self.y -= 6

    def _draw_code_paginated(self, lines):
        """v6.19 / 2026-05-17 新增:超大 code block 分段繪製

        策略:把 lines 切成多段,每段塞當前頁剩餘空間,每段畫自己的灰底
        關鍵:不預先 new_page(舊 bug),也不一次計算 box_h(會 overflow)
        """
        idx = 0
        n_total = len(lines)
        while idx < n_total:
            # 計算當前頁能塞幾行
            # 可用高 = self.y - MARGIN_B - 5(底部 padding)
            avail_h = self.y - MARGIN_B - 5
            if avail_h < LINE_H_CODE + 6:
                # 連一行都塞不下 → 換頁
                self.new_page()
                avail_h = self.y - MARGIN_B - 5
            # 一段塞幾行(扣上下 padding 約 11pt)
            seg_lines_n = int((avail_h - 6) // LINE_H_CODE)
            seg_lines_n = max(1, min(seg_lines_n, n_total - idx))
            seg = lines[idx:idx + seg_lines_n]
            # 畫這一段的灰底 + 文字
            top = self.y + FONT_CODE + 1
            bot = self.y - (seg_lines_n - 1) * LINE_H_CODE - 5
            self.c.setFillColorRGB(*COLOR_CODE_BG)
            self.c.rect(MARGIN_L, bot, USABLE_W, top - bot, fill=1, stroke=0)
            self.c.setFont("NotoCJK", FONT_CODE)
            self.c.setFillColorRGB(*COLOR_TEXT)
            for cl in seg:
                self.c.drawString(MARGIN_L + 4, self.y, cl)
                self.y -= LINE_H_CODE
            idx += seg_lines_n
            if idx < n_total:
                # 還有後續行 → 換頁,繼續
                self.new_page()
        self.y -= 6

    def draw_table(self, rows):
        """表格繪製 — v6.18 / 2026-05-12 第二輪重寫

        三項重大改進:
        (1) 欄寬演算法:雙約束(最小欄寬 + 平衡 wrap 後行數)取代「最寬一格決定欄寬」
        (2) 跨頁分列繪製:逐列繪製,跨頁自動換頁 + 重畫表頭
        (3) 短欄保護:中文欄至少 4 字寬,避免「Pha / se A / 入 / 口」拆字

        歷史問題:舊版「最寬一格 + 比例縮放」演算法把「主軸」欄(40+ 字)硬擠成
        單行寬,排擠「#」/「軸數」等短欄到只剩 3~4 中文字寬,造成 35:1 失衡。
        新演算法允許長欄 wrap 2~3 行,讓短欄保有最小可讀寬。

        cell 內 [text](#anchor) 與 inline「N.M 節」自動連結維持 v4.10/v6.18 邏輯。
        """
        if not rows:
            return
        cleaned = []
        for row in rows:
            stripped = "".join(row).replace("-", "").replace(":", "").strip()
            if not stripped:
                continue
            cleaned.append(row)
        if not cleaned:
            return

        n_cols = max(len(r) for r in cleaned)
        cleaned = [r + [""] * (n_cols - len(r)) for r in cleaned]

        # ── 解析每個 cell 的 link 並產生純文字版 ──
        # cells_parsed[r][c] = list of segments: ("text", str) | ("link", str, slug) | ("url", str, url)
        # cells_plain[r][c] = 純文字(用於 wrap 計算)
        cells_parsed = []
        cells_plain = []
        for r in cleaned:
            row_parsed = []
            row_plain = []
            for cell in r:
                clean = self._strip_md(cell)
                # Step 1: 先抓明示 [text](target) link
                segs = []
                pos = 0
                plain = ""
                for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", clean):
                    if m.start() > pos:
                        segs.append(("text", clean[pos:m.start()]))
                        plain += clean[pos:m.start()]
                    label = m.group(1)
                    target = m.group(2)
                    if target.startswith("#"):
                        segs.append(("link", label, target[1:]))
                    elif target.startswith("http") or target.startswith("mailto:"):
                        segs.append(("url", label, target))
                    else:
                        segs.append(("text", label))
                    plain += label
                    pos = m.end()
                if pos < len(clean):
                    segs.append(("text", clean[pos:]))
                    plain += clean[pos:]

                # Step 2: 對 text segment 內掃描 inline「N.M 節」/「N.M.K 節」自動轉 link
                new_segs = []
                for seg in segs:
                    if seg[0] != "text":
                        new_segs.append(seg)
                        continue
                    t = seg[1]
                    last = 0
                    for mm in re.finditer(r"(?<![\dA-Za-z])(\d+)\.(\d+)(?:\.\d+)?\s*節", t):
                        if mm.start() > last:
                            new_segs.append(("text", t[last:mm.start()]))
                        label = mm.group(0)
                        short_slug = f"sec-{mm.group(1)}-{mm.group(2)}"
                        new_segs.append(("link", label, short_slug))
                        last = mm.end()
                    if last < len(t):
                        new_segs.append(("text", t[last:]))

                row_parsed.append(new_segs)
                row_plain.append(plain)
            cells_parsed.append(row_parsed)
            cells_plain.append(row_plain)

        # ════════════════════════════════════════════════════════════════
        # v6.18 / 2026-05-12 第二輪重寫:雙約束欄寬演算法
        # ════════════════════════════════════════════════════════════════
        # 舊演算法問題:取「最寬一格的單行寬度」當欄寬,長欄擠死短欄
        # 新演算法:
        #   1. 算每欄「最小可讀寬」=表頭文字寬 OR 中文 4 字寬 OR 最長單詞寬,取最大
        #   2. 算每欄「自然寬」=各 cell 寬度的 80% 分位數(避開單格極端值影響)
        #   3. 在「總寬 = USABLE_W」約束下,優先給最小可讀寬,剩餘空間按自然寬比例分配
        #   4. 任何欄 < 最小可讀寬時保護(其他欄縮)
        # ════════════════════════════════════════════════════════════════
        PADDING = 12   # 左右 padding 合計
        MIN_CN_CHARS = 4  # 中文最小 4 字
        # 估「中文一字寬」(NotoCJK FONT_CODE)
        cn_char_w = self.tw("中", FONT_CODE, "NotoCJK")
        MIN_COL_FLOOR = cn_char_w * MIN_CN_CHARS + PADDING  # 約 4 中文字 + padding

        # Step 1: 每欄最小可讀寬
        min_widths = []
        for ci in range(n_cols):
            # 表頭文字寬
            hdr_text = cells_plain[0][ci] if cleaned else ""
            hdr_w = self.tw(hdr_text, FONT_CODE, "NotoCJK") + PADDING
            # 各列「最長不可斷單詞」寬(如英文識別字、長數字)
            # 中文每字本身就可換行,所以實際是看英數連續串
            longest_word_w = 0
            for r_plain in cells_plain:
                if ci >= len(r_plain): continue
                # 找最長連續英數+底線+句點(識別字)
                for word in re.findall(r"[A-Za-z0-9_\.\-/]+", r_plain[ci]):
                    ww = self.tw(word, FONT_CODE, "NotoCJK")
                    if ww > longest_word_w:
                        longest_word_w = ww
            # 取三者最大,作為該欄絕對下限
            mw = max(hdr_w, longest_word_w + PADDING, MIN_COL_FLOOR)
            # 但 min 不能超過 USABLE_W / n_cols 太多(否則欄擠不下)
            mw = min(mw, USABLE_W / n_cols * 1.5)
            min_widths.append(mw)

        # 若 min 總和已超過 USABLE_W → 等比例縮減 min(維持比例)
        sum_min = sum(min_widths)
        if sum_min > USABLE_W:
            scale = USABLE_W / sum_min
            min_widths = [m * scale for m in min_widths]
            sum_min = USABLE_W

        # Step 2: 每欄「自然寬」=該欄各 cell 的文字寬(取較高分位數,避免單一極端值)
        natural_widths = []
        for ci in range(n_cols):
            widths_in_col = []
            for r_plain in cells_plain:
                if ci >= len(r_plain): continue
                w = self.tw(r_plain[ci], FONT_CODE, "NotoCJK") + PADDING
                widths_in_col.append(w)
            if not widths_in_col:
                natural_widths.append(min_widths[ci])
                continue
            widths_in_col.sort()
            # 取 80% 分位作自然寬,讓 20% 最長 cell 容許 wrap
            p80_idx = int(len(widths_in_col) * 0.8)
            p80 = widths_in_col[min(p80_idx, len(widths_in_col)-1)]
            # 但若 80% 分位 < min,用 min
            natural_widths.append(max(p80, min_widths[ci]))

        # Step 3: 配給「剩餘空間」按自然寬 - min 寬的比例
        remaining = USABLE_W - sum_min
        if remaining <= 0:
            col_widths = list(min_widths)
        else:
            # 「自然超出 min 的部分」總和
            excess = [max(0, nw - mw) for nw, mw in zip(natural_widths, min_widths)]
            sum_excess = sum(excess)
            if sum_excess <= 0:
                # 所有欄都 min 就夠,剩餘空間平均分給最寬欄(避免短欄被拉爆)
                # 按 natural width 比例分配
                sum_nat = sum(natural_widths)
                if sum_nat > 0:
                    col_widths = [mw + remaining * (nw / sum_nat) for mw, nw in zip(min_widths, natural_widths)]
                else:
                    col_widths = [mw + remaining / n_cols for mw in min_widths]
            else:
                # 按 excess 比例分配剩餘空間
                col_widths = [mw + remaining * (e / sum_excess) for mw, e in zip(min_widths, excess)]

        # 確保總和 = USABLE_W(浮點誤差校正)
        total = sum(col_widths)
        if abs(total - USABLE_W) > 0.5:
            col_widths = [cw * USABLE_W / total for cw in col_widths]

        # ════════════════════════════════════════════════════════════════
        # 為每個 cell 計算 wrap 後的行數 + 列高
        # ════════════════════════════════════════════════════════════════
        wrapped_cells = []   # [[[line1, line2], [line1], ...], ...]
        row_heights = []
        MIN_ROW_H = LINE_H_TABLE  # 18
        LINE_IN_CELL = 13         # cell 內行距
        for r_idx, r_plain in enumerate(cells_plain):
            cell_lines = []
            max_lines = 1
            for ci, plain in enumerate(r_plain):
                avail = col_widths[ci] - PADDING + 2  # 留 padding
                wrapped = self.wrap(plain, FONT_CODE, "NotoCJK", max(avail, 10))
                cell_lines.append(wrapped)
                if len(wrapped) > max_lines:
                    max_lines = len(wrapped)
            wrapped_cells.append(cell_lines)
            h = max(MIN_ROW_H, max_lines * LINE_IN_CELL + 5)
            row_heights.append(h)

        # ════════════════════════════════════════════════════════════════
        # v6.18 / 2026-05-12 第二輪重寫:跨頁分列繪製
        # ════════════════════════════════════════════════════════════════
        # 舊邏輯:整表跳頁 — 表格放不下整個跳下頁,前面留大片空白(主因)
        # 新邏輯:逐列繪製,跨頁時自動換頁 + 重畫表頭
        #   - 在 self.y - row_h < MARGIN_B 時,換新頁,重畫表頭
        #   - 表頭永遠跟在頂端(專業文件慣例)
        # ════════════════════════════════════════════════════════════════

        x0 = MARGIN_L
        header_h = row_heights[0]
        header_wrapped = wrapped_cells[0]
        header_segs = cells_parsed[0]

        def _draw_one_row(r_idx, is_header):
            """繪製單列(表頭或資料列),回傳新的 self.y"""
            rh = row_heights[r_idx]
            row_wrapped = wrapped_cells[r_idx]
            row_segs = cells_parsed[r_idx]
            y_top_row = self.y

            # 底色 / 邊框
            if is_header:
                self.c.setFillColorRGB(*COLOR_TABLE_HEADER_BG)
                self.c.rect(x0, y_top_row - rh, USABLE_W, rh, fill=1, stroke=0)
                self.c.setStrokeColorRGB(*COLOR_TABLE_HEADER_BORDER)
            else:
                self.c.setStrokeColorRGB(*COLOR_TABLE_BODY_BORDER)
            self.c.setLineWidth(0.5)
            self.c.rect(x0, y_top_row - rh, USABLE_W, rh, fill=0, stroke=1)
            # 欄分隔線
            x_tmp = x0
            for cw in col_widths[:-1]:
                x_tmp += cw
                self.c.line(x_tmp, y_top_row, x_tmp, y_top_row - rh)

            # 填內容
            font_use = "NotoCJK-Bold" if is_header else "NotoCJK"
            x_cur = x0
            for ci, lines in enumerate(row_wrapped):
                self.c.setFont(font_use, FONT_CODE)
                n_lines = len(lines)
                cell_content_h = n_lines * LINE_IN_CELL
                first_baseline = y_top_row - (rh - cell_content_h) / 2 - FONT_CODE

                segs = row_segs[ci]
                char_attrs = []
                for seg in segs:
                    if seg[0] == "text":
                        for ch in seg[1]:
                            char_attrs.append(("text", ch, None, None))
                    elif seg[0] == "link":
                        slug = seg[2]
                        for ch in seg[1]:
                            char_attrs.append(("link", ch, slug, None))
                    elif seg[0] == "url":
                        url = seg[2]
                        for ch in seg[1]:
                            char_attrs.append(("url", ch, None, url))

                char_idx = 0
                for li, ln in enumerate(lines):
                    y_line = first_baseline - li * LINE_IN_CELL
                    x_draw = x_cur + 5
                    line_chars = char_attrs[char_idx:char_idx + len(ln)]
                    char_idx += len(ln)
                    cur_kind = None
                    cur_slug = None
                    cur_url = None
                    cur_buf = ""

                    def flush():
                        nonlocal cur_buf, x_draw
                        if not cur_buf: return
                        if cur_kind in ("link", "url"):
                            self.c.setFillColorRGB(*COLOR_LINK)
                        else:
                            self.c.setFillColorRGB(*COLOR_TEXT)
                        self.c.drawString(x_draw, y_line, cur_buf)
                        w = self.tw(cur_buf, FONT_CODE, font_use)
                        if cur_kind == "link" and cur_slug:
                            rect = (x_draw, y_line - 2, x_draw + w, y_line + FONT_CODE + 2)
                            self.pending_links.setdefault(self.page_num, []).append((rect, cur_slug))
                        elif cur_kind == "url" and cur_url:
                            rect = (x_draw, y_line - 2, x_draw + w, y_line + FONT_CODE + 2)
                            self.c.linkURL(cur_url, rect, relative=0)
                        x_draw += w
                        cur_buf = ""

                    for ch_data in line_chars:
                        kind, ch, slug, url = ch_data
                        if kind != cur_kind or slug != cur_slug or url != cur_url:
                            flush()
                            cur_kind = kind
                            cur_slug = slug
                            cur_url = url
                        cur_buf += ch
                    flush()

                x_cur += col_widths[ci]

            self.y = y_top_row - rh

        # 先確保表頭 + 第一資料列能放得下(避免「孤兒表頭」)
        # 第一資料列若存在,需保留至少 1 列空間
        first_data_h = row_heights[1] if len(row_heights) > 1 else 0
        # 跨頁判斷要保留頁碼空間(12pt buffer)
        if self.y - (header_h + first_data_h) < MARGIN_B + 12:
            self.new_page()

        # 繪製表頭
        _draw_one_row(0, is_header=True)

        # 繪製資料列(每列前檢查是否跨頁)
        # 頁碼位於 y=MARGIN_B-0.2,字高 9pt,所以 row 底部必須在 MARGIN_B + 12 以上
        # 避免 row 文字行高擠壓到頁碼區
        _table_safe_b = MARGIN_B + 12
        for ri in range(1, len(cleaned)):
            rh = row_heights[ri]
            # 跨頁檢查:該列放不下 → 換頁 + 重畫表頭
            if self.y - rh < _table_safe_b:
                self.new_page()
                _draw_one_row(0, is_header=True)
            _draw_one_row(ri, is_header=False)

        # 重設文字色
        self.c.setFillColorRGB(*COLOR_TEXT)
        self.y -= 10  # 表格後預留間距


# ========== MD 解析 ==========
def parse_markdown(md):
    lines = md.split("\n")
    ins = []
    in_code = False
    code_buf = []
    in_table = False
    table_buf = []

    def flush_table():
        nonlocal in_table, table_buf
        if in_table and table_buf:
            parsed = []
            for row in table_buf:
                row = row.strip()
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|"):
                    row = row[:-1]
                # v6.18 / 2026-05-13 修補:split 表格欄分隔符 | 時,跳過反引號 `...` 內的 |
                # 例:| `|` | 垂直連線 | 之前會被誤判成 3 欄(`,`空, 垂直連線),
                #     造成右欄沒標題、內容擠壓。
                # 演算法:逐字掃描,記錄 backtick 計數;backtick 奇數時的 | 視為文字
                cells = []
                cur = ""
                in_bt = False
                for ch in row:
                    if ch == "`":
                        in_bt = not in_bt
                        cur += ch
                    elif ch == "|" and not in_bt:
                        cells.append(cur.strip())
                        cur = ""
                    else:
                        cur += ch
                cells.append(cur.strip())
                parsed.append(cells)
            ins.append(("table", parsed, None))
        in_table = False
        table_buf = []

    for raw in lines:
        if raw.strip() == "<!-- pagebreak -->":
            flush_table()
            ins.append(("pagebreak", None, None))
            continue

        if raw.strip().startswith("```"):
            flush_table()
            if in_code:
                ins.append(("code", code_buf, None))
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(raw)
            continue

        if raw.strip().startswith("|"):
            if not in_table:
                in_table = True
            table_buf.append(raw)
            continue
        else:
            if in_table:
                flush_table()

        line = raw.rstrip()

        if line.startswith("# "):
            ins.append(("h1", line[2:], None))
        elif line.startswith("## "):
            txt = line[3:]
            ins.append(("h2", txt, to_slug(txt)))
        elif line.startswith("### "):
            txt = line[4:]
            ins.append(("h3", txt, to_slug(txt)))
        elif line.startswith("#### "):
            txt = line[5:]
            ins.append(("h4", txt, to_slug(txt)))
        elif line.startswith("##### "):
            # v4.10.3 新增:h5 支援(原本會被當 para 渲染,無 orphan 保護)
            txt = line[6:]
            ins.append(("h5", txt, to_slug(txt)))
        elif line.strip() == "---":
            ins.append(("hr", None, None))
        elif line.strip() == "":
            ins.append(("blank", None, None))
        elif line.startswith("- ") or line.startswith("* "):
            ins.append(("bullet_0", line[2:], None))
        elif line.startswith("  - ") or line.startswith("  * "):
            ins.append(("bullet_1", line[4:], None))
        elif line.startswith("    - ") or line.startswith("    * "):
            ins.append(("bullet_2", line[6:], None))
        elif re.match(r"^\d+\.\s", line):
            ins.append(("numbered", line, None))
        elif line.startswith(">"):
            ins.append(("quote", line.lstrip("> "), None))
        else:
            ins.append(("para", line, None))

    flush_table()
    return ins


def render_pdf(md_path, pdf_path):
    register_fonts()
    # v6.21 / 2026-06-28:讀取 md 同層 pdf_meta.cfg 決定 PDF 標題/主題(三專案共用)
    _pdf_title, _pdf_author, _pdf_subject = load_pdf_meta(md_path)
    with open(md_path, encoding="utf-8") as f:
        md = f.read()

    # 字符相容性檢查:警告 md 中字型不支援的字符(避免渲染為空白方框)
    # v6.18 / 2026-05-14:檢查邏輯也對齊 register_fonts 的 fallback 順序
    try:
        import os
        from fontTools.ttLib import TTCollection
        _check_candidates = [
            r"C:\Windows\Fonts\YuGothR.ttc",
            r"C:\Windows\Fonts\yugothr.ttc",
            r"C:\Windows\Fonts\YuGothM.ttc",
            "/Library/Fonts/YuGothic.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]
        _check_path = next((p for p in _check_candidates if os.path.exists(p)), None)
        if _check_path:
            ttc_r = TTCollection(_check_path)
            cmap = ttc_r.fonts[0].getBestCmap()
            missing = {}
            for ch in md:
                if ord(ch) < 32:
                    continue
                if ord(ch) not in cmap:
                    missing[ch] = missing.get(ch, 0) + 1
            if missing:
                print("⚠ 警告:以下字符字型不支援,將渲染為空白方框:")
                for ch, count in sorted(missing.items(), key=lambda x: -x[1]):
                    print(f"   '{ch}' U+{ord(ch):04X} 共 {count} 次  → 建議改用文字(OK/NG/通過/不通過)")
    except Exception as e:
        print(f"字符檢查跳過: {e}")

    # ── 標題寬度檢查(v5.11 / 2026-04-28 新增)──
    # 根本問題:draw_h1/h2/h3/h4/h5 用 drawString 畫單行標題,沒呼叫 wrap()
    # 標題太長時會超出 PDF 右邊界被裁掉、或溢出頁面邊界跨頁切割
    # 解法:用 reportlab 的 stringWidth 真實量測(不是估算!),超寬就 raise SystemExit
    try:
        from reportlab.pdfbase import pdfmetrics as _pm
        avail_w = MARGIN_R_X - MARGIN_L  # A4 內文寬 ≈ 495.3pt
        size_map = {1: FONT_H1, 2: FONT_H2, 3: FONT_H3, 4: FONT_H4, 5: FONT_H4}
        long_titles = []
        in_code_block = False
        for line_no, raw in enumerate(md.splitlines(), 1):
            # 跳過 code block 內的 # 行(不是真標題)
            if raw.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            m = re.match(r'^(#{1,5})\s+(.+?)\s*$', raw)
            if not m:
                continue
            level = len(m.group(1))
            text = m.group(2)
            font_size = size_map.get(level, FONT_H4)
            # H1~H5 都用 NotoCJK-Bold
            actual_w = _pm.stringWidth(text, "NotoCJK-Bold", font_size)
            if actual_w > avail_w:
                long_titles.append((line_no, level, text, actual_w))
        if long_titles:
            print(f"\n⚠ 標題超出可用寬度 {avail_w:.1f}pt(將被裁掉或跨頁切割):")
            for line_no, level, text, w in long_titles:
                over = w - avail_w
                print(f"   L{line_no:5d} H{level} 寬度 {w:.0f}pt(超出 {over:.0f}pt):")
                print(f"          {text[:80]}")
            print(f"\n  建議:把長標題拆成短標題 + 列表內容,例如:")
            print(f"    原:#### v5.11 / 2026-04-28:A + B + C + D")
            print(f"    改:#### v5.11 / 2026-04-28")
            print(f"       後面用 - A / - B / - C / - D 列表呈現")
            raise SystemExit(1)
        else:
            print(f"✓ 標題寬度檢查通過(全部 ≤ {avail_w:.0f}pt)")
    except SystemExit:
        raise
    except Exception as e:
        print(f"標題寬度檢查跳過: {e}")

    ins = parse_markdown(md)

    b = PDFBuilder(pdf_path, pdf_title=_pdf_title,
                   pdf_author=_pdf_author, pdf_subject=_pdf_subject)

    def estimate_height(idx, max_items=8):
        """概估 idx 起始的後續區塊到下個 h2/h3/h4 為止的高度"""
        h = 0
        cnt = 0
        for k in range(idx, len(ins)):
            if cnt >= max_items:
                break
            kk = ins[k][0]
            tt = ins[k][1] if ins[k][1] else ""
            if kk in ("h2", "h3", "h4", "h5"):
                if k > idx:  # 遇到下個標題就停
                    break
                # 自己是標題,計入
                if kk == "h2":
                    h += 50
                elif kk == "h3":
                    h += 30
                else:
                    h += 25
            elif kk == "para" or kk == "numbered":
                txt = tt
                # 估行數:全寬可塞 ≈ 50 中文字
                lines_n = max(1, len(txt) // 50 + 1)
                h += lines_n * LINE_H_BODY
            elif kk == "bullet_0" or kk == "bullet_1" or kk == "bullet_2":
                lines_n = max(1, len(tt) // 48 + 1)
                h += lines_n * LINE_H_BODY
            elif kk == "code":
                # v6.19 / 2026-05-17 修補:超過一頁的 code block 對 lookahead 來說,
                # 只報「最多一頁」高度。否則 needs_pagebreak 會把 H 推下頁也沒用
                # (下頁也塞不下),反而造成 P130 整頁空白現象。
                raw_h = len(tt) * LINE_H_CODE + 11
                page_avail = Y_TOP - MARGIN_B  # ≈ 683pt
                h += min(raw_h, page_avail - 50)
            elif kk == "quote":
                lines_n = max(1, len(tt) // 50 + 1)
                h += lines_n * LINE_H_BODY + 13
            elif kk == "table":
                # v6.18 / 2026-05-12 第二輪重寫:table 自己會跨頁,不再算「整表整塊高度」
                # 舊版用 `max_cell_len // 20` 估行數,對長 cell 容易高估 5~10 倍
                # 例:v5.16 表格某 cell 250 字 → 估 13 行 = 169pt;實際 wrap 後僅 5 行 = 65pt
                # 修正:對於 needs_pagebreak 場景,只算表頭 + 前 2 列高度(因為表格已可跨頁)
                # 取最多前 3 列估算,且每列高度上限 35pt(2 行)
                table_h = 0
                for ri, row in enumerate(tt[:3]):  # 最多前 3 列
                    max_cell_len = max((len(c) for c in row), default=0)
                    lines_n = max(1, min(2, max_cell_len // 25 + (1 if max_cell_len % 25 else 0)))
                    row_h = max(18, lines_n * 13 + 5)
                    table_h += row_h
                # 不論實際表格多大,本估算只報「表頭 + 前 2 列」高度(實際表格可跨頁)
                h += table_h + 10
            elif kk == "blank":
                h += 3
            cnt += 1
        return h

    def needs_pagebreak_for_h3_or_h4(idx):
        """遇到 h3/h4/h5 時:確保本標題 + 其後緊接區塊能塞下

        v6.18 / 2026-05-12 第二輪重寫:配合表格逐列跨頁,大幅放寬 orphan 條件
        - 舊邏輯:收集後 6 個區塊高度,若塞不下整組推下頁 → 大表格把短標題推下,
          前頁留大空白(本輪實測 p21/p30/p83 都是此問題)
        - 新邏輯:只看「H4 + 緊接 2 個非標題區塊」+ 60pt buffer
          - 表格自己會跨頁,不必把整個表格擋下來
          - 只保證標題 + 第一段內容不會分離
        - h3 的「下個標題」仍只認 h2/h3(子結構保護)
        - h4 的「下個標題」只認 h2/h3/h4
        - h5 的「下個標題」認 h2/h3/h4/h5

        v6.19 / 2026-05-17 修補:H4 緊接 H5 時透視看 H5 的後續區塊
        - 場景:### A4.7 H4 → ##### A 子標題 H5 → bullet list
        - 舊邏輯:只看到 H4 + H5(算 50pt)就以為塞得下,H4 留在頁尾
        - 新邏輯:H4 stop_at 不認 H5,把 H5 跟其後 1 個非標題區塊一起算
        """
        my_kind = ins[idx][0]
        if my_kind == "h3":
            h_self = 30
            # v6.19 / 2026-05-17:H3 也不認 H4/H5 為「下個標題」,透視看
            stop_at = {"h2", "h3"}
        elif my_kind == "h4":
            h_self = 25
            # v6.19 / 2026-05-17:H4 不再認 H5 為「下個標題」,讓 H5 的後續區塊也計入
            stop_at = {"h2", "h3", "h4"}
        else:  # h5
            h_self = 25
            stop_at = {"h2", "h3", "h4", "h5"}

        j = idx + 1
        collected = 0
        total_block_h = 0
        # v6.19 / 2026-05-17:從 2 改為 3,涵蓋「H4 + H5 + 第一條 bullet + 第二條 bullet」
        # 多層子標題場景(A4.7、4.7、11.x 等)需更多前瞻
        MAX_LOOK = 3
        while j < len(ins) and collected < MAX_LOOK:
            kk = ins[j][0]
            if kk == "blank":
                j += 1
                continue
            if kk in stop_at:
                break
            # 對於表格,只算「表頭 + 前 2 列」高度(其餘可跨頁)
            if kk == "table":
                # 簡化:表頭約 20pt,前 2 列各約 18pt
                total_block_h += 60
            elif kk in ("h5",):
                # v6.19:H5 子標題本身佔 25pt,但不停下,繼續看後續區塊
                total_block_h += 25
            else:
                total_block_h += estimate_height(j, max_items=1)
            collected += 1
            j += 1
        if collected == 0:
            total_block_h = 40
        # v6.18 重寫:buffer 從 100 改為 60(表格可分頁不必過大保留)
        need = h_self + total_block_h + 60
        return b.y - need < MARGIN_B

    def is_pseudo_heading(idx):
        """判斷:para 後面緊跟 code/table/bullet → 視為小標題,不可孤立在頁尾
        判斷條件(嚴格):
        - case A:結尾為冒號(「:」/「:」)+ 後接 code/table/bullet/numbered
        - case B:結尾為反引號/檔名後綴/結束括號 + 後接 code/table
        遞迴穿透:若下一個非 blank 是「冒號結尾的 para」,繼續往下看(視為連續引導句)
        """
        if idx >= len(ins):
            return False
        if ins[idx][0] != "para":
            return False
        txt = (ins[idx][1] or "").rstrip()
        # 找下一個非 blank 元素;若該元素是冒號結尾的 para,繼續穿透
        j = idx + 1
        max_chain = 5  # 最多穿透 5 個冒號 para
        chain_count = 0
        while j < len(ins) and chain_count < max_chain:
            kk = ins[j][0]
            if kk == "blank":
                j += 1
                continue
            # 若是 para 且冒號結尾,穿透往下找
            if kk == "para":
                pt = (ins[j][1] or "").rstrip()
                if pt.endswith(("：", ":")):
                    j += 1
                    chain_count += 1
                    continue
            # 找到非 blank、非冒號 para 的元素,停下
            break
        if j >= len(ins):
            return False
        next_kind = ins[j][0]

        # case A:結尾冒號 + 後接區塊型內容(含 bullet)
        if txt.endswith(("：", ":")):
            if next_kind in ("code", "table", "bullet_0", "bullet_1", "bullet_2", "numbered"):
                return True

        # case B:結尾為反引號/檔名後綴/結束括號 + 後接 code/table
        if txt.endswith(("`", ")", ".json", ".py", ".pyw", ".md")):
            if next_kind in ("code", "table"):
                return True

        # case C(2026-04-26 新增):純粗體 para + 後接 bullet/code/table
        # 例:「**規則 3:大角度跳線 jump_big**」「**原則 4:避免硬換頁**」
        # 整行是 **...** 包夾(可有冒號或不有),後接內容區塊
        txt_stripped = txt.strip()
        if (txt_stripped.startswith("**") and txt_stripped.endswith("**")
                and txt_stripped.count("**") == 2
                and len(txt_stripped) > 4):  # 排除單獨 ****
            if next_kind in ("code", "table", "bullet_0", "bullet_1", "bullet_2", "numbered"):
                return True

        return False

    for i, (kind, text, slug) in enumerate(ins):
        # 若 --- 緊接 h2,跳過(避免多一條線)
        if kind == "hr":
            j = i + 1
            while j < len(ins) and ins[j][0] == "blank":
                j += 1
            if j < len(ins) and ins[j][0] == "h2":
                continue
            # 一般 hr 不畫(舊版沒有獨立 hr)

        # look-ahead 換頁判斷(h5 用 h4 相同邏輯)
        if kind in ("h3", "h4", "h5"):
            if needs_pagebreak_for_h3_or_h4(i):
                b.new_page()
        elif kind == "para" and is_pseudo_heading(i):
            # 偽小標題:確保「冒號 para + 緊接第一個區塊」不分離
            # v6.18 / 2026-05-12 第二輪重寫:從 max_items=8 改為 3
            # 表格本身已會逐列跨頁,不必把整個表格擋下來。
            # 舊邏輯 8 個區塊太大,造成「冒號 para 才剛印幾行就換頁」浪費空間
            need = estimate_height(i, max_items=3) + 20
            # 仍保留:若 b.y 接近頁頂(剛換頁),不要再次換頁(避免孤標題)
            if b.y - need < MARGIN_B and b.y < 720:
                b.new_page()

        if kind == "pagebreak":
            b.new_page()
        elif kind == "h1":
            b.draw_h1(text)
        elif kind == "h2":
            # v4.10.1:估算 h2 後下一非 blank 區塊高度,傳給 draw_h2 做條件式換頁
            j = i + 1
            while j < len(ins) and ins[j][0] == "blank":
                j += 1
            next_block_h = 0
            if j < len(ins):
                next_block_h = estimate_height(j, max_items=3)
            b.draw_h2(text, slug, estimated_next_block_h=next_block_h)
        elif kind == "h3":
            b.draw_h3(text, slug)
        elif kind == "h4":
            b.draw_h4(text, slug)
        elif kind == "h5":
            b.draw_h5(text, slug)
        elif kind == "blank":
            b.y -= 3
        elif kind == "bullet_0":
            b.draw_bullet(text, 0)
        elif kind == "bullet_1":
            b.draw_bullet(text, 1)
        elif kind == "bullet_2":
            b.draw_bullet(text, 2)
        elif kind == "numbered":
            b.draw_numbered(text)
        elif kind == "quote":
            b.draw_quote(text)
        elif kind == "para":
            b.draw_para(text)
        elif kind == "code":
            b.draw_code(text)
        elif kind == "table":
            b.draw_table(text)

    total = b.page_num
    b.c.save()
    return post_process(pdf_path, b.anchors, b.pending_links, total,
                        pdf_title=_pdf_title, pdf_author=_pdf_author,
                        pdf_subject=_pdf_subject)


def post_process(pdf_path, anchors, pending_links, total_pages,
                 pdf_title=None, pdf_author=None, pdf_subject=None):
    # v6.21 / 2026-06-28:metadata 由 render_pdf 傳入(三專案共用),未傳則 fallback
    pdf_title = pdf_title or _DEFAULT_PDF_TITLE
    pdf_author = pdf_author or _DEFAULT_PDF_AUTHOR
    pdf_subject = pdf_subject or _DEFAULT_PDF_SUBJECT
    # 頁碼 overlay
    buf = BytesIO()
    c2 = canvas.Canvas(buf, pagesize=A4)
    for i in range(1, total_pages + 1):
        c2.setFont("NotoCJK", FONT_CODE)
        c2.setFillColorRGB(*COLOR_FOOTER)
        c2.drawCentredString(PAGE_W / 2, MARGIN_B - 0.2,
                             f"第 {i} 頁 / 共 {total_pages} 頁")
        c2.showPage()
    c2.save()
    buf.seek(0)

    base = PdfReader(pdf_path)
    overlay = PdfReader(buf)
    writer = PdfWriter()
    for i, page in enumerate(base.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)

    # 連結 — v6.18 / 2026-05-13 22:30 第二次修補:回退手動構建 /A → /GoTo → /D
    #
    # 歷史:
    # - 原版手動構建用 PdfReader 來源頁的 indirect_reference(被 pypdf 重排造成失效)
    # - v6.18 / 2026-05-12 21:00 改用 pypdf.annotations.Link 高階 API
    #   → 但 pypdf 5.x 的 Link.fit 寫出來是 /Dest 而非 /A,且 /Dest 第一元素是
    #     純整數而非 indirect ref,viewer 認定無效目標 → 連結點下去沒反應(工程師回報)
    # - v6.18 / 2026-05-13 22:30 修法:手動構建,page ref 用 writer.pages[pn-1].indirect_reference
    #   (writer 自己分配的 ref,不會被重排)
    #
    # PDF 規範:link annotation 的 /A action 形式是 GoTo,/D 第一元素必須是 indirect
    # reference to a page object,/XYZ x y zoom 指定目標座標
    for page_num, links in pending_links.items():
        if page_num > len(writer.pages):
            continue
        src_page = writer.pages[page_num - 1]
        # 取得來源頁現有 annots 陣列(或新建)
        src_annots = src_page.get("/Annots")
        if src_annots is None:
            src_annots = ArrayObject()
            src_page[NameObject("/Annots")] = src_annots
        elif not isinstance(src_annots, ArrayObject):
            src_annots = ArrayObject(src_annots)
            src_page[NameObject("/Annots")] = src_annots

        for (rect, slug) in links:
            if slug not in anchors:
                continue
            pn, y = anchors[slug]
            if pn > len(writer.pages):
                continue
            # 取目標頁的 writer 內 indirect reference
            target_page = writer.pages[pn - 1]
            target_ref = target_page.indirect_reference
            if target_ref is None:
                continue

            # 構建 /D destination array: [page_ref, /XYZ, x, y, zoom]
            dest = ArrayObject([
                target_ref,
                NameObject("/XYZ"),
                NullObject(),         # x (null = 不指定,保持當前 x)
                FloatObject(y),       # y (對齊視窗頂)
                NullObject(),         # zoom (null = 不改縮放)
            ])
            # 構建 /A action: GoTo destination
            action = DictionaryObject({
                NameObject("/Type"): NameObject("/Action"),
                NameObject("/S"): NameObject("/GoTo"),
                NameObject("/D"): dest,
            })
            # 構建 link annotation
            link_annot = DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([
                    FloatObject(rect[0]), FloatObject(rect[1]),
                    FloatObject(rect[2]), FloatObject(rect[3]),
                ]),
                NameObject("/Border"): ArrayObject([
                    NumberObject(0), NumberObject(0), NumberObject(0)
                ]),
                NameObject("/A"): action,
            })
            # 加入來源頁的 annots
            annot_ref = writer._add_object(link_annot)
            src_annots.append(annot_ref)

    # v6.19 / 2026-05-16 自動連結健康度檢查(內建,不依賴外部工具)
    # 工程師回報「13.11 跳到 13.8」根因是 v6.18 hack(791.89)+ VerifyLinks 放行
    # 為避免再被類似 bug 偷過去,把核心檢查內建在 post_process 內,每次產 PDF 都跑
    _link_health_problems = []
    # 檢查 1:unresolved links(slug 不在 anchors 內 → 點下沒反應)
    _unresolved_count = 0
    for _pg, _lks in pending_links.items():
        for _rect, _slug in _lks:
            if _slug not in anchors:
                _unresolved_count += 1
    if _unresolved_count > 0:
        _link_health_problems.append(f"Unresolved links: {_unresolved_count}")
    # 檢查 2:同 (page, y) 多個 anchor 共用(可能是 791.89 hack 殘留)
    _pos_to_slugs = {}
    for _slug, (_pn, _y) in anchors.items():
        _pos_to_slugs.setdefault((_pn, round(_y, 1)), []).append(_slug)
    # 過濾 sec-* alias 雙胞胎(同 H3 既有 long slug 也有 sec-N-M short slug,正常)
    _shared_pos = []
    for (_pn, _y), _slugs in _pos_to_slugs.items():
        # 排除 sec-* 跟其他 slug 配對(同 H3 兩種 alias 是正常的)
        _non_sec = [s for s in _slugs if not s.startswith('sec-')]
        if len(_non_sec) >= 2:
            _shared_pos.append((_pn, _y, _non_sec))
    if _shared_pos:
        _link_health_problems.append(
            f"同座標多 anchor 警告(可能 791.89 hack 殘留):{len(_shared_pos)} 處")
        for _pn, _y, _slugs in _shared_pos[:5]:
            _link_health_problems.append(
                f"  p{_pn} y={_y}: {', '.join(repr(s[:40]) for s in _slugs[:3])}")
    if _link_health_problems:
        import sys
        sys.stderr.write("\n⚠ 連結健康度檢查警告:\n")
        for _p in _link_health_problems:
            sys.stderr.write(f"  {_p}\n")
    else:
        import sys
        sys.stderr.write(f"✓ 連結健康度檢查通過({len(anchors)} anchors / "
                         f"{sum(len(v) for v in pending_links.values())} links)\n")

    # v5.12 / 2026-05-03 新增 PDF metadata
    # v6.21 / 2026-06-28:改用 pdf_meta.cfg 讀入的值(三專案共用)
    # 注意:reportlab Canvas.setTitle/setAuthor/setSubject 會被 pypdf 後製覆蓋,
    # 所以必須在 PdfWriter 階段重新設定 metadata。
    writer.add_metadata({
        "/Title": pdf_title,
        "/Author": pdf_author,
        "/Subject": pdf_subject,
    })

    with open(pdf_path, "wb") as f:
        writer.write(f)
    return total_pages


# ═══════════════════════════════════════════════════════════════════════════════
# VerifyLinks 整合(v6.19 / 2026-05-16)
# 工程師指示:「光檢測 PDF 的程式都越來越多了 — 合併」
# 用法:python CreatePDF.py verify <pdf路徑> [容差]
# 原始:獨立檔案 VerifyLinks.py(已併入此檔)
# ═══════════════════════════════════════════════════════════════════════════════

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine, LTChar


def verify(pdf_path, tolerance=20):
    all_pages = list(extract_pages(pdf_path))

    # 抽所有粗體標題(H2=15pt, H3=13pt, H4=11pt)
    headings = []
    for pi, pg in enumerate(all_pages):
        for el in pg:
            if isinstance(el, LTTextContainer):
                for line in el:
                    if isinstance(line, LTTextLine):
                        first = next((c for c in line if isinstance(c, LTChar)), None)
                        # v6.21 / 2026-06-23:標題粗體判定相容原漾黑(PostScript 名為
                        # GenYoGothic2TC-B,結尾 -B 而非 Bold)。游黑體/Noto 仍是 ...-Bold。
                        _fn = first.fontname if first else ""
                        _is_bold = bool(first) and (
                            "Bold" in _fn or _fn.endswith("-B") or _fn.endswith("+GenYoGothic2TC-B")
                        )
                        # v6.21 / 115/09/10:粗體檔缺席時標題與內文同字重,
                        # 靠字名判不出來 → 退回字級判定(內文 9.5pt,H4 起 11pt)。
                        # 兩條件取聯集,有真粗體時行為與舊版完全相同。
                        if not _is_bold and first and first.size >= 10.5:
                            _is_bold = True
                        if first and first.size >= 10.5 and _is_bold:
                            text = line.get_text().strip()
                            if text:
                                headings.append({
                                    "page": pi + 1, "y0": line.y0, "y1": line.y1,
                                    "size": round(first.size, 1), "text": text,
                                })

    # 所有連結
    r = PdfReader(pdf_path)
    links = []
    url_link_count = 0  # v4.10 / 2026-04-25:URL link 獨立統計(reportlab linkURL)
    for pi, p in enumerate(r.pages):
        annots = p.get("/Annots") or []
        for a in annots:
            ao = a.get_object()
            if ao.get("/Subtype") == "/Link":
                action = ao.get("/A")
                if action:
                    aobj = action.get_object()
                    if aobj.get("/S") == "/URI":
                        url_link_count += 1
                        continue
                    d = aobj.get("/D")
                    if d and len(d) >= 4:
                        for dpi, dp in enumerate(r.pages):
                            if dp.indirect_reference and dp.indirect_reference.idnum == d[0].idnum:
                                rect = ao.get("/Rect")
                                links.append({
                                    "src_page": pi + 1,
                                    "src_rect": [round(float(x), 1) for x in rect],
                                    "dest_page": dpi + 1,
                                    "dest_y": round(float(d[3]), 1),
                                })
                                break

    def find_link_text(src_page, rect):
        rx0, ry0, rx1, ry1 = rect
        for el in all_pages[src_page - 1]:
            if isinstance(el, LTTextContainer):
                for line in el:
                    if isinstance(line, LTTextLine):
                        if ry0 - 2 <= line.y0 <= ry1 + 2 and line.x0 < rx1 and line.x1 > rx0:
                            # 只取 rect 範圍內字符
                            chars = []
                            for ch in line:
                                if isinstance(ch, LTChar):
                                    if rx0 - 1 <= ch.x0 and ch.x1 <= rx1 + 2:
                                        chars.append(ch.get_text())
                            t = ''.join(chars).strip()
                            if t:
                                return t
        return "?"

    # 逐連結檢查
    problems = []
    for link in links:
        dp = link["dest_page"]
        dy = link["dest_y"]
        candidates = [h for h in headings if h["page"] == dp]
        if not candidates:
            problems.append({
                "type": "no_heading",
                "link": link,
                "reason": f"第 {dp} 頁沒有任何標題"
            })
            continue

        # 最接近的標題(依 y1 判斷)
        best = min(candidates, key=lambda c: abs(dy - c["y1"]))
        diff = dy - best["y1"]

        # 合理範圍:dest_y 應在標題頂上方 0~20pt
        # 即 diff 應 >= 0 且 <= 20
        # v6.19 / 2026-05-16 移除 v6.18 的 791.89 exception
        # v6.18 hack:「H3/H4/H5 統一跳頁頂 791.89」會導致同頁多 H3 全跳到頁頂
        # 工程師回報「點 13.11 跳到 13.8」就是這個 hack 的副作用
        # 現在改用真實 y,VerifyLinks 不再放行 791.89
        if diff < -5 or diff > tolerance:
            src_text = find_link_text(link["src_page"], link["src_rect"])
            problems.append({
                "type": "offset",
                "link": link,
                "src_text": src_text,
                "target": best,
                "diff": diff,
            })

    return links, headings, problems, url_link_count


def verify_cli(pdf="/mnt/user-data/outputs/AI_Agent.pdf", tol=20):
    """VerifyLinks 子命令入口(原 VerifyLinks.py main 邏輯)"""
    links, headings, problems, url_link_count = verify(pdf, tol)

    print(f"PDF: {pdf}")
    print(f"  總標題數: {len(headings)}")
    print(f"  總連結數: {len(links)} (內部 anchor) + {url_link_count} (URL 外部)")
    print(f"  容差: {tol}pt")
    print(f"  問題連結: {len(problems)}")
    if problems:
        print("\n" + "=" * 70)
        for i, p in enumerate(problems[:30]):
            if p["type"] == "offset":
                link = p["link"]
                t = p["target"]
                print(f"\n問題 {i+1}: 偏差 {p['diff']:+.1f}pt")
                print(f"  連結來源: 第 {link['src_page']} 頁 '{p['src_text'][:50]}'")
                print(f"  連結目標: 第 {link['dest_page']} 頁 y={link['dest_y']}")
                print(f"  最近標題: '{t['text'][:40]}' (y0={t['y0']:.1f}, y1={t['y1']:.1f})")
    else:
        print("\n✓ 所有連結都精準對齊標題")

    # ─────────────────────────────────────────────────────────────────
    # v4.10 / 2026-04-25 新增:檢查 md 中的 [text](#anchor) 是否都成功生成 PDF 連結
    # 找出「md 寫了但 PDF 沒生成」的失效連結(slug 找不到 anchor 的情況)
    # ─────────────────────────────────────────────────────────────────
    import os, re
    md_path = pdf.replace('.pdf', '.md')
    if os.path.exists(md_path):
        print("\n" + "=" * 70)
        print("【md → PDF 連結生成檢查】(v4.10 新增)")

        # v6.18 / 2026-05-12 同步 CreatePDF.to_slug:加 ⚠ ◆ ─
        # v6.21 / 2026-06-28:補反引號 `(對齊主體 to_slug L546,v6.19 已加但 verify 內嵌版漏同步)
        #   不補會誤報:標題含反引號(如「`_split`」)時,verify 版 slug 保留反引號,
        #   但主體 to_slug 與 md link target 都已去反引號 → verify 誤判 anchor 失效
        TO_SLUG_REMOVE = "、,。,()(){}〔〕[]【】《》「」『』/\\:·:!?!?★☆✓✗⚠◆─`\u2713\u2717"
        def to_slug(heading):
            s = heading.strip().lower().replace(".", "")
            for c in TO_SLUG_REMOVE:
                s = s.replace(c, "")
            return s.replace(" ", "-").replace("\t", "-").strip("-")

        md_text = open(md_path, encoding='utf-8').read()

        # 收集 md 所有標題的 slug 與 sec-N-M
        valid_slugs = set()
        valid_secs = set()  # sec-N-M
        for line in md_text.split("\n"):
            mh = re.match(r'^(#{2,5})\s+(.+)$', line)
            if mh:
                title = mh.group(2).strip()
                valid_slugs.add(to_slug(title))
                # v6.18 / 2026-05-12 修補:H3/H4/H5 都註冊 sec-N-M(對齊 CreatePDF L302/L325/L348)
                # 之前只認 H3,造成 H4 sec-N-M(如「8.4.4 節」自動轉 sec-8-4)被誤判失效
                if len(mh.group(1)) in (3, 4, 5):  # ### #### #####
                    msec = re.match(r"^(\d+)\.(\d+)", title)
                    if msec:
                        valid_secs.add(f"sec-{msec.group(1)}-{msec.group(2)}")

        # 找 md 所有 [text](#anchor)
        md_link_count = 0
        broken = []
        for text, anchor in re.findall(r'\[([^\]]+)\]\(#([^)]+)\)', md_text):
            md_link_count += 1
            if anchor in ('xxx', 'y', 'ch', '章節slug', 'sec', 'anchor', '21-...', '新-anchor'): continue
            if text in ('章節', '章節名', 'x', 'text', '文字'): continue
            # 排除明顯範例文字(anchor 含 ... 或以「新-」開頭)
            if '...' in anchor or anchor.startswith('新-'): continue
            if anchor not in valid_slugs and anchor not in valid_secs:
                broken.append(("explicit", text, anchor))

        # v4.10 / 2026-04-25 新增:檢查「[章節](#x) N.M 節」與 inline「N.M 節」自動連結
        # CreatePDF 會把它們轉成 sec-N-M,若 sec-N-M 不存在 → 連結失效
        # 注意:排除反引號內的範例文字(`N.M 節`)與 ``` 程式碼區塊內的文字
        # 簡化:先把 ``` 區塊與單反引號內容遮掉
        md_clean = re.sub(r'```.*?```', '', md_text, flags=re.DOTALL)
        md_clean = re.sub(r'`[^`]*`', '', md_clean)
        broken_sec = []
        # v6.18 / 2026-05-12 同 CreatePDF L416:加 N.M.K 節 支援(8.4.4 節 → sec-8-4)
        for m in re.finditer(r'(?<![\dA-Za-z])(\d+)\.(\d+)(?:\.\d+)?\s*節', md_clean):
            sec = f"sec-{m.group(1)}-{m.group(2)}"
            if sec not in valid_secs:
                ctx = md_clean[max(0, m.start()-30):m.end()+10].replace('\n', ' ')
                broken_sec.append((f"{m.group(1)}.{m.group(2)} 節", sec, ctx))
        # 去重
        seen = set()
        broken_sec_unique = []
        for nm, sec, ctx in broken_sec:
            key = (nm, ctx[:50])
            if key in seen: continue
            seen.add(key)
            broken_sec_unique.append((nm, sec, ctx))

        print(f"  md 中連結數: {md_link_count}")
        print(f"  PDF 中實際生成: {len(links)} anchor + {url_link_count} URL")
        if broken:
            print(f"  ✗ 顯式連結失效(anchor 找不到): {len(broken)}")
            for kind, text, anchor in broken[:10]:
                print(f"    [{text[:30]}](#{anchor[:50]})")
        else:
            print(f"  ✓ 所有 md 顯式連結都對應到實際標題")

        if broken_sec_unique:
            print(f"\n  ✗ 「N.M 節」死引用(章節不存在): {len(broken_sec_unique)}")
            for nm, sec, ctx in broken_sec_unique[:10]:
                print(f"    {nm}  ({sec})  ...{ctx[:60]}...")
            sys.exit(2)
        else:
            print(f"  ✓ 所有「N.M 節」引用都對應到實際 h3 章節")

        # ─────────────────────────────────────────────────────────────────
        # 檢查 D — 精確 link 數量 1:1 比對(v4.10 / 2026-04-25 14:30 新增)
        # 排除範例後 md 顯式 link 數應 == PDF 實際生成 link 數
        # 漏掉的常見原因:
        #   - 標題層級不被 CreatePDF 註冊 anchor(歷史 bug:h4/h5 不註冊)
        #   - draw_table / draw_bullet 沒處理 markdown link
        #   - cell 內第 2+ 個 link 被遺失
        # ─────────────────────────────────────────────────────────────────
        valid_md_links = 0
        for text, anchor in re.findall(r'\[([^\]]+)\]\(#([^)]+)\)', md_text):
            if anchor in ('xxx', 'y', 'ch', '章節slug', 'sec', 'anchor', '21-...', '新-anchor'): continue
            if text in ('章節', '章節名', 'x', 'text', '文字'): continue
            if '...' in anchor or anchor.startswith('新-'): continue
            valid_md_links += 1

        diff = valid_md_links - len(links) - url_link_count
        print(f"\n  【精確 1:1 比對】")
        print(f"  排除範例後 md 有效 link 數: {valid_md_links}")
        print(f"  PDF 實際生成 link 數:        {len(links)} anchor + {url_link_count} URL = {len(links) + url_link_count}")
        if diff > 0:
            print(f"  ✗ 失蹤連結: {diff} 個未被 CreatePDF 寫入 PDF")
            print(f"     可能原因:標題層級不註冊 anchor / 表格或 list 沒處理 link")
            sys.exit(2)
        elif diff < 0:
            print(f"  ⚠ PDF 多了 {-diff} 個連結(可能是 inline「N.M 節」自動連結)")
        else:
            print(f"  ✓ md 與 PDF link 數量精確一致")

        if broken:
            sys.exit(2)

    # ═════════════════════════════════════════════════════════════════
    # 檢查 E — 版面健康度(v6.18 / 2026-05-12 第二輪重寫新增)
    # ═════════════════════════════════════════════════════════════════
    # 過去問題:VerifyLinks 只檢查連結失效,沒檢查版面品質,造成
    #   - 「欄寬比 35:1」的表格上線多版本沒人發現
    #   - 「短章節獨占整頁」浪費紙張沒人發現
    #   - 「表格擠死」+「Pha / se A / 入 / 口」拆字
    # 本檢查抓 3 種異常:
    #   E1. md 內表格欄寬比 >= 10x → 警告(此類表會視覺擠死)
    #   E2. PDF 內某頁文字密度 < 30%(扣表頭) → 警告(可能是表格跳頁造成大空白)
    #   E3. md 內 2 欄表格 + 內容欄文字 > 80 字 → 建議改用清單
    # ═════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("【版面健康度檢查】(v6.18 / 2026-05-12 新增)")

    md_path_check = pdf.replace('.pdf', '.md')
    layout_warnings = 0

    if os.path.exists(md_path_check):
        md_full = open(md_path_check, encoding='utf-8').read()

        # E1: 表格欄寬失衡掃描
        lines_md = md_full.split('\n')
        tables_e1 = []
        cur_t = []
        for i, ln in enumerate(lines_md):
            if ln.strip().startswith('|') and ln.strip().endswith('|'):
                cur_t.append((i + 1, ln))
            else:
                if len(cur_t) >= 2:
                    tables_e1.append(cur_t)
                cur_t = []
        if cur_t:
            tables_e1.append(cur_t)

        bad_tables = []
        for tbl in tables_e1:
            if len(tbl) < 3:
                continue
            header = tbl[0][1]
            cols = [c.strip() for c in header.split('|')[1:-1]]
            n_cols = len(cols)
            if n_cols < 2:
                continue
            col_widths_md = [0] * n_cols
            for ln_no, ln in tbl:
                cells = [c.strip() for c in ln.split('|')[1:-1]]
                for ci, c in enumerate(cells[:n_cols]):
                    # 中文 2 字寬,半形 1 字寬
                    w = sum(2 if ord(ch) > 127 else 1 for ch in c)
                    if w > col_widths_md[ci]:
                        col_widths_md[ci] = w
            if not col_widths_md or min(col_widths_md) == 0:
                continue
            ratio = max(col_widths_md) / max(min(col_widths_md), 1)
            if ratio >= 10:
                bad_tables.append((tbl[0][0], n_cols, col_widths_md, ratio, cols[:3]))

        bad_tables.sort(key=lambda x: -x[3])
        if bad_tables:
            print(f"  E1. 表格欄寬失衡(比例 >= 10x): {len(bad_tables)} 個")
            for ln_no, nc, cws, ratio, cnames in bad_tables[:5]:
                cn_disp = " / ".join(cnames[:3])
                print(f"     L{ln_no}: 比 {ratio:.1f}x  ({nc}欄)  欄名: {cn_disp}")
                print(f"             欄寬(中文字): {cws}")
            if len(bad_tables) > 5:
                print(f"     ...(還有 {len(bad_tables) - 5} 個)")
            layout_warnings += len(bad_tables)
            print(f"     → 建議:渲染引擎已用雙約束欄寬演算法,實際 PDF 通常已修正")
        else:
            print(f"  E1. ✓ 無欄寬比 >= 10x 的表格")

        # E3: 2 欄表格內容過長(建議改用清單)
        e3_warnings = []
        for tbl in tables_e1:
            if len(tbl) < 3:
                continue
            header = tbl[0][1]
            cols = [c.strip() for c in header.split('|')[1:-1]]
            if len(cols) != 2:
                continue
            # 算第 2 欄(內容欄)平均字寬
            content_widths = []
            for ln_no, ln in tbl[2:]:  # 跳過表頭與分隔線
                cells = [c.strip() for c in ln.split('|')[1:-1]]
                if len(cells) >= 2:
                    w = sum(2 if ord(ch) > 127 else 1 for ch in cells[1])
                    content_widths.append(w)
            if not content_widths:
                continue
            avg = sum(content_widths) / len(content_widths)
            mx = max(content_widths)
            if mx >= 100 and avg >= 50:
                e3_warnings.append((tbl[0][0], cols, mx, avg, len(tbl) - 2))

        if e3_warnings:
            print(f"\n  E3. 2 欄表內容過長(建議改清單): {len(e3_warnings)} 個")
            for ln_no, cn, mx, avg, n_rows in e3_warnings[:3]:
                print(f"     L{ln_no}: '{cn[0]}' / '{cn[1]}'  內容欄最長 {mx} 字,平均 {avg:.0f} 字,共 {n_rows} 列")
            if len(e3_warnings) > 3:
                print(f"     ...(還有 {len(e3_warnings) - 3} 個)")
        else:
            print(f"  E3. ✓ 無 2 欄表內容過長案例")

    # E2: PDF 大空白頁掃描(用 pdfminer 抓每頁文字密度)
    # 在 verify() 內已抽過 all_pages,但這裡是 main scope,要重抽
    all_pages_e2 = list(extract_pages(pdf))
    page_density = []
    for pi, pg in enumerate(all_pages_e2):
        # 估文字佔據面積
        text_h = 0
        for el in pg:
            if isinstance(el, LTTextContainer):
                # bbox 高度
                try:
                    text_h += (el.y1 - el.y0)
                except Exception:
                    pass
        # A4 可用高度約 770pt(扣 margin)
        density = text_h / 770.0
        page_density.append((pi + 1, density))

    low_density_pages = [(p, d) for p, d in page_density if d < 0.25 and p > 1 and p < len(page_density)]
    if low_density_pages:
        # 跳過 H2 章節邊界(第一頁、目錄頁)
        print(f"\n  E2. 文字密度 < 25% 的頁面: {len(low_density_pages)} 頁")
        for p, d in low_density_pages[:5]:
            print(f"     p{p}: 密度 {d:.0%}")
        if len(low_density_pages) > 5:
            print(f"     ...(還有 {len(low_density_pages) - 5} 頁)")
        print(f"     → 可能原因:章節邊界 H2 強制換頁(若為短章節已自動合併)")
    else:
        print(f"\n  E2. ✓ 無文字密度 < 25% 的頁面(版面緊湊)")

    print()
    if layout_warnings == 0 and not low_density_pages:
        print("✓ 版面健康度檢查通過")


if __name__ == "__main__":
    import sys
    # v6.19 / 2026-05-16:整合 VerifyLinks 為 subcommand
    # 用法:
    #   python CreatePDF.py <md> <pdf>       # 產 PDF(預設)
    #   python CreatePDF.py verify <pdf>     # 跑連結驗證(原 VerifyLinks)
    #   python CreatePDF.py verify <pdf> 30  # 容差 30pt
    if len(sys.argv) >= 2 and sys.argv[1] == "verify":
        pdf_arg = sys.argv[2] if len(sys.argv) > 2 else "/mnt/user-data/outputs/AI_Agent.pdf"
        tol_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        verify_cli(pdf_arg, tol_arg)
    else:
        md = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/AI_Agent_working.md"
        pdf = sys.argv[2] if len(sys.argv) > 2 else "/mnt/user-data/outputs/AI_Agent.pdf"
        pages = render_pdf(md, pdf)
        print(f"✓ {pdf} ({pages} 頁)")
