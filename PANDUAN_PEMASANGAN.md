# PANDUAN PEMASANGAN LENGKAP
## Advanced AI Trading Bot (XAUUSD)

---

## 📥 LANGKAH 1: Download File dari GitHub

### Cara A - Menggunakan Git (Disarankan):
```bash
git clone https://github.com/gameburik1173-collab/Kalkulator-.git
cd Kalkulator-
```

### Cara B - Download Manual:
1. Buka: `https://github.com/gameburik1173-collab/Kalkulator-`
2. Klik tombol hijau **"Code"**
3. Pilih **"Download ZIP"**
4. Extract ZIP ke folder pilihan Anda, misalnya `C:\Trading_Bot\`

### File yang Akan Anda Dapatkan:
```
📁 Kalkulator-/
├── config.py              ← Konfigurasi utama (EDIT INI DULU)
├── ambil_data.py          ← Ambil data M1/M3/M5/M15
├── strategi.py            ← Strategi: Breakout+Pullback, QM, RBR/DBD
├── money_management.py    ← Lot sizing dinamis (1-2% risk)
├── self_learning.py       ← Self-learning & adaptasi
├── ai_agent.py            ← Mesin keputusan AI
├── trading_bot.py         ← Main bot (file utama yang dijalankan)
├── PANDUAN_PEMASANGAN.md  ← File ini
└── index.html             ← Compound calculator (bonus)
```

---

## 💻 LANGKAH 2: Install Python

1. Download Python dari: https://www.python.org/downloads/
2. **PENTING:** Saat install, centang ✅ **"Add Python to PATH"**
3. Klik "Install Now"
4. Verifikasi di CMD:
```bash
python --version
```
Harus muncul: `Python 3.10.x` atau lebih tinggi

---

## 📦 LANGKAH 3: Install Library yang Dibutuhkan

Buka **Command Prompt** (CMD) atau **PowerShell**, lalu jalankan:

```bash
pip install MetaTrader5
pip install pandas
pip install numpy
```

Atau jalankan sekaligus:
```bash
pip install MetaTrader5 pandas numpy
```

### Verifikasi Instalasi:
```bash
python -c "import MetaTrader5; import pandas; import numpy; print('Semua library OK!')"
```

---

## 📊 LANGKAH 4: Install & Setup MetaTrader 5

1. Download MT5 dari broker Anda (Exness, XM, FBS, OctaFX, dll)
2. Install dan **login** ke akun trading
3. Pastikan chart **XAUUSD** terbuka
4. Aktifkan Algo Trading:
   - Menu: **Tools → Options → Expert Advisors**
   - Centang: ✅ "Allow algorithmic trading"
   - Centang: ✅ "Allow DLL imports"
   - Klik OK
5. Di toolbar atas, pastikan tombol **"Algo Trading"** berwarna **hijau**

---

## ⚙️ LANGKAH 5: Edit Konfigurasi (WAJIB!)

Buka file **`config.py`** dengan Notepad atau text editor, lalu edit:

```python
BROKER_CONFIG = {
    "server": "Exness-MT5Real",    # ← Ganti dengan server broker Anda
    "login": 12345678,              # ← Ganti dengan nomor akun MT5
    "password": "YourPassword",     # ← Ganti dengan password MT5
    "symbol": "XAUUSD",            # ← Pair yang mau ditrade
    "magic_number": 202501,
}
```

### Cara Cari Nama Server:
1. Buka MetaTrader 5
2. Klik menu **File → Login to Trade Account**
3. Lihat field **"Server"** — itulah nama yang harus Anda masukkan

### Contoh Nama Server per Broker:
| Broker | Server |
|--------|--------|
| Exness | `Exness-MT5Real` atau `Exness-MT5Real2` |
| XM | `XMGlobal-MT5` |
| FBS | `FBS-Real` |
| OctaFX | `OctaFX-MT5` |
| ICMarkets | `ICMarketsSC-MT5` |

---

## 🚀 LANGKAH 6: Jalankan Bot

Buka CMD/PowerShell, masuk ke folder project:

```bash
cd C:\Trading_Bot\Kalkulator-
```

### ▶️ Mode Live Trading (bot berjalan terus):
```bash
python trading_bot.py
```

### 🔍 Mode Test Analisis (1x analisis tanpa eksekusi):
```bash
python trading_bot.py --analyze
```

### 📊 Mode Lihat Status:
```bash
python trading_bot.py --status
```

### 📈 Mode Lihat Report Performa:
```bash
python trading_bot.py --report
```

### ❓ Bantuan:
```bash
python trading_bot.py --help
```

---

## ✅ LANGKAH 7: Verifikasi Bot Berjalan

Jika berhasil, Anda akan melihat output seperti ini:

```
======================================================================
  ADVANCED TRADING BOT - Starting
======================================================================
  Symbol: XAUUSD
  Timeframes: {'trend': 'M15', 'signal': 'M5', 'micro': 'M1', 'micro_alt': 'M3'}
  Risk: 1.5% per trade
  RR Minimum: 1:2.0
  SL Range: 30-60 pips
  Max Daily Trades: 5
  Analysis Interval: 30s
