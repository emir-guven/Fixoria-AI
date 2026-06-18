import streamlit as st
from openai import OpenAI
from PIL import Image
import numpy as np
import sqlite3
import hashlib
import os
import socket
from datetime import datetime
from fpdf import FPDF
import matplotlib


st.set_page_config(page_title="Fixoria AI", page_icon="🤖", layout="wide")

DB = "fixoria_v8.db"

# ===== YARDIMCI =====
def hashle(p):
    return hashlib.sha256(str(p).encode()).hexdigest()

def simdi():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_device_info():
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    except:
        hostname, ip = "Bilinmiyor", "Bilinmiyor"
    return hostname, ip

# ===== VERİTABANI =====
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        ad_soyad TEXT,
        son_giris TEXT
    )''')

    # Eski DB'den geldiyse eksik sütunları ekle
    for sql in [
        "ALTER TABLE users ADD COLUMN ad_soyad TEXT",
        "ALTER TABLE users ADD COLUMN son_giris TEXT",
        "ALTER TABLE loglar ADD COLUMN ip_adresi TEXT",
    ]:
        try:
            c.execute(sql)
            conn.commit()
        except:
            pass

    c.execute('''CREATE TABLE IF NOT EXISTS loglar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sicil_no TEXT,
        soru TEXT,
        cevap TEXT,
        foto_durum TEXT DEFAULT "Yok",
        tarih TEXT,
        ip_adresi TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_no TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        konu TEXT,
        mesaj TEXT,
        durum TEXT DEFAULT "Açık",
        oncelik TEXT DEFAULT "Normal",
        tarih TEXT DEFAULT CURRENT_TIMESTAMP,
        kapanma_tarihi TEXT,
        atanan_it TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS session_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip_adresi TEXT,
        cihaz_adi TEXT,
        giris_tarihi TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hedef_rol TEXT,
        hedef_user TEXT,
        mesaj TEXT,
        ticket_no TEXT,
        okundu INTEGER DEFAULT 0,
        tarih TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Varsayılan kullanıcılar
    for uname, pwd, role, ad in [
        ('admin', hashle('admin'), 'Yonetici',  'Admin'),
        ('99999', hashle('admin'), 'IT_Uzmani', 'Sistem Yöneticisi'),
        ('12345', hashle('1234'),  'Kullanici', 'Test Personeli'),
    ]:
        c.execute("INSERT OR IGNORE INTO users (username,password,role,ad_soyad) VALUES (?,?,?,?)",
                  (uname, pwd, role, ad))

    conn.commit()
    conn.close()


def login_user(username, password):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT role, ad_soyad FROM users WHERE username=? AND password=?",
              (username, hashle(password)))
    row = c.fetchone()
    if row:
        c.execute("UPDATE users SET son_giris=? WHERE username=?", (simdi(), username))
        conn.commit()
    conn.close()
    return row  # (role, ad_soyad) or None

def log_chat(username, role, content):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    _, ip = get_device_info()
    c.execute("INSERT INTO loglar (sicil_no, soru, cevap, tarih, ip_adresi) VALUES (?,?,?,?,?)",
              (username, content if role == "user" else "", content if role == "assistant" else "", simdi(), ip))
    conn.commit()
    conn.close()

def kaydet_session(username):
    hostname, ip = get_device_info()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO session_logs (username, ip_adresi, cihaz_adi, giris_tarihi) VALUES (?,?,?,?)",
              (username, ip, hostname, simdi()))
    conn.commit()
    conn.close()

def ticket_olustur(username, mesaj, konu="Genel"):
    import random
    ticket_no = f"FIX-{random.randint(100000,999999)}"
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO tickets (ticket_no, username, konu, mesaj, tarih) VALUES (?,?,?,?,?)",
              (ticket_no, username, konu, mesaj, simdi()))
    c.execute("""INSERT INTO notifications (hedef_rol, mesaj, ticket_no, okundu, tarih)
                 VALUES (?,?,?,?,?)""",
              ("IT_Uzmani", f"{username} kullanıcısından yeni ticket: {konu}", ticket_no, 0, simdi()))
    conn.commit()
    conn.close()
    return ticket_no

def okunmamis_bildirim_say(rol, username=None):
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        if username:
            c.execute("SELECT COUNT(*) FROM notifications WHERE (hedef_rol=? OR hedef_user=?) AND okundu=0",
                      (str(rol), str(username)))
        else:
            c.execute("SELECT COUNT(*) FROM notifications WHERE hedef_rol=? AND okundu=0", (str(rol),))
        n = c.fetchone()[0]
        conn.close()
        return n
    except:
        return 0

def bildirimleri_oku(rol, username=None):
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        if username:
            c.execute("SELECT id, hedef_rol, hedef_user, mesaj, ticket_no, okundu, tarih FROM notifications WHERE (hedef_rol=? OR hedef_user=?) ORDER BY tarih DESC LIMIT 20",
                      (str(rol), str(username)))
        else:
            c.execute("SELECT id, hedef_rol, hedef_user, mesaj, ticket_no, okundu, tarih FROM notifications WHERE hedef_rol=? ORDER BY tarih DESC LIMIT 20", (str(rol),))
        rows = c.fetchall()
        c.execute("UPDATE notifications SET okundu=1 WHERE hedef_rol=?", (str(rol),))
        if username:
            c.execute("UPDATE notifications SET okundu=1 WHERE hedef_user=?", (str(username),))
        conn.commit()
        conn.close()
        return rows
    except:
        return []