======================================================================
AI Agent initialized successfully
Bot is now running. Press Ctrl+C to stop.
```

---

## 📱 LANGKAH 8: Setup Notifikasi Telegram (Opsional)

Jika ingin dapat notifikasi di HP saat ada trade:

### A. Buat Bot Telegram:
1. Buka Telegram, cari **@BotFather**
2. Ketik `/newbot`
3. Beri nama bot (contoh: "Trading Bot Saya")
4. Beri username (contoh: `mytradingbot_123_bot`)
5. Catat **TOKEN** yang diberikan

### B. Dapatkan Chat ID:
1. Kirim pesan apapun ke bot yang baru dibuat
2. Buka browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Cari field `"chat":{"id": 123456789}` — itu **Chat ID** Anda

### C. Edit `config.py`:
```python
NOTIFICATION_CONFIG = {
    "telegram_enabled": True,
    "telegram_token": "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
    "telegram_chat_id": "123456789",
    "notify_on_trade": True,
    "notify_on_signal": True,
    "notify_on_error": True,
    "daily_report": True,
}
```

---

## ⚠️ TIPS PENTING

### 🔴 GUNAKAN AKUN DEMO DULU!
- Jangan langsung pakai uang real
- Test minimal **2-4 minggu** di akun demo
- Pastikan hasilnya positif baru pindah ke real

### 🟡 Risk Management:
- Default: 1.5% risk per trade (sangat aman)
- Maksimal 5 trade per hari
- Bot berhenti otomatis jika drawdown > 5%

### 🟢 Self-Learning:
- Bot menyimpan semua trade di `trade_history.json`
- Setelah **20+ trade**, bot mulai belajar dan menyesuaikan
- Semakin banyak data, semakin pintar keputusannya

### 🔵 Cara Menghentikan Bot:
- Tekan **Ctrl+C** di terminal
- Bot akan shutdown dengan aman (tidak akan menutup trade yang sedang berjalan)

---

## 🔧 TROUBLESHOOTING (Solusi Masalah)

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| `ModuleNotFoundError: MetaTrader5` | Library belum diinstall | `pip install MetaTrader5` |
| `MT5 initialization failed` | MT5 belum dibuka | Buka MT5 dan login dulu |
| `MT5 login failed` | Server/login/password salah | Cek ulang config.py |
| `No data received for M5` | Symbol salah atau chart belum dibuka | Buka chart XAUUSD di MT5 |
| `Daily trade limit reached` | Sudah 5 trade hari ini | Normal, tunggu besok |
| `Max drawdown reached` | Loss berturut-turut | Bot istirahat otomatis, evaluasi strategi |
| Bot jalan tapi tidak trade | Belum ada sinyal valid | Normal! Bot hanya trade saat semua kondisi terpenuhi |
| `pip not recognized` | Python PATH belum diset | Reinstall Python, centang "Add to PATH" |

---

## 📋 CARA KERJA BOT (Ringkasan)

```
┌─────────────────────────────────────────────────┐
│          SETIAP 30 DETIK BOT MELAKUKAN:         │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. Ambil data candle M15, M5, M3, M1          │
│                    ↓                            │
│  2. Analisis TREND di M15                       │
│     (EMA 20/50/200, Swing High/Low)            │
│                    ↓                            │
│  3. Cari SINYAL di M5:                         │
│     • Breakout + Pullback                      │
│     • QM Pattern (Quasimodo)                   │
│                    ↓                            │
│  4. KONFIRMASI di M1/M3:                       │
│     • RBR (Rally-Base-Rally) → BUY             │
│     • DBD (Drop-Base-Drop) → SELL              │
│                    ↓                            │
│  5. AI SCORING (confidence 0-1):               │
│     • Confluence       25%                     │
│     • MTF Alignment    20%                     │
│     • Self-Learning    20%                     │
│     • Market Fit       15%                     │
│     • RR Quality       10%                     │
│     • Session          10%                     │
│                    ↓                            │
│  6. Jika confidence > threshold:               │
│     → HITUNG LOT (1-2% risk)                   │
│     → EXECUTE TRADE                            │
│                    ↓                            │
│  7. MANAGE TRADE:                              │
│     • Breakeven setelah +20 pips               │
│     • Trailing stop setelah +30 pips           │
│                    ↓                            │
│  8. CATAT HASIL → UPDATE LEARNING              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 📞 BANTUAN

Jika ada masalah atau pertanyaan:
- Buat **Issue** di GitHub: `https://github.com/gameburik1173-collab/Kalkulator-/issues`

---

*⚠️ DISCLAIMER: Bot ini untuk tujuan edukasi. Trading mengandung risiko tinggi kehilangan modal. Selalu gunakan akun demo terlebih dahulu dan jangan investasikan uang yang tidak siap Anda kehilangan.*