def temizle_chat(username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM loglar WHERE sicil_no=?", (username,))
    conn.commit()
    conn.close()

def gecmisi_yukle(username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT soru, cevap FROM loglar WHERE sicil_no=? ORDER BY id ASC", (username,))
    rows = c.fetchall()
    conn.close()
    mesajlar = []
    for soru, cevap in rows:
        if soru:
            mesajlar.append({"role": "user", "content": soru})
        if cevap:
            mesajlar.append({"role": "assistant", "content": cevap})
    return mesajlar

_DEJAVU_REGULAR = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans.ttf")
_DEJAVU_BOLD = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans-Bold.ttf")

def sohbeti_pdf_yap(messages, username):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", _DEJAVU_REGULAR)
    pdf.add_font("DejaVu", "B", _DEJAVU_BOLD)

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, "Fixoria AI - Sohbet Geçmişi", new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 7, f"Kullanıcı: {username}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"İndirilme Tarihi: {simdi()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for m in messages:
        rol = "Sen" if m["role"] == "user" else "Fixoria AI"
        pdf.set_font("DejaVu", "B", 11)
        pdf.set_text_color(37, 99, 235) if rol == "Sen" else pdf.set_text_color(16, 150, 90)
        pdf.cell(0, 7, f"[{rol}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 6, m["content"])
        pdf.ln(2)

    return bytes(pdf.output())

def insana_aktar(ticket_no, username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE tickets SET atanan_it=? WHERE ticket_no=?", ("99999", ticket_no))
    c.execute("INSERT INTO notifications (hedef_user, mesaj, ticket_no, okundu, tarih) VALUES (?,?,?,?,?)",
              ("99999", f"{username} kullanıcısı insan desteği talep etti: {ticket_no}", ticket_no, 0, simdi()))
    conn.commit()
    conn.close()

init_db()

# ===== TEMA =====
st.markdown("""
<style>
.stApp { background-color: #0f1117; color: #e8eaf0; }
.block-container { max-width: 950px; padding-top: 3rem !important; }
.subtitle { color: #8b95a8; text-align:center; margin-bottom:12px; font-size:1.1rem; }
.fixoria-logo { font-size:22px; font-weight:700; color:#38BDF8; padding:0.4rem 0 0.8rem 0; }
.device-box { font-size:11px; color:#64748b; background:#0f1117; border-radius:8px;
              padding:8px 10px; margin:6px 0; font-family:monospace; line-height:1.7; }
.badge { display:inline-block; background:#2563EB; color:#fff; border-radius:999px;
         font-size:11px; padding:1px 7px; margin-left:6px; }
.badge-red { background:#DC2626; }
.ticket-row { background:#1a1f2e; border-radius:10px; padding:10px 14px; margin-bottom:8px;
              border-left:3px solid #2563EB; }
.ticket-open  { border-left-color:#2563EB; }
.ticket-closed{ border-left-color:#10B981; }
.ticket-urgent{ border-left-color:#EF4444; }
.notif-item { background:#1a1f2e; border-radius:8px; padding:8px 12px; margin-bottom:6px;
              font-size:13px; border-left:3px solid #F59E0B; }
div.stButton > button {
    border-radius:999px; border:1px solid #2e3347; background:#1a1f2e;
    color:#c8cfe0; padding:0.45rem 0.9rem; font-size:14px; font-weight:500; transition:all 0.2s;
}
div.stButton > button:hover { border-color:#4a5568; background:#232a3d; color:#fff; }
[data-testid="stSidebar"] { background-color:#161b27; }
[data-testid="stFileUploader"] { background:#1a1f2e; border:1px dashed #2e3347; border-radius:12px; }
input[type="text"], input[type="password"] {
    background-color:#1a1f2e !important; color:#e8eaf0 !important;
    border:1px solid #2e3347 !important; border-radius:8px !important;
}
hr { border-color:#2e3347; }

#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; }
[data-testid="stToolbar"] { visibility: hidden !important; height: 0 !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stStatusWidget"] { visibility: hidden !important; }
.stDeployButton { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ===== SESSION STATE =====
for k, v in {
    "logged_in": False, "username": "", "role": "", "ad_soyad": "",
    "messages": [], "ai_tetikle": False, "gecici_soru": "",
    "show_analiz": False, "show_notif": False,
    "aktif_panel": "chat", "son_ticket": None
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ===== MODEL =====
@st.cache_resource(show_spinner="Model yükleniyor...")
def model_yukle():
    try:
        from tensorflow.keras.models import load_model
        if os.path.exists("keras_Model.h5") and os.path.exists("labels.txt"):
            m = load_model("keras_Model.h5", compile=False)
            with open("labels.txt", "r", encoding="utf-8") as f:
                cls = f.readlines()
            return m, cls
    except:
        pass
    return None, None

model, class_names = model_yukle()

def get_openai_api_key():
    try:
        key = st.secrets.get("OPENAI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY")

_api_key = get_openai_api_key()
try:
    client = OpenAI(api_key=_api_key) if _api_key else None
except Exception:
    client = None

# ==========================================
# GİRİŞ EKRANI
# ==========================================
if not st.session_state.logged_in:
    st.markdown("""
    <style>
    .block-container { padding-top: 12vh !important; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div style="text-align:center;font-size:32px;font-weight:700;color:#38BDF8;padding:2rem 0 0.5rem">Fixoria AI</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Kurumsal IT Destek Girişi</div>', unsafe_allow_html=True)

        with st.form("login_form"):
            log_user = st.text_input("Kullanıcı Adı", key="log_user")
            log_pass = st.text_input("Şifre", type="password", key="log_pass")
            giris = st.form_submit_button("Giriş Yap", use_container_width=True)

        if giris:
            # GÜVENLİK/ZIRH KONTROLÜ: Veritabanı çökse bile admin girişini kurtarır
            if log_user.strip().lower() == "admin" and log_pass == "admin":
                st.session_state.logged_in = True
                st.session_state.username  = "admin"
                st.session_state.role      = "Yonetici"
                st.session_state.ad_soyad  = "Sistem Yöneticisi (Admin)"
                kaydet_session("admin")
                st.rerun()
            else:
                row = login_user(log_user, log_pass)
                if row:
                    st.session_state.logged_in = True
                    st.session_state.username  = log_user
                    st.session_state.role      = row[0]
                    st.session_state.ad_soyad  = row[1] or log_user
                    kaydet_session(log_user)
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı!")

# ==========================================
# ANA UYGULAMA
# ==========================================
else:
    # ZIRH: Eğer admin ise rolün boş kalmasını engelliyoruz
    if st.session_state.username.lower() == "admin":
        st.session_state.role = "Yonetici"

    hostname, ip = get_device_info()
    bildirim_sayisi = okunmamis_bildirim_say(st.session_state.role, st.session_state.username)

    # -------- SIDEBAR --------
    with st.sidebar:
        st.markdown('<div class="fixoria-logo">Fixoria AI</div>', unsafe_allow_html=True)
        st.markdown("---")

        rol_etiketi = {"Yonetici": "🔴 Yönetici", "IT_Uzmani": "🔵 IT Uzmanı", "Kullanici": "🟢 Personel"}.get(st.session_state.role, st.session_state.role)
        st.markdown(f"**{st.session_state.ad_soyad}**")
        st.markdown(f"{rol_etiketi}")

        try:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("SELECT son_giris FROM users WHERE username=?", (st.session_state.username,))
            son_giris = c.fetchone()
            conn.close()
            son_giris_txt = son_giris[0] if son_giris and son_giris[0] else "—"
        except:
            son_giris_txt = "—"

        st.markdown(f"""<div class="device-box">
🖥 {hostname}<br>
🌐 {ip}<br>
🕐 Son giriş: {son_giris_txt}
</div>""", unsafe_allow_html=True)

        st.markdown("---")

        if st.button(f"🔔 Bildirimler", use_container_width=True):
            st.session_state.show_notif = not st.session_state.show_notif
            st.session_state.aktif_panel = "notif"
            st.rerun()

        if st.button("🆕 Yeni Sohbet", use_container_width=True):
            st.session_state.messages = []
            st.session_state.son_ticket = None
            st.session_state.aktif_panel = "chat"
            st.session_state.show_notif = False
            st.rerun()

        if st.button("💬 Sohbet", use_container_width=True):
            st.session_state.aktif_panel = "chat"
            st.session_state.show_notif = False
            st.rerun()

        if st.button("📸 Görsel Analiz", use_container_width=True):
            st.session_state.aktif_panel = "analiz"
            st.session_state.show_notif = False
            st.rerun()

        if st.button("🎫 Ticketlarım", use_container_width=True):
            st.session_state.aktif_panel = "tickets"
            st.session_state.show_notif = False
            st.rerun()

        if st.button("📜 Geçmiş", use_container_width=True):
            st.session_state.aktif_panel = "gecmis"
            st.session_state.show_notif = False
            st.rerun()

        # DÜZELTİLDİ / SÜPER ZIRH: Admin kelimesini görünce butonları şak diye basar
        if st.session_state.role in ("IT_Uzmani", "Yonetici") or st.session_state.username.lower() == "admin":
            if st.button("🖥 IT Paneli", use_container_width=True):
                st.session_state.aktif_panel = "it_panel"
                st.rerun()

        if st.session_state.role == "Yonetici" or st.session_state.username.lower() == "admin":
            if st.button("👑 Yönetici Paneli", use_container_width=True):
                st.session_state.aktif_panel = "yonetici"
                st.rerun()

        st.markdown("---")
        if st.button("🚪 Çıkış Yap", use_container_width=True):
            for k in ["logged_in","username","role","ad_soyad","messages","aktif_panel"]:
                st.session_state[k] = False if k=="logged_in" else ([] if k=="messages" else "")
            st.session_state.son_ticket = None
            st.rerun()

    # -------- ANA İÇERİK --------
    st.markdown('<div style="text-align:center;font-size:32px;font-weight:700;color:#38BDF8;padding:0.3rem 0 0.1rem">Fixoria AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Akıllı Teknik Destek Asistanı</div>', unsafe_allow_html=True)

    if client is None:
        st.warning("⚠️ OPENAI_API_KEY bulunamadı. Ya `.streamlit/secrets.toml` dosyasına `OPENAI_API_KEY = \"sk-...\"` satırını ekleyin, ya da sistem ortam değişkeni olarak tanımlayın. Streamlit Cloud'da bu, Settings > Secrets kısmından yapılır.")

    if bildirim_sayisi > 0:
        st.info(f"🔔 {bildirim_sayisi} okunmamış bildiriminiz var.")

    # ======== PANEL: BİLDİRİMLER ========
    if st.session_state.aktif_panel == "notif":
        st.subheader("🔔 Bildirimler")
        rows = bildirimleri_oku(st.session_state.role, st.session_state.username)
        if not rows:
            st.info("Bildirim yok.")
        for r in rows:
            st.markdown(f'<div class="notif-item">🎫 <b>{r[4]}</b> — {r[3]}<br><small style="color:#64748b">{r[6]}</small></div>', unsafe_allow_html=True)

    # ======== PANEL: GEÇMİŞ ========
    elif st.session_state.aktif_panel == "gecmis":
        st.subheader("📜 Sohbet Geçmişi")
        gecmis_mesajlar = gecmisi_yukle(st.session_state.username)

        col_a, col_b = st.columns(2)
        with col_a:
            if gecmis_mesajlar:
                st.download_button(
                    "📥 Sohbeti İndir (PDF)",
                    data=sohbeti_pdf_yap(gecmis_mesajlar, st.session_state.username),
                    file_name=f"fixoria_sohbet_{st.session_state.username}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        with col_b:
            if st.button("🗑 Geçmişi Temizle", use_container_width=True):
                temizle_chat(st.session_state.username)
                st.session_state.messages = []
                st.toast("Geçmiş temizlendi!")
                st.rerun()

        st.markdown("---")

        if not gecmis_mesajlar:
            st.info("Henüz kayıtlı sohbet geçmişi yok.")
        else:
            for msg in gecmis_mesajlar:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

    # ======== PANEL: SOHBET ========
    elif st.session_state.aktif_panel == "chat":
        col1, col2, col3 = st.columns(3)
        if col1.button("🌐 İnternet Gitti", use_container_width=True):
            st.session_state.gecici_soru = "İnternet bağlantım koptu, ne yapmalıyım?"
            st.session_state.ai_tetikle = True
            st.rerun()
        if col2.button("🖨️ Yazıcı Çalışmıyor", use_container_width=True):
            st.session_state.gecici_soru = "Yazıcıdan çıktı alamıyorum."
            st.session_state.ai_tetikle = True
            st.rerun()
        if col3.button("🔐 Giriş Yapamıyorum", use_container_width=True):
            st.session_state.gecici_soru = "Sisteme giriş yapamıyorum şifrem hata veriyor."
            st.session_state.ai_tetikle = True
            st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if st.session_state.son_ticket:
            if st.button("🙋 İnsan Desteğine Aktar", use_container_width=True, key="insana_aktar_btn"):
                insana_aktar(st.session_state.son_ticket, st.session_state.username)
                st.success(f"Talebiniz insan IT desteğine iletildi. Ticket: {st.session_state.son_ticket}")

        kullanici_girisi = st.chat_input("Teknik sorununuzu buraya yazın...")

        if kullanici_girisi or st.session_state.ai_tetikle:
            soru = kullanici_girisi if kullanici_girisi else st.session_state.gecici_soru
            st.session_state.ai_tetikle = False

            with st.chat_message("user"):
                st.markdown(soru)
            st.session_state.messages.append({"role": "user", "content": soru})
            log_chat(st.session_state.username, "user", soru)

            if client:
                rol = st.session_state.role
                if rol == "IT_Uzmani":
                    system_p = ("Sen Fixoria AI adında Kıdemli IT Sistem Mühendisisin. "
                                "Karşındaki IT personeli/sistem yöneticisi. Detaylı teknik analiz yap. "
                                "PowerShell/CMD/Bash komutları ver, root-cause analizi yap. "
                                "Teknik servise başvurun deme. Türkçe yaz. Markdown kullanma.")
                elif rol == "Yonetici":
                    system_p = ("Sen Fixoria AI adında kurumsal IT asistanısın. "
                                "Karşındaki üst düzey yönetici. Hem teknik hem yönetimsel bakış açısıyla yanıt ver. "
                                "Türkçe yaz.")
                else:
                    system_p = ("Sen Fixoria AI adlı kurumsal IT teknik destek asistanısın. "
                                "Bilgisayar, internet, yazıcı, yazılım, donanım konularında yardım et. "
                                "En fazla 5 adım ver. Kesin teşhis koyma. Türkçe yaz. Markdown kullanma.")

                with st.chat_message("assistant"):
                    with st.spinner("Yanıtlanıyor..."):
                        try:
                            api_msgs = [{"role": "system", "content": system_p}]
                            for m in st.session_state.messages:
                                api_msgs.append({"role": m["role"], "content": m["content"]})

                            resp = client.chat.completions.create(
                                model="gpt-4o-mini", messages=api_msgs
                            )
                            cevap = resp.choices[0].message.content

                            ticket_no = ticket_olustur(
                                st.session_state.username, soru,
                                konu=soru[:50] + ("..." if len(soru) > 50 else "")
                            )
                            st.session_state.son_ticket = ticket_no
                            cevap_tam = f"{cevap}\n\n🎫 Ticket No: {ticket_no}"

                            st.markdown(cevap_tam)
                            st.session_state.messages.append({"role": "assistant", "content": cevap_tam})
                            log_chat(st.session_state.username, "assistant", cevap_tam)
                        except Exception as e:
                            st.error(f"Hata: {e}")
            else:
                with st.chat_message("assistant"):
                    st.error("⚠️ AI bağlantısı kurulamadı. OPENAI_API_KEY ne `.streamlit/secrets.toml` dosyasında ne de ortam değişkenlerinde bulunamadı. Lütfen birini tanımlayın.")

    # ======== PANEL: GÖRSEL ANALİZ ========
    elif st.session_state.aktif_panel == "analiz":
        st.subheader("📸 Görsel ile Donanım Analizi")
        dosya = st.file_uploader("Arızalı cihazın fotoğrafını yükleyin", type=["jpg","png","jpeg"])

        if dosya:
            if model is None:
                st.warning("Model yüklenemedi. Görsel analiz devre dışı.")
            else:
                col_img, col_res = st.columns([1, 2])
                image = Image.open(dosya).convert("RGB")
                with col_img:
                    st.image(image, caption="Yüklenen Görsel", use_column_width=True)
                with col_res:
                    with st.spinner("Analiz ediliyor..."):
                        img_r = image.resize((224, 224))
                        arr = (np.asarray(img_r).astype(np.float32) / 127.5) - 1
                        data = np.ndarray(shape=(1,224,224,3), dtype=np.float32)
                        data[0] = arr
                        pred = model.predict(data)
                        idx = np.argmax(pred)
                        cls_name = class_names[idx].strip()
                        conf = pred[0][idx]

                        st.info(f"**Tahmin:** {cls_name}")
                        if "arızalı" in cls_name.lower():
                            st.error("🚨 Donanım arızası tespit edildi. IT departmanına bildirin.")
                            ticket_olustur(st.session_state.username, f"Görsel analiz: {cls_name}", "Donanım Arızası")
                        elif "normal" in cls_name.lower():
                            st.success("✅ Cihaz normal görünüyor. Sorun yazılımsal olabilir.")
                        else:
                            st.warning("⚠️ Net değerlendirilemedi. Daha iyi ışıkta tekrar deneyin.")
                        st.caption(f"Güven: %{conf*100:.1f}")

    # ======== PANEL: TİCKETLARIM ========
    elif st.session_state.aktif_panel == "tickets":
        st.subheader("🎫 Ticketlarım")
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT ticket_no, konu, durum, oncelik, tarih FROM tickets WHERE username=? ORDER BY id DESC",
                  (st.session_state.username,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            st.info("Henüz ticket oluşturulmadı.")
        else:
            for r in rows:
                ticket_no, konu, durum, oncelik, tarih = r
                renk = {"Açık":"ticket-open","Kapalı":"ticket-closed","Acil":"ticket-urgent"}.get(durum,"ticket-open")
                st.markdown(f"""<div class="ticket-row {renk}">
<b>{ticket_no}</b> — {konu}<br>
<small style="color:#64748b">Durum: <b>{durum}</b> | Öncelik: {oncelik} | {tarih}</small>
</div>""", unsafe_allow_html=True)

    # ======== PANEL: IT PANELİ ========
    elif st.session_state.aktif_panel == "it_panel":
        st.subheader("🖥 IT Uzmanı Paneli")

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("""SELECT t.ticket_no, t.username, t.konu, t.durum, t.tarih, t.atanan_it
                     FROM tickets t ORDER BY t.id DESC LIMIT 50""")
        rows = c.fetchall()
        conn.close()

        col_a, col_b, col_c = st.columns(3)
        acik   = sum(1 for r in rows if r[3] == "Açık")
        kapali = sum(1 for r in rows if r[3] == "Kapalı")
        toplam = len(rows)
        col_a.metric("Toplam Ticket", toplam)
        col_b.metric("Açık", acik)
        col_c.metric("Kapalı", kapali)

        st.markdown("---")
        if not rows:
            st.info("Ticket yok.")
        for r in rows:
            ticket_no, username, konu, durum, tarih, atanan_it = r
            renk = {"Açık":"ticket-open","Kapalı":"ticket-closed","Acil":"ticket-urgent"}.get(durum,"ticket-open")
            atanan_etiket = f' | 🙋 İnsan Desteği: <b>{atanan_it}</b>' if atanan_it else ""
            col1, col2 = st.columns([4,1])
            with col1:
                st.markdown(f"""<div class="ticket-row {renk}">
<b>{ticket_no}</b> | 👤 {username}<br>
{konu}<br>
<small style="color:#64748b">Durum: <b>{durum}</b> | {tarih}{atanan_etiket}</small>
</div>""", unsafe_allow_html=True)
            with col2:
                if durum == "Açık":
                    if st.button("✅ Kapat", key=f"kapat_{ticket_no}"):
                        conn2 = sqlite3.connect(DB)
                        c2 = conn2.cursor()
                        c2.execute("UPDATE tickets SET durum='Kapalı', kapanma_tarihi=? WHERE ticket_no=?",
                                   (simdi(), ticket_no))
                        c2.execute("INSERT INTO notifications (hedef_user, mesaj, ticket_no, okundu, tarih) VALUES (?,?,?,?,?)",
                                   (username, f"Ticketınız çözüldü: {konu[:40]}", ticket_no, 0, simdi()))
                        conn2.commit()
                        conn2.close()
                        st.rerun()

    # ======== PANEL: YÖNETİCİ PANELİ ========
    elif st.session_state.aktif_panel == "yonetici":
        if st.session_state.role != "Yonetici" and st.session_state.username.lower() != "admin":
            st.error("Erişim reddedildi.")
        else:
            st.subheader("👑 Yönetici Paneli")
            tab1, tab2, tab3, tab4 = st.tabs(["📊 Genel", "👥 Kullanıcılar", "🎫 Tüm Ticketlar", "📋 Oturum Logları"])

            with tab1:
                conn = sqlite3.connect(DB)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM users")
                u_say = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM tickets")
                t_say = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM tickets WHERE durum='Açık'")
                a_say = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM session_logs")
                s_say = c.fetchone()[0]
                conn.close()

                col1,col2,col3,col4 = st.columns(4)
                col1.metric("Toplam Kullanıcı", u_say)
                col2.metric("Toplam Ticket", t_say)
                col3.metric("Açık Ticket", a_say)
                col4.metric("Toplam Oturum", s_say)

            with tab2:
                conn = sqlite3.connect(DB)
                c = conn.cursor()
                c.execute("SELECT username, ad_soyad, role, son_giris FROM users ORDER BY id")
                kullanicilar = c.fetchall()
                conn.close()

                for u in kullanicilar:
                    rol_r = {"Yonetici":"🔴","IT_Uzmani":"🔵","Kullanici":"🟢"}.get(u[2],"⚪")
                    st.markdown(f"""<div class="ticket-row">
{rol_r} <b>{u[0]}</b> — {u[1] or "—"}<br>
<small style="color:#64748b">Rol: {u[2]} | Son giriş: {u[3] or "—"}</small>
</div>""", unsafe_allow_html=True)

                # DÜZELTİLDİ: Admin girişi kesinleştirildi
                if st.session_state.role == "Yonetici" or st.session_state.username.lower() == "admin":
                    st.markdown("**Yeni Kullanıcı Ekle**")
                    c1, c2, c3, c4 = st.columns(4)
                    yeni_u = c1.text_input("Kullanıcı Adı", key="yeni_u")
                    yeni_p = c2.text_input("Şifre", type="password", key="yeni_p")
                    yeni_ad = c3.text_input("Ad Soyad", key="yeni_ad")
                    yeni_rol = c4.selectbox("Rol", ["Kullanici", "IT_Uzmani", "Yonetici"], key="yeni_rol")
                    
                    if st.button("➕ Kullanıcı Ekle"):
                        if yeni_u and yeni_p:
                            try:
                                conn2 = sqlite3.connect(DB)
                                c2e = conn2.cursor()
                                c2e.execute("INSERT INTO users (username,password,role,ad_soyad) VALUES (?,?,?,?)",
                                           (yeni_u, hashle(yeni_p), yeni_rol, yeni_ad))
                                conn2.commit()
                                conn2.close()
                                st.success(f"{yeni_u} eklendi!")
                                st.rerun()
                            except:
                                st.error("Bu kullanıcı adı zaten var.")
                        else:
                            st.warning("Kullanıcı adı ve şifre zorunlu.")
                else:
                    st.info("🔒 Yeni kullanıcı ekleme yetkisi sadece **admin** hesabına aittir.")

            with tab3:
                conn = sqlite3.connect(DB)
                c = conn.cursor()
                c.execute("SELECT ticket_no, username, konu, durum, oncelik, tarih FROM tickets ORDER BY id DESC")
                tüm_t = c.fetchall()
                conn.close()

                filtre = st.selectbox("Filtrele", ["Hepsi","Açık","Kapalı","Acil"])
                for r in tüm_t:
                    if filtre != "Hepsi" and r[3] != filtre:
                        continue
                    renk = {"Açık":"ticket-open","Kapalı":"ticket-closed","Acil":"ticket-urgent"}.get(r[3],"ticket-open")
                    st.markdown(f"""<div class="ticket-row {renk}">
<b>{r[0]}</b> | 👤 {r[1]}<br>
{r[2]}<br>
<small style="color:#64748b">Durum: {r[3]} | Öncelik: {r[4]} | {r[5]}</small>
</div>""", unsafe_allow_html=True)

            with tab4:
                conn = sqlite3.connect(DB)
                c = conn.cursor()
                c.execute("SELECT username, ip_adresi, cihaz_adi, giris_tarihi FROM session_logs ORDER BY id DESC LIMIT 100")
                logs = c.fetchall()
                conn.close()

                for l in logs:
                    st.markdown(f"""<div class="ticket-row" style="border-left-color:#8B5CF6">
👤 <b>{l[0]}</b> | 🌐 {l[1]} | 🖥 {l[2]}<br>
<small style="color:#64748b">🕐 {l[3]}</small>
</div>""", unsafe_allow_html=True)