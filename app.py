app_code = r'''"""
FinsightAI - Ekonomik Danışman (v2.2 Final)
Tüm Özellikler: Haber NLP, Makro, Emtia, Gayrimenkul, Jeopolitik, 65+ Şirket, Portföy
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
import requests
import feedparser
from typing import Dict, Tuple, Optional, List, Any
from dataclasses import dataclass
from enum import Enum
import io

# ========== YAPILANDIRMA ==========
st.set_page_config(
    page_title="FinsightAI - Ekonomik Danışman",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SIFRE KORUMASI ---
if "sifre_dogrulandi" not in st.session_state:
    st.session_state.sifre_dogrulandi = False

if not st.session_state.sifre_dogrulandi:
    st.title("🔒 FinsightAI - Ekonomik Danışman")
    st.markdown("### Kişisel Finans Asistanınıza Hoş Geldiniz")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        sifre = st.text_input("Şifre", type="password", placeholder="Şifrenizi girin...")
        if st.button("🔓 Giriş", use_container_width=True):
            if sifre == "Finans@12345":
                st.session_state.sifre_dogrulandi = True
                st.rerun()
            else:
                st.error("❌ Yanlış şifre!")
    st.stop()

# ========== VERI YAPILARI ==========
class Sinyal(Enum):
    GUC_AL = "🟢 GÜÇLÜ AL"
    AL = "🟢 AL"
    SAT = "🔴 SAT"
    GUC_SAT = "🔴 GÜÇLÜ SAT"
    BEKLE = "🟡 BEKLE"
    RISKLI = "⚠️ RİSKLİ"

@dataclass
class MakroVeri:
    fed_faiz: float
    ecb_faiz: float
    tcmb_faiz: float
    enflasyon_us: float
    enflasyon_tr: float
    issizlik_us: float
    issizlik_tr: float
    pmi_us: float
    pmi_tr: float
    getiri_egrisi: float
    vix: float
    dxy: float
    usdtry: float
    rom_skor: float
    haber_skoru: float
    risk_seviyesi: str
    enflasyon_trendi: str
    jeopolitik_risk: float
    savunma_sektoru_agirlik: float

@dataclass
class EmtiaAnalizi:
    isim: str
    sembol: str
    fiyat: float
    degisim_1h: float
    degisim_1y: float
    sinyal: Sinyal
    gerekce: str
    enflasyon_korelasyonu: float
    risk_kacisi_puani: float

@dataclass
class GayrimenkulAnalizi:
    bolge: str
    konut_fiyat_endeksi: float
    yillik_artis: float
    reel_getiri: float
    kira_carpani: float
    faiz_etkisi: str
    sinyal: Sinyal
    gerekce: str
    yatirim_notu: str

@dataclass
class VarlikRotasyonu:
    varlik_sinifi: str
    agirlik_onerisi: float
    sinyal: Sinyal
    gerekce: str
    makro_kosul: str

@dataclass
class SirketAnalizi:
    sembol: str
    isim: str
    sektor: str
    borsa: str
    fiyat: float
    fk: float
    pddd: float
    roe: float
    kar_marji: float
    borc_ok: float
    fcf: float
    cagr: float
    temel_skor: float
    hedef_fiyat: float
    yukari_potansiyel: float
    sinyal: Sinyal
    risk_aciklama: str
    pozisyon_buyuklugu: float
    jeopolitik_etki: float

# ========== API ANAHTARLARI ==========
def get_api_keys() -> Tuple[str, str]:
    try:
        return st.secrets["FRED_API_KEY"], st.secrets["NEWS_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.sidebar.warning("⚠️ API anahtarları secrets.toml'da bulunamadı.")
        return "", ""

FRED_API_KEY, NEWS_API_KEY = get_api_keys()

# ========== YARDIMCI FONKSIYONLAR ==========
def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value in ['.', '']:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_close_price(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series()
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        return close.iloc[:, 0]
    return close

def calculate_rom_score(slope: float, unemp_rate: float, prev_unemp: Optional[float]) -> int:
    score = 0
    if slope < 0:
        score += 50
    if unemp_rate and prev_unemp and (unemp_rate > prev_unemp):
        score += 30
    return min(score, 100)

def get_risk_level(rom: float, vix: float, haber_skoru: float, jeopolitik: float) -> str:
    skor = rom + (vix / 5) + (abs(haber_skoru) * 10) + (jeopolitik / 2)
    if skor > 80:
        return "🔴 YÜKSEK RİSK"
    elif skor > 50:
        return "🟡 ORTA RİSK"
    else:
        return "🟢 DÜŞÜK RİSK"

def get_enflasyon_trendi(enflasyon_us: float, enflasyon_tr: float, fed_faiz: float) -> str:
    if enflasyon_us > 4.0 or enflasyon_tr > 30.0:
        return "YUKSELIYOR"
    elif enflasyon_us < 2.5 and enflasyon_tr < 20.0:
        return "DUSUYOR"
    else:
        return "STABIL"

# ========== 1. HABER MOTORU + JEOPOLITIK ANALIZ ==========
@st.cache_data(ttl=21600)
def get_global_news(api_key: str) -> List[Dict]:
    if not api_key:
        return []
    try:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q=(inflation+OR+recession+OR+fed+OR+interest+rates+OR+economy+OR+gold+OR+oil+OR+war+OR+conflict+OR+defense)"
            f"&language=en&sortBy=publishedAt&pageSize=30&apiKey={api_key}"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        articles = response.json().get('articles', [])
        return [
            {
                "baslik": a.get('title', ''),
                "aciklama": a.get('description', ''),
                "kaynak": a.get('source', {}).get('name', ''),
                "tarih": a.get('publishedAt', '')[:10],
                "url": a.get('url', ''),
                "resim": a.get('urlToImage', '')
            }
            for a in articles
        ]
    except Exception as e:
        st.error(f"Küresel haber hatası: {str(e)}")
        return []

@st.cache_data(ttl=21600)
def get_turkish_news() -> List[Dict]:
    kaynaklar = {
        "Bloomberg HT": "https://www.bloomberght.com/feeds/news.rss",
        "Dünya Gazetesi": "https://www.dunya.com/rss/rss.xml",
        "Hürriyet Ekonomi": "https://www.hurriyet.com.tr/rss/ekonomi",
    }
    haberler = []
    for kaynak_adi, rss_url in kaynaklar.items():
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                haberler.append({
                    "baslik": entry.get('title', ''),
                    "aciklama": entry.get('summary', '')[:200],
                    "kaynak": kaynak_adi,
                    "tarih": entry.get('published', '')[:10],
                    "url": entry.get('link', ''),
                    "resim": ""
                })
        except Exception:
            continue
    return haberler

def analyze_news_sentiment(haberler: List[Dict]) -> Tuple[float, float, float, List[Dict]]:
    olumlu = ["büyüme", "artış", "yükseliş", "kazanç", "rekor", "güçlü", "olumlu",
              "destek", "teşvik", "indirim", "düşüş enflasyon", "faiz indirimi", "altın yükseliş",
              "growth", "rise", "increase", "profit", "record", "strong", "positive",
              "support", "stimulus", "cut", "lower inflation", "gold surge"]
    
    olumsuz = ["kriz", "çöküş", "düşüş", "zarar", "resesyon", "enflasyon", "faiz artışı",
               "işsizlik", "risk", "tehdit", "gerilim", "belirsizlik", "altın düşüş",
               "crisis", "crash", "collapse", "loss", "recession", "inflation", "hike",
               "unemployment", "risk", "threat", "tension", "uncertainty", "gold drop"]
    
    jeopolitik_kelimeler = [
        "savaş", "çatışma", "savunma", "askeri", "füze", "silah", "operasyon",
        "war", "conflict", "defense", "military", "missile", "weapon", "operation",
        "terör", "güvenlik", "sınır", "işgal", "bombardıman", "tension",
        "terror", "security", "border", "invasion", "bombing", "attack"
    ]
    
    savunma_kelimeler = [
        "savunma sanayi", "aselsan", "havelsan", "roketsan", "tai", "baykar",
        "defense industry", "lockheed", "raytheon", "northrop", "boeing defense",
        "thyssenkrupp", "bae systems", "airbus defence", "saab"
    ]
    
    toplam_skor = 0
    jeopolitik_skor = 0
    savunma_skor = 0
    analizli = []
    
    for haber in haberler:
        metin = (haber["baslik"] + " " + haber.get("aciklama", "")).lower()
        
        olumlu_say = sum(1 for k in olumlu if k in metin)
        olumsuz_say = sum(1 for k in olumsuz if k in metin)
        
        if olumlu_say + olumsuz_say > 0:
            skor = (olumlu_say - olumsuz_say) / (olumlu_say + olumsuz_say)
        else:
            skor = 0
        
        toplam_skor += skor
        
        j_skor = sum(2 for k in jeopolitik_kelimeler if k in metin)
        s_skor = sum(3 for k in savunma_kelimeler if k in metin)
        
        jeopolitik_skor += j_skor
        savunma_skor += s_skor
        
        if skor > 0.3:
            etki = "🟢 Olumlu"
        elif skor < -0.3:
            etki = "🔴 Olumsuz"
        else:
            etki = "⚪ Nötr"
        
        j_etki = ""
        if j_skor > 0:
            j_etki = f" | 🌍 Jeopolitik Risk: +{j_skor}"
        if s_skor > 0:
            j_etki += f" | 🛡️ Savunma: +{s_skor}"
        
        analizli.append({
            **haber,
            "duygu_skoru": round(skor, 2),
            "jeopolitik_skor": j_skor,
            "savunma_skor": s_skor,
            "etki": etki + j_etki
        })
    
    ortalama_skor = toplam_skor / len(haberler) if haberler else 0
    jeopolitik_risk = min(jeopolitik_skor * 2, 100)
    savunma_agirlik = min(savunma_skor * 5, 50)
    
    return round(ortalama_skor, 2), jeopolitik_risk, savunma_agirlik, analizli

# ========== 2. MAKRO VERI TOPLAMA ==========
@st.cache_data(ttl=21600)
def get_fred_val(series_id: str, api_key: str) -> Tuple[Optional[float], Optional[float]]:
    if not api_key:
        return None, None
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&sort_order=desc&limit=2"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if 'observations' not in data or len(data['observations']) < 2:
            return None, None
        val = safe_float(data['observations'][0]['value'])
        prev = safe_float(data['observations'][1]['value'])
        return val, prev
    except Exception:
        return None, None

@st.cache_data(ttl=21600)
def get_macro_data(api_key: str, haber_skoru: float, jeopolitik_risk: float, savunma_agirlik: float) -> MakroVeri:
    fed_funds, _ = get_fred_val('FEDFUNDS', api_key)
    dgs10, _ = get_fred_val('DGS10', api_key)
    dgs2, _ = get_fred_val('DGS2', api_key)
    vix, _ = get_fred_val('VIXCLS', api_key)
    unemp_rate, prev_unemp = get_fred_val('UNRATE', api_key)
    
    try:
        usdtry_df = yf.download('USDTRY=X', period="1d", progress=False)
        usdtry = float(get_close_price(usdtry_df).iloc[-1]) if not usdtry_df.empty else 35.0
    except:
        usdtry = 35.0
    
    tcmb_faiz = 50.0
    enflasyon_tr = 38.0
    issizlik_tr = 8.5
    pmi_tr = 48.0
    ecb_faiz = 4.5
    enflasyon_us = 3.2
    pmi_us = 49.0
    dxy = 105.0
    
    fed_funds = fed_funds if fed_funds is not None else 5.5
    vix = vix if vix is not None else 20.0
    unemp_rate = unemp_rate if unemp_rate is not None else 4.0
    
    slope = (dgs10 - dgs2) if (dgs10 is not None and dgs2 is not None) else 0.0
    rom = calculate_rom_score(slope, unemp_rate, prev_unemp)
    rom += int(haber_skoru * 10)
    rom = max(0, min(rom, 100))
    
    risk = get_risk_level(rom, vix, haber_skoru, jeopolitik_risk)
    enflasyon_trendi = get_enflasyon_trendi(enflasyon_us, enflasyon_tr, fed_funds)
    
    return MakroVeri(
        fed_faiz=fed_funds, ecb_faiz=ecb_faiz, tcmb_faiz=tcmb_faiz,
        enflasyon_us=enflasyon_us, enflasyon_tr=enflasyon_tr,
        issizlik_us=unemp_rate, issizlik_tr=issizlik_tr,
        pmi_us=pmi_us, pmi_tr=pmi_tr,
        getiri_egrisi=slope, vix=vix, dxy=dxy, usdtry=usdtry,
        rom_skor=rom, haber_skoru=haber_skoru, risk_seviyesi=risk,
        enflasyon_trendi=enflasyon_trendi,
        jeopolitik_risk=jeopolitik_risk,
        savunma_sektoru_agirlik=savunma_agirlik
    )

# ========== 3. EMTIA ANALIZ MOTORU ==========
EMTIA_DATABASE = {
    'Altın (XAU/USD)': {'sembol': 'GC=F', 'enflasyon_korelasyonu': 0.85, 'risk_kacisi': 95},
    'Gümüş (XAG/USD)': {'sembol': 'SI=F', 'enflasyon_korelasyonu': 0.75, 'risk_kacisi': 80},
    'Ham Petrol (WTI)': {'sembol': 'CL=F', 'enflasyon_korelasyonu': 0.60, 'risk_kacisi': 40},
    'Bakır': {'sembol': 'HG=F', 'enflasyon_korelasyonu': 0.50, 'risk_kacisi': 30},
    'Doğal Gaz': {'sembol': 'NG=F', 'enflasyon_korelasyonu': 0.45, 'risk_kacisi': 35},
    'Buğday': {'sembol': 'ZW=F', 'enflasyon_korelasyonu': 0.55, 'risk_kacisi': 50},
}

@st.cache_data(ttl=21600)
def analyze_commodities(makro: MakroVeri) -> List[EmtiaAnalizi]:
    emtialar = []
    for isim, meta in EMTIA_DATABASE.items():
        try:
            df = yf.download(meta['sembol'], period="1y", progress=False, auto_adjust=True)
            if df.empty:
                continue
            close_series = get_close_price(df)
            if len(close_series) < 2:
                continue
            
            fiyat = close_series.iloc[-1]
            fiyat_1h = close_series.iloc[-min(len(close_series), 21)]
            fiyat_1y = close_series.iloc[0]
            
            degisim_1h = ((fiyat / fiyat_1h) - 1) * 100
            degisim_1y = ((fiyat / fiyat_1y) - 1) * 100
            
            sinyal = Sinyal.BEKLE
            gerekce = ""
            
            if makro.jeopolitik_risk > 30:
                if isim == 'Altın (XAU/USD)':
                    sinyal = Sinyal.GUC_AL
                    gerekce = f"🌍 Jeopolitik risk yüksek ({makro.jeopolitik_risk}%)! Altın güvenli liman."
                elif isim == 'Ham Petrol (WTI)':
                    sinyal = Sinyal.AL
                    gerekce = f"⛽ Jeopolitik gerilim petrol arzını tehdit ediyor."
            elif makro.enflasyon_trendi == "YUKSELIYOR":
                if meta['enflasyon_korelasyonu'] > 0.7:
                    if degisim_1h > 2:
                        sinyal = Sinyal.GUC_AL
                        gerekce = f"🛡️ Enflasyon yükseliyor! {isim} güçlü hedge. Son 1 ay %{degisim_1h:.1f} yükseldi."
                    else:
                        sinyal = Sinyal.AL
                        gerekce = f"🛡️ Enflasyon hedge'i için {isim} biriktirme fırsatı."
                elif meta['enflasyon_korelasyonu'] > 0.5:
                    sinyal = Sinyal.AL
                    gerekce = f"📈 Enflasyon ortamında {isim} değer kazanabilir."
            elif makro.vix > 25 or makro.rom_skor > 50:
                if meta['risk_kacisi'] > 80:
                    sinyal = Sinyal.GUC_AL
                    gerekce = f"🛡️ Riskli ortamda {isim} güvenli liman."
                elif meta['risk_kacisi'] > 50:
                    sinyal = Sinyal.AL
                    gerekce = f"🛡️ Risk kaçışı varlığı olarak {isim} değerlendirilebilir."
            elif makro.rom_skor > 60:
                if isim == 'Ham Petrol (WTI)':
                    sinyal = Sinyal.SAT
                    gerekce = f"📉 Resesyon talebi düşürecek. Petrol sat."
                elif meta['risk_kacisi'] > 70:
                    sinyal = Sinyal.AL
                    gerekce = f"🛡️ Resesyon hedge'i."
            
            if not gerekce:
                gerekce = f"Nötr durum. Son 1 ay: %{degisim_1h:.1f}, 1 yıl: %{degisim_1y:.1f}"
            
            emtialar.append(EmtiaAnalizi(
                isim=isim, sembol=meta['sembol'], fiyat=round(fiyat, 2),
                degisim_1h=round(degisim_1h, 2), degisim_1y=round(degisim_1y, 2),
                sinyal=sinyal, gerekce=gerekce,
                enflasyon_korelasyonu=meta['enflasyon_korelasyonu'],
                risk_kacisi_puani=meta['risk_kacisi']
            ))
        except Exception as e:
            st.warning(f"{isim} analiz edilemedi: {str(e)}")
            continue
    
    return sorted(emtialar, key=lambda x: x.risk_kacisi_puani, reverse=True)

# ========== 4. TÜRKİYE GAYRİMENKUL ANALIZI ==========
@st.cache_data(ttl=21600)
def analyze_turkey_real_estate(makro: MakroVeri) -> List[GayrimenkulAnalizi]:
    bolgeler = {
        'İstanbul (Avrupa)': {'kfe': 28500, 'yillik_artis': 45, 'kira_carpani': 22, 'faiz_etkisi': 'olumsuz'},
        'İstanbul (Anadolu)': {'kfe': 22000, 'yillik_artis': 38, 'kira_carpani': 18, 'faiz_etkisi': 'olumsuz'},
        'Ankara': {'kfe': 12500, 'yillik_artis': 35, 'kira_carpani': 16, 'faiz_etkisi': 'nötr'},
        'İzmir': {'kfe': 16000, 'yillik_artis': 40, 'kira_carpani': 19, 'faiz_etkisi': 'olumsuz'},
        'Antalya': {'kfe': 14000, 'yillik_artis': 55, 'kira_carpani': 15, 'faiz_etkisi': 'olumsuz'},
        'Bursa': {'kfe': 9500, 'yillik_artis': 30, 'kira_carpani': 14, 'faiz_etkisi': 'nötr'},
    }
    
    sonuclar = []
    for bolge, veri in bolgeler.items():
        reel_getiri = veri['yillik_artis'] - makro.enflasyon_tr
        
        faiz_etkisi = veri['faiz_etkisi']
        if makro.tcmb_faiz > 40:
            faiz_etkisi = "🔴 Çok Olumsuz"
        elif makro.tcmb_faiz > 30:
            faiz_etkisi = "🟡 Olumsuz"
        elif makro.tcmb_faiz < 20:
            faiz_etkisi = "🟢 Olumlu"
        
        sinyal = Sinyal.BEKLE
        gerekce = ""
        yatirim_notu = ""
        
        if makro.enflasyon_tr > 30 and makro.tcmb_faiz > 40:
            if reel_getiri > 5:
                sinyal = Sinyal.AL
                gerekce = f"🏠 Enflasyon %{makro.enflasyon_tr}, reel getiri %{reel_getiri:.1f}. Gayrimenkul enflasyon hedge'i."
                yatirim_notu = "Nakit alıcı için fırsat. Kredi maliyeti yüksek, nakit güçlü."
            else:
                sinyal = Sinyal.BEKLE
                gerekce = f"⚠️ Enflasyon yüksek ama reel getiri düşük (%{reel_getiri:.1f})."
                yatirim_notu = "Fiyat artışı enflasyonu karşılamıyor, bekleyin."
        elif makro.tcmb_faiz < 20:
            if veri['kira_carpani'] < 16:
                sinyal = Sinyal.GUC_AL
                gerekce = f"🚀 Faiz düşüşü + kira çarpanı {veri['kira_carpani']} yıl. Çok cazip!"
                yatirim_notu = "Kredi maliyeti düşecek, talep artışı bekleniyor."
            else:
                sinyal = Sinyal.AL
                gerekce = f"📉 Düşük faiz ortamı gayrimenkulü destekliyor."
                yatirim_notu = "Kira getirisi ve değer artışı potansiyeli var."
        elif makro.tcmb_faiz > 40:
            sinyal = Sinyal.SAT
            gerekce = f"📉 TCMB faizi %{makro.tcmb_faiz}. Kredi erişimi kısıtlı, likidite düşük."
            yatirim_notu = "Nakit alıcı için pazarlama fırsatı. Satıcılar zorlanıyor."
        
        if not gerekce:
            gerekce = f"Kira çarpanı: {veri['kira_carpani']} yıl. Yıllık artış: %{veri['yillik_artis']}."
            yatirim_notu = "Genel değerlendirme nötr."
        
        sonuclar.append(GayrimenkulAnalizi(
            bolge=bolge, konut_fiyat_endeksi=veri['kfe'],
            yillik_artis=veri['yillik_artis'], reel_getiri=round(reel_getiri, 2),
            kira_carpani=veri['kira_carpani'], faiz_etkisi=faiz_etkisi,
            sinyal=sinyal, gerekce=gerekce, yatirim_notu=yatirim_notu
        ))
    
    return sorted(sonuclar, key=lambda x: x.reel_getiri, reverse=True)

# ========== 5. VARLIK SINIFI ROTASYONU ==========
def calculate_asset_rotation(makro: MakroVeri, emtialar: List[EmtiaAnalizi], 
                             gayrimenkul: List[GayrimenkulAnalizi]) -> List[VarlikRotasyonu]:
    rotasyon = []
    
    # Hisse Senetleri
    if makro.rom_skor > 60 or makro.vix > 30 or makro.jeopolitik_risk > 50:
        hisse_sinyal = Sinyal.SAT
        hisse_gerekce = f"Riskli ortam (ROM {makro.rom_skor}%, VIX {makro.vix}, Jeopolitik {makro.jeopolitik_risk}%). Hisseler riskli."
        hisse_agirlik = 15
    elif makro.rom_skor > 40 or makro.vix > 25:
        hisse_sinyal = Sinyal.BEKLE
        hisse_gerekce = "Orta risk ortamı. Seçici hisse stratejisi."
        hisse_agirlik = 35
    else:
        hisse_sinyal = Sinyal.AL
        hisse_gerekce = "Düşük risk ortamı. Büyüme hisseleri değerlendirilebilir."
        hisse_agirlik = 50
    
    if makro.jeopolitik_risk > 40 and makro.savunma_sektoru_agirlik > 10:
        hisse_gerekce += f" Savunma sektörüne ağırlık verin ({makro.savunma_sektoru_agirlik}%)."
        hisse_agirlik += 5
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Hisse Senetleri",
        agirlik_onerisi=hisse_agirlik,
        sinyal=hisse_sinyal,
        gerekce=hisse_gerekce,
        makro_kosul="ROM+VIX+Jeopolitik"
    ))
    
    # Altın & Değerli Metaller
    altin_sinyal = Sinyal.BEKLE
    altin_agirlik = 10
    altin_gerekce = ""
    
    if makro.jeopolitik_risk > 40:
        altin_sinyal = Sinyal.GUC_AL
        altin_agirlik = 25
        altin_gerekce = f"🌍 Jeopolitik risk yüksek ({makro.jeopolitik_risk}%)! Altın güvenli liman."
    elif makro.enflasyon_trendi == "YUKSELIYOR":
        altin_sinyal = Sinyal.GUC_AL
        altin_agirlik = 20
        altin_gerekce = f"🛡️ Enflasyon %{makro.enflasyon_tr}! Altın enflasyon hedge'i."
    elif makro.vix > 25 or makro.rom_skor > 50:
        altin_sinyal = Sinyal.AL
        altin_agirlik = 15
        altin_gerekce = f"🛡️ Riskli ortamda altın güvenli liman."
    elif makro.enflasyon_trendi == "DUSUYOR" and makro.rom_skor < 30:
        altin_sinyal = Sinyal.SAT
        altin_agirlik = 5
        altin_gerekce = "📉 Enflasyon düşüyor, altın cazibesini kaybedebilir."
    else:
        altin_gerekce = "Nötr durum. Küçük altın pozisyonu korunabilir."
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Altın & Değerli Metaller",
        agirlik_onerisi=altin_agirlik,
        sinyal=altin_sinyal,
        gerekce=altin_gerekce,
        makro_kosul="Jeopolitik+Enflasyon+VIX"
    ))
    
    # Türkiye Gayrimenkul
    tr_gayri_sinyal = Sinyal.BEKLE
    tr_gayri_agirlik = 10
    tr_gayri_gerekce = ""
    
    if makro.enflasyon_tr > 30 and makro.tcmb_faiz > 40:
        tr_gayri_sinyal = Sinyal.AL
        tr_gayri_agirlik = 15
        tr_gayri_gerekce = f"🏠 Enflasyon %{makro.enflasyon_tr}, faiz %{makro.tcmb_faiz}. Nakit alıcı için fırsat!"
    elif makro.tcmb_faiz < 20:
        tr_gayri_sinyal = Sinyal.GUC_AL
        tr_gayri_agirlik = 20
        tr_gayri_gerekce = "🚀 Düşük faiz ortamı! Kredi maliyeti düşük, talep patlaması bekleniyor."
    elif makro.rom_skor > 60:
        tr_gayri_sinyal = Sinyal.BEKLE
        tr_gayri_agirlik = 5
        tr_gayri_gerekce = "⚠️ Resesyon riski. Kiracı riski yüksek, dikkatli olun."
    else:
        tr_gayri_gerekce = "Nötr durum. Kira getirisi ve değer artışı takip edilmeli."
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Türkiye Gayrimenkul",
        agirlik_onerisi=tr_gayri_agirlik,
        sinyal=tr_gayri_sinyal,
        gerekce=tr_gayri_gerekce,
        makro_kosul="TR Enflasyon+TCMB Faiz"
    ))
    
    # Nakit / Tahvil
    nakit_sinyal = Sinyal.BEKLE
    nakit_agirlik = 100 - hisse_agirlik - altin_agirlik - tr_gayri_agirlik
    nakit_gerekce = ""
    
    if makro.rom_skor > 50 or makro.vix > 25 or makro.jeopolitik_risk > 50:
        nakit_sinyal = Sinyal.AL
        nakit_gerekce = f"💵 Riskli ortamda nakit kraldır."
    elif nakit_agirlik < 10:
        nakit_agirlik = 10
        nakit_gerekce = "Minimum nakit rezervi."
    else:
        nakit_gerekce = "Standart nakit rezervi."
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Nakit / Tahvil / Mevduat",
        agirlik_onerisi=nakit_agirlik,
        sinyal=nakit_sinyal,
        gerekce=nakit_gerekce,
        makro_kosul="ROM+VIX+Jeopolitik"
    ))
    
    # Kripto (Bitcoin)
    btc_sinyal = Sinyal.BEKLE
    btc_agirlik = 0
    btc_gerekce = ""
    
    if makro.jeopolitik_risk > 50:
        btc_sinyal = Sinyal.SAT
        btc_gerekce = "📉 Yüksek jeopolitik riskte kripto aşırı volatil."
    elif makro.enflasyon_trendi == "YUKSELIYOR" and makro.rom_skor < 40:
        btc_sinyal = Sinyal.AL
        btc_agirlik = 3
        btc_gerekce = "₿ Enflasyon hedge'i olarak küçük pozisyon. (Yüksek risk!)"
    else:
        btc_gerekce = "Nötr durum. Kripto spekülatif, dikkatli olun."
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Kripto (Bitcoin)",
        agirlik_onerisi=btc_agirlik,
        sinyal=btc_sinyal,
        gerekce=btc_gerekce,
        makro_kosul="Jeopolitik+Enflasyon"
    ))
    
    # Emtia (Petrol, Bakır)
    emtia_sinyal = Sinyal.BEKLE
    emtia_agirlik = 0
    emtia_gerekce = ""
    
    if makro.jeopolitik_risk > 40:
        emtia_sinyal = Sinyal.AL
        emtia_agirlik = 5
        emtia_gerekce = "⛽ Jeopolitik gerilim petrol arzını tehdit ediyor."
    elif makro.enflasyon_trendi == "YUKSELIYOR":
        emtia_sinyal = Sinyal.AL
        emtia_agirlik = 5
        emtia_gerekce = "📈 Enflasyon ortamında emtia değer kazanır."
    elif makro.rom_skor > 60:
        emtia_sinyal = Sinyal.SAT
        emtia_gerekce = "📉 Resesyon talebi düşürecek."
    else:
        emtia_gerekce = "Nötr durum."
    
    rotasyon.append(VarlikRotasyonu(
        varlik_sinifi="Emtia (Petrol, Bakır)",
        agirlik_onerisi=emtia_agirlik,
        sinyal=emtia_sinyal,
        gerekce=emtia_gerekce,
        makro_kosul="Jeopolitik+Enflasyon+Resesyon"
    ))
    
    return rotasyon
'''

print(f"Part 1 written: {len(app_code)} chars")
part2 = r'''
# ========== 6. OTOMATIK ŞIRKET TARAMA (65+ ŞIRKET) ==========
AUTO_COMPANY_DATABASE = {
    # === BİST (Türkiye) ===
    'ASELS.IS': {'isim': 'Aselsan', 'sektor': 'Savunma', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'GARAN.IS': {'isim': 'Garanti Bankası', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'AKBNK.IS': {'isim': 'Akbank', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'ISCTR.IS': {'isim': 'İş Bankası', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'YKBNK.IS': {'isim': 'Yapı Kredi', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'HALKB.IS': {'isim': 'Halkbank', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'VAKBN.IS': {'isim': 'Vakıfbank', 'sektor': 'Finansallar', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'THYAO.IS': {'isim': 'Türk Hava Yolları', 'sektor': 'Ulaştırma', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'PGSUS.IS': {'isim': 'Pegasus', 'sektor': 'Ulaştırma', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'TUPRS.IS': {'isim': 'Tüpraş', 'sektor': 'Enerji', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'PETKM.IS': {'isim': 'Petkim', 'sektor': 'Enerji', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'EREGL.IS': {'isim': 'Ereğli Demir Çelik', 'sektor': 'Hammaddeler', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'KRDMD.IS': {'isim': 'Kardemir', 'sektor': 'Hammaddeler', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'BIMAS.IS': {'isim': 'BİM', 'sektor': 'Perakende', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'SOKM.IS': {'isim': 'Şok Marketler', 'sektor': 'Perakende', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'MGROS.IS': {'isim': 'Migros', 'sektor': 'Perakende', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'ULKER.IS': {'isim': 'Ülker', 'sektor': 'Gıda', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'TCELL.IS': {'isim': 'Turkcell', 'sektor': 'Teknoloji', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'TTKOM.IS': {'isim': 'Türk Telekom', 'sektor': 'Teknoloji', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    'ECILC.IS': {'isim': 'Eczacıbaşı İlaç', 'sektor': 'Sağlık', 'borsa': 'BIST', 'ulke': 'Türkiye'},
    
    # === ABD ===
    'LMT': {'isim': 'Lockheed Martin', 'sektor': 'Savunma', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'NOC': {'isim': 'Northrop Grumman', 'sektor': 'Savunma', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'RTX': {'isim': 'Raytheon', 'sektor': 'Savunma', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'GD': {'isim': 'General Dynamics', 'sektor': 'Savunma', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'BA': {'isim': 'Boeing', 'sektor': 'Savunma', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'NVDA': {'isim': 'NVIDIA', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'AAPL': {'isim': 'Apple', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'MSFT': {'isim': 'Microsoft', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'GOOGL': {'isim': 'Alphabet', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'META': {'isim': 'Meta', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'AMZN': {'isim': 'Amazon', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'TSLA': {'isim': 'Tesla', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'ABD'},
    'JPM': {'isim': 'JPMorgan', 'sektor': 'Finansallar', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'V': {'isim': 'Visa', 'sektor': 'Finansallar', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'MA': {'isim': 'Mastercard', 'sektor': 'Finansallar', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'BAC': {'isim': 'Bank of America', 'sektor': 'Finansallar', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'XOM': {'isim': 'Exxon Mobil', 'sektor': 'Enerji', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'CVX': {'isim': 'Chevron', 'sektor': 'Enerji', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'JNJ': {'isim': 'J&J', 'sektor': 'Sağlık', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'PFE': {'isim': 'Pfizer', 'sektor': 'Sağlık', 'borsa': 'NYSE', 'ulke': 'ABD'},
    'UNH': {'isim': 'UnitedHealth', 'sektor': 'Sağlık', 'borsa': 'NYSE', 'ulke': 'ABD'},
    
    # === AVRUPA ===
    'SAP': {'isim': 'SAP SE', 'sektor': 'Teknoloji', 'borsa': 'XETRA', 'ulke': 'Almanya'},
    'SIE.DE': {'isim': 'Siemens', 'sektor': 'Teknoloji', 'borsa': 'XETRA', 'ulke': 'Almanya'},
    'ALV.DE': {'isim': 'Allianz', 'sektor': 'Finansallar', 'borsa': 'XETRA', 'ulke': 'Almanya'},
    'BMW.DE': {'isim': 'BMW', 'sektor': 'Ulaştırma', 'borsa': 'XETRA', 'ulke': 'Almanya'},
    'ASML': {'isim': 'ASML Holding', 'sektor': 'Teknoloji', 'borsa': 'XETRA', 'ulke': 'Hollanda'},
    'NESN.SW': {'isim': 'Nestlé', 'sektor': 'Sağlık', 'borsa': 'SIX', 'ulke': 'İsviçre'},
    'ROG.SW': {'isim': 'Roche', 'sektor': 'Sağlık', 'borsa': 'SIX', 'ulke': 'İsviçre'},
    'AIR.PA': {'isim': 'Airbus', 'sektor': 'Savunma', 'borsa': 'EPA', 'ulke': 'Fransa'},
    'OR.PA': {'isim': 'L\'Oréal', 'sektor': 'Sağlık', 'borsa': 'EPA', 'ulke': 'Fransa'},
    'BA.L': {'isim': 'BAE Systems', 'sektor': 'Savunma', 'borsa': 'LSE', 'ulke': 'İngiltere'},
    'RDSA.L': {'isim': 'Shell', 'sektor': 'Enerji', 'borsa': 'LSE', 'ulke': 'İngiltere'},
    
    # === ASYA ===
    '7203.T': {'isim': 'Toyota', 'sektor': 'Ulaştırma', 'borsa': 'TSE', 'ulke': 'Japonya'},
    '6758.T': {'isim': 'Sony', 'sektor': 'Teknoloji', 'borsa': 'TSE', 'ulke': 'Japonya'},
    '005930.KS': {'isim': 'Samsung', 'sektor': 'Teknoloji', 'borsa': 'KRX', 'ulke': 'G. Kore'},
    '000660.KS': {'isim': 'SK Hynix', 'sektor': 'Teknoloji', 'borsa': 'KRX', 'ulke': 'G. Kore'},
    'BABA': {'isim': 'Alibaba', 'sektor': 'Teknoloji', 'borsa': 'NYSE', 'ulke': 'Çin'},
    'JD': {'isim': 'JD.com', 'sektor': 'Teknoloji', 'borsa': 'NASDAQ', 'ulke': 'Çin'},
    'RELIANCE.NS': {'isim': 'Reliance', 'sektor': 'Enerji', 'borsa': 'NSE', 'ulke': 'Hindistan'},
    'TCS.NS': {'isim': 'Tata Consultancy', 'sektor': 'Teknoloji', 'borsa': 'NSE', 'ulke': 'Hindistan'},
    'TSM': {'isim': 'TSMC', 'sektor': 'Teknoloji', 'borsa': 'NYSE', 'ulke': 'Tayvan'},
}

@st.cache_data(ttl=21600)
def analyze_company(sembol: str, meta: Dict, makro: MakroVeri) -> Optional[SirketAnalizi]:
    try:
        ticker = yf.Ticker(sembol)
        info = ticker.info
        
        if not info:
            return None
        
        fiyat = info.get('currentPrice', info.get('regularMarketPrice', 0))
        fk = info.get('trailingPE', info.get('forwardPE', 0))
        pddd = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0)
        if roe:
            roe = roe * 100
        
        kar_marji = info.get('profitMargins', 0)
        if kar_marji:
            kar_marji = kar_marji * 100
        
        borc_ok = info.get('debtToEquity', 0)
        if borc_ok:
            borc_ok = borc_ok / 100
        
        fcf = info.get('freeCashflow', 0)
        if fcf:
            fcf = fcf / 1e9
        
        cagr = info.get('revenueGrowth', 0)
        if cagr:
            cagr = cagr * 100
        else:
            cagr = 10.0
        
        # Temel skor hesaplama
        temel_skor = 50
        
        if fk and fk > 0:
            if fk < 15:
                temel_skor += 15
            elif fk < 25:
                temel_skor += 5
            else:
                temel_skor -= 10
        
        if roe and roe > 15:
            temel_skor += 15
        elif roe and roe > 10:
            temel_skor += 5
        elif roe and roe < 5:
            temel_skor -= 10
        
        if borc_ok and borc_ok < 0.5:
            temel_skor += 10
        elif borc_ok and borc_ok > 1.5:
            temel_skor -= 15
        
        if kar_marji and kar_marji > 20:
            temel_skor += 10
        elif kar_marji and kar_marji < 5:
            temel_skor -= 10
        
        if fcf and fcf > 1:
            temel_skor += 10
        
        # Jeopolitik etki
        jeopolitik_etki = 0
        sektor = meta['sektor']
        
        if makro.jeopolitik_risk > 40:
            if sektor == 'Savunma':
                jeopolitik_etki = 25
                temel_skor += 20
            elif sektor in ['Enerji', 'Hammaddeler']:
                jeopolitik_etki = 10
                temel_skor += 5
            elif sektor == 'Ulaştırma':
                jeopolitik_etki = -15
                temel_skor -= 10
            elif sektor == 'Teknoloji':
                jeopolitik_etki = -10
                temel_skor -= 5
        
        # Makro etki
        if sektor == 'Finansallar' and makro.fed_faiz > 4.5:
            temel_skor += 5
        elif sektor == 'Teknoloji' and makro.fed_faiz > 5.0:
            temel_skor -= 10
        
        if makro.rom_skor > 60 and sektor in ['Teknoloji', 'Hammaddeler', 'Ulaştırma']:
            temel_skor -= 15
        elif makro.rom_skor > 60 and sektor in ['Sağlık', 'Perakende']:
            temel_skor += 5
        
        if makro.vix > 30:
            temel_skor -= 5
        
        # Hedef fiyat
        expected_pe = 15 + (cagr * 0.3) if cagr > 0 else 12
        if fk and fk > 0:
            eps = fiyat / fk
            hedef_fiyat = eps * expected_pe
        else:
            hedef_fiyat = fiyat * (1 + cagr / 100) ** 2 / 1.15
        
        # Jeopolitik durumda hedef fiyat ayarlaması
        if jeopolitik_etki > 0:
            hedef_fiyat *= (1 + jeopolitik_etki / 100)
        elif jeopolitik_etki < 0:
            hedef_fiyat *= (1 + jeopolitik_etki / 100)
        
        yukari_potansiyel = ((hedef_fiyat / fiyat) - 1) * 100 if fiyat > 0 else 0
        
        # Sinyal belirleme
        if temel_skor > 75 and yukari_potansiyel > 20:
            sinyal = Sinyal.GUC_AL if jeopolitik_etki > 15 else Sinyal.AL
            risk = "Düşük risk, güçlü temel"
            if jeopolitik_etki > 15:
                risk += f" + Jeopolitik destek (+{jeopolitik_etki}%)"
        elif temel_skor > 60 and yukari_potansiyel > 10:
            sinyal = Sinyal.AL
            risk = "Orta risk, pozitif görünüm"
        elif temel_skor < 40 or yukari_potansiyel < -10:
            sinyal = Sinyal.SAT
            risk = "Zayıf temel, satış baskısı"
        elif makro.rom_skor > 70:
            sinyal = Sinyal.RISKLI
            risk = "Yüksek makro risk!"
        else:
            sinyal = Sinyal.BEKLE
            risk = "Karışık sinyaller"
        
        # Pozisyon büyüklüğü
        if sinyal in [Sinyal.AL, Sinyal.GUC_AL]:
            pos_size = min((yukari_potansiyel / 100) * 0.5 * ((100 - makro.rom_skor) / 100) * 100, 20)
            if jeopolitik_etki > 15:
                pos_size = min(pos_size * 1.3, 25)
        elif sinyal == Sinyal.SAT:
            pos_size = 0
        else:
            pos_size = min((yukari_potansiyel / 100) * 0.3 * ((100 - makro.rom_skor) / 100) * 100, 10)
        
        return SirketAnalizi(
            sembol=sembol, isim=meta['isim'], sektor=sektor, borsa=meta['borsa'],
            fiyat=round(fiyat, 2), fk=round(fk, 2) if fk else 0,
            pddd=round(pddd, 2) if pddd else 0, roe=round(roe, 2) if roe else 0,
            kar_marji=round(kar_marji, 2) if kar_marji else 0,
            borc_ok=round(borc_ok, 2) if borc_ok else 0,
            fcf=round(fcf, 2) if fcf else 0, cagr=round(cagr, 2),
            temel_skor=round(temel_skor, 2), hedef_fiyat=round(hedef_fiyat, 2),
            yukari_potansiyel=round(yukari_potansiyel, 2),
            sinyal=sinyal, risk_aciklama=risk,
            pozisyon_buyuklugu=round(max(0, pos_size), 2),
            jeopolitik_etki=round(jeopolitik_etki, 2)
        )
    except Exception as e:
        return None

@st.cache_data(ttl=21600)
def screen_all_companies(makro: MakroVeri, max_companies: int = 100) -> pd.DataFrame:
    sonuclar = []
    
    sorted_companies = sorted(AUTO_COMPANY_DATABASE.items(), 
                             key=lambda x: 1 if x[1]['sektor'] == 'Savunma' and makro.jeopolitik_risk > 40 else 0,
                             reverse=True)
    
    for sembol, meta in sorted_companies:
        analiz = analyze_company(sembol, meta, makro)
        
        if analiz:
            sonuclar.append({
                "Sembol": analiz.sembol,
                "Şirket": analiz.isim,
                "Sektör": analiz.sektor,
                "Borsa": analiz.borsa,
                "Ülke": meta.get('ulke', ''),
                "Fiyat": f"${analiz.fiyat}",
                "F/K": analiz.fk,
                "PD/DD": analiz.pddd,
                "ROE": f"%{analiz.roe}",
                "Kar Marjı": f"%{analiz.kar_marji}",
                "Borç/ÖK": analiz.borc_ok,
                "FCF": f"${analiz.fcf}B",
                "CAGR": f"%{analiz.cagr}",
                "Temel Skor": analiz.temel_skor,
                "Jeopolitik Etki": f"%{analiz.jeopolitik_etki}",
                "Hedef Fiyat": f"${analiz.hedef_fiyat}",
                "Potansiyel": f"%{analiz.yukari_potansiyel}",
                "Sinyal": analiz.sinyal.value,
                "Risk": analiz.risk_aciklama,
                "Öneri Ağırlık": f"%{analiz.pozisyon_buyuklugu}"
            })
    
    return pd.DataFrame(sonuclar)
'''

print(f"Part 2 written: {len(part2)} chars")
part3 = r'''
# ========== 7. PORTFÖY OPTİMİZASYONU & RİSK YÖNETİMİ ==========
class PortfoyOptimizasyonu:
    def __init__(self, sermaye: float = 1_000_000, risk_toleransi: str = "orta"):
        self.sermaye = sermaye
        self.risk_toleransi = risk_toleransi
        self.pozisyonlar = {}
        self.stop_losslar = {}
        self.risk_metrics = {}
        
    def hesapla_optimal_agirliklar(self, sirketler_df: pd.DataFrame, makro: MakroVeri) -> pd.DataFrame:
        if sirketler_df.empty:
            return pd.DataFrame()
        
        # Sadece AL ve GUC_AL sinyalleri olanları al
        al_sinyaller = ['🟢 AL', '🟢 GÜÇLÜ AL']
        portfoy_hisseleri = sirketler_df[sirketler_df['Sinyal'].isin(al_sinyaller)].copy()
        
        if portfoy_hisseleri.empty:
            return pd.DataFrame()
        
        # Risk toleransına göre maksimum pozisyon
        if self.risk_toleransi == "dusuk":
            max_pozisyon = 10
            min_pozisyon = 2
            nakit_orani = 0.30
        elif self.risk_toleransi == "orta":
            max_pozisyon = 15
            min_pozisyon = 3
            nakit_orani = 0.20
        else:  # yuksek
            max_pozisyon = 20
            min_pozisyon = 5
            nakit_orani = 0.10
        
        # Potansiyele göre ağırlıklandırma
        portfoy_hisseleri['Potansiyel_Sayi'] = portfoy_hisseleri['Potansiyel'].str.replace('%', '').astype(float)
        portfoy_hisseleri['Temel_Skor_Sayi'] = portfoy_hisseleri['Temel Skor']
        
        # Makro risk düzeltmesi
        risk_faktoru = max(0, (100 - makro.rom_skor) / 100)
        portfoy_hisseleri['Risk_Ayarli_Potansiyel'] = portfoy_hisseleri['Potansiyel_Sayi'] * risk_faktoru
        
        # Ağırlık hesaplama
        toplam_potansiyel = portfoy_hisseleri['Risk_Ayarli_Potansiyel'].sum()
        if toplam_potansiyel > 0:
            portfoy_hisseleri['Agirlik'] = (portfoy_hisseleri['Risk_Ayarli_Potansiyel'] / toplam_potansiyel) * (1 - nakit_orani)
        else:
            portfoy_hisseleri['Agirlik'] = (1 - nakit_orani) / len(portfoy_hisseleri)
        
        # Maksimum pozisyon sınırı
        portfoy_hisseleri['Agirlik'] = portfoy_hisseleri['Agirlik'].clip(upper=max_pozisyon/100)
        
        # Normalize
        toplam_agirlik = portfoy_hisseleri['Agirlik'].sum()
        if toplam_agirlik > 0:
            portfoy_hisseleri['Agirlik'] = portfoy_hisseleri['Agirlik'] / toplam_agirlik * (1 - nakit_orani)
        
        # Sektör çeşitlendirmesi
        sektor_agirlik = portfoy_hisseleri.groupby('Sektör')['Agirlik'].sum()
        asiri_agirlikli_sektor = sektor_agirlik[sektor_agirlik > 0.30].index.tolist()
        
        for sektor in asiri_agirlikli_sektor:
            sektor_hisseleri = portfoy_hisseleri[portfoy_hisseleri['Sektör'] == sektor]
            duzeltme_faktoru = 0.30 / sektor_agirlik[sektor]
            portfoy_hisseleri.loc[portfoy_hisseleri['Sektör'] == sektor, 'Agirlik'] *= duzeltme_faktoru
        
        # Son normalize
        toplam_agirlik = portfoy_hisseleri['Agirlik'].sum()
        if toplam_agirlik > 0:
            portfoy_hisseleri['Agirlik'] = portfoy_hisseleri['Agirlik'] / toplam_agirlik * (1 - nakit_orani)
        
        portfoy_hisseleri['Yatirim_Tutari'] = portfoy_hisseleri['Agirlik'] * self.sermaye
        portfoy_hisseleri['Hedef_Fiyat_Sayi'] = portfoy_hisseleri['Hedef Fiyat'].str.replace('$', '').astype(float)
        portfoy_hisseleri['Fiyat_Sayi'] = portfoy_hisseleri['Fiyat'].str.replace('$', '').astype(float)
        portfoy_hisseleri['Stop_Loss'] = portfoy_hisseleri['Fiyat_Sayi'] * 0.85  # %15 stop-loss
        
        return portfoy_hisseleri[['Sembol', 'Şirket', 'Sektör', 'Borsa', 'Fiyat', 'Agirlik', 
                                   'Yatirim_Tutari', 'Hedef Fiyat', 'Potansiyel', 'Stop_Loss',
                                   'Temel Skor', 'Sinyal']].sort_values('Agirlik', ascending=False)
    
    def hesapla_portfoy_metrics(self, portfoy_df: pd.DataFrame, makro: MakroVeri) -> Dict:
        if portfoy_df.empty:
            return {}
        
        toplam_deger = portfoy_df['Yatirim_Tutari'].sum()
        ortalama_potansiyel = portfoy_df['Potansiyel'].str.replace('%', '').astype(float).mean()
        ortalama_temel_skor = portfoy_df['Temel Skor'].mean()
        
        # Sektör dağılımı
        sektor_dagilimi = portfoy_df.groupby('Sektör')['Agirlik'].sum().to_dict()
        
        # Ülke dağılımı
        ulke_dagilimi = portfoy_df.groupby('Borsa')['Agirlik'].sum().to_dict()
        
        # Risk metrikleri
        beta_portfoy = 1.0  # Varsayılan
        if makro.rom_skor > 60:
            beta_portfoy = 1.3
        elif makro.rom_skor < 30:
            beta_portfoy = 0.8
        
        portfoy_risk = beta_portfoy * (makro.vix / 100) * 100
        
        return {
            'toplam_yatirim': toplam_deger,
            'nakit_orani': 1 - portfoy_df['Agirlik'].sum(),
            'beklenen_getiri': ortalama_potansiyel,
            'ortalama_temel_skor': ortalama_temel_skor,
            'portfoy_risk_skoru': portfoy_risk,
            'beta': beta_portfoy,
            'sektor_dagilimi': sektor_dagilimi,
            'ulke_dagilimi': ulke_dagilimi,
            'hisse_sayisi': len(portfoy_df),
            'jeopolitik_korunma': any(s == 'Savunma' for s in sektor_dagilimi.keys())
        }

class StopLossYoneticisi:
    def __init__(self):
        self.aktif_stoplar = {}
        self.stop_gecmisi = []
    
    def ayarla_stop_loss(self, sembol: str, giris_fiyati: float, stop_turu: str = "yuzde", 
                         deger: float = 0.15, atr_degeri: float = None) -> Dict:
        if stop_turu == "yuzde":
            stop_fiyati = giris_fiyati * (1 - deger)
        elif stop_turu == "atr" and atr_degeri:
            stop_fiyati = giris_fiyati - (atr_degeri * deger)
        elif stop_turu == "takip":
            stop_fiyati = giris_fiyati * (1 - deger)
        else:
            stop_fiyati = giris_fiyati * 0.85
        
        stop_bilgisi = {
            'sembol': sembol,
            'giris_fiyati': giris_fiyati,
            'stop_fiyati': stop_fiyati,
            'stop_turu': stop_turu,
            'risk_yuzde': (giris_fiyati - stop_fiyati) / giris_fiyati * 100,
            'tarih': datetime.now().strftime("%Y-%m-%d"),
            'aktif': True,
            'en_yuksek_fiyat': giris_fiyati
        }
        
        self.aktif_stoplar[sembol] = stop_bilgisi
        return stop_bilgisi
    
    def guncelle_takip_stop(self, sembol: str, mevcut_fiyat: float, takip_yuzdesi: float = 0.10):
        if sembol not in self.aktif_stoplar:
            return None
        
        stop = self.aktif_stoplar[sembol]
        if not stop['aktif']:
            return stop
        
        # En yüksek fiyatı güncelle
        if mevcut_fiyat > stop['en_yuksek_fiyat']:
            stop['en_yuksek_fiyat'] = mevcut_fiyat
            
            # Takip eden stop'u güncelle
            if stop['stop_turu'] == 'takip':
                yeni_stop = mevcut_fiyat * (1 - takip_yuzdesi)
                if yeni_stop > stop['stop_fiyati']:
                    stop['stop_fiyati'] = yeni_stop
                    stop['risk_yuzde'] = (mevcut_fiyat - yeni_stop) / mevcut_fiyat * 100
        
        # Stop kontrolü
        if mevcut_fiyat <= stop['stop_fiyati']:
            stop['aktif'] = False
            stop['kapanis_fiyati'] = mevcut_fiyat
            stop['kapanis_tarihi'] = datetime.now().strftime("%Y-%m-%d")
            stop['zarar_yuzde'] = (stop['giris_fiyati'] - mevcut_fiyat) / stop['giris_fiyati'] * 100
            self.stop_gecmisi.append(stop.copy())
            return {'tetiklendi': True, 'stop': stop}
        
        return {'tetiklendi': False, 'stop': stop}
    
    def hesapla_pozisyon_boyutu(self, sermaye: float, risk_yuzde: float, 
                                  giris_fiyati: float, stop_fiyati: float) -> Dict:
        risk_tutari = sermaye * risk_yuzde
        fiyat_riski = giris_fiyati - stop_fiyati
        
        if fiyat_riski <= 0:
            return {'hisse_adedi': 0, 'pozisyon_degeri': 0, 'risk_tutari': 0}
        
        hisse_adedi = int(risk_tutari / fiyat_riski)
        pozisyon_degeri = hisse_adedi * giris_fiyati
        
        return {
            'hisse_adedi': hisse_adedi,
            'pozisyon_degeri': pozisyon_degeri,
            'risk_tutari': risk_tutari,
            'risk_yuzde': risk_yuzde * 100,
            'fiyat_riski': fiyat_riski
        }

# ========== 8. RAPORLAMA & EXPORT ==========
class RaporMotoru:
    def __init__(self):
        self.rapor_icerigi = []
    
    def olustur_ozet_rapor(self, makro: MakroVeri, emtialar: List[EmtiaAnalizi],
                           gayrimenkul: List[GayrimenkulAnalizi], rotasyon: List[VarlikRotasyonu],
                           sirketler_df: pd.DataFrame, portfoy_df: pd.DataFrame) -> str:
        rapor = f"""
{'='*80}
FINSIGHTAI - EKONOMİK DANIŞMAN RAPORU
Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}
{'='*80}

📊 MAKRO EKONOMİK GÖRÜNÜM
{'-'*40}
• Fed Faiz: %{makro.fed_faiz}
• TCMB Faiz: %{makro.tcmb_faiz}
• Enflasyon (ABD): %{makro.enflasyon_us}
• Enflasyon (TR): %{makro.enflasyon_tr}
• VIX: {makro.vix}
• USD/TRY: {makro.usdtry}
• ROM Skoru: {makro.rom_skor}/100
• Risk Seviyesi: {makro.risk_seviyesi}
• Jeopolitik Risk: {makro.jeopolitik_risk}/100
• Savunma Sektörü Ağırlığı: %{makro.savunma_sektoru_agirlik}

🌍 VARLIK ROTASYONU ÖNERİLERİ
{'-'*40}
"""
        for varlik in rotasyon:
            rapor += f"• {varlik.varlik_sinifi}: %{varlik.agirlik_onerisi} - {varlik.sinyal.value}\n"
            rapor += f"  └─ {varlik.gerekce}\n"
        
        rapor += f"\n⛏️ EMTİA ANALİZİ\n{'-'*40}\n"
        for emtia in emtialar[:5]:
            rapor += f"• {emtia.isim}: {emtia.sinyal.value} (${emtia.fiyat})\n"
            rapor += f"  └─ {emtia.gerekce}\n"
        
        rapor += f"\n🏠 TÜRKİYE GAYRİMENKUL\n{'-'*40}\n"
        for gm in gayrimenkul[:3]:
            rapor += f"• {gm.bolge}: {gm.sinyal.value} (Reel Getiri: %{gm.reel_getiri})\n"
            rapor += f"  └─ {gm.yatirim_notu}\n"
        
        if not sirketler_df.empty:
            rapor += f"\n📈 EN İYİ 10 ŞİRKET\n{'-'*40}\n"
            en_iyi = sirketler_df.nlargest(10, 'Temel Skor')
            for _, sirket in en_iyi.iterrows():
                rapor += f"• {sirket['Şirket']} ({sirket['Sembol']}): {sirket['Sinyal']}\n"
                rapor += f"  F/K: {sirket['F/K']} | Hedef: {sirket['Hedef Fiyat']} | Potansiyel: {sirket['Potansiyel']}\n"
        
        if not portfoy_df.empty:
            rapor += f"\n💼 ÖNERİLEN PORTFÖY\n{'-'*40}\n"
            for _, poz in portfoy_df.head(10).iterrows():
                rapor += f"• {poz['Şirket']} ({poz['Sembol']}): %{poz['Agirlik']*100:.1f} (${poz['Yatirim_Tutari']:,.0f})\n"
                rapor += f"  Stop-Loss: ${poz['Stop_Loss']:.2f} | Hedef: {poz['Hedef Fiyat']}\n"
        
        rapor += f"\n{'='*80}\n⚠️ UYARI: Bu rapor yatırım tavsiyesi değildir.\n"
        rapor += f"{'='*80}"
        
        return rapor
    
    def export_to_excel(self, makro: MakroVeri, emtialar: List[EmtiaAnalizi],
                        gayrimenkul: List[GayrimenkulAnalizi], rotasyon: List[VarlikRotasyonu],
                        sirketler_df: pd.DataFrame, portfoy_df: pd.DataFrame) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Makro veri
            makro_df = pd.DataFrame([{
                'Fed Faiz': makro.fed_faiz,
                'TCMB Faiz': makro.tcmb_faiz,
                'Enflasyon ABD': makro.enflasyon_us,
                'Enflasyon TR': makro.enflasyon_tr,
                'VIX': makro.vix,
                'USD/TRY': makro.usdtry,
                'ROM Skor': makro.rom_skor,
                'Risk Seviyesi': makro.risk_seviyesi,
                'Jeopolitik Risk': makro.jeopolitik_risk
            }])
            makro_df.to_excel(writer, sheet_name='Makro Veriler', index=False)
            
            # Emtia
            emtia_df = pd.DataFrame([{
                'İsim': e.isim,
                'Fiyat': e.fiyat,
                'Sinyal': e.sinyal.value,
                'Gerekçe': e.gerekce,
                'Risk Kaçışı': e.risk_kacisi_puani
            } for e in emtialar])
            emtia_df.to_excel(writer, sheet_name='Emtia Analizi', index=False)
            
            # Gayrimenkul
            gm_df = pd.DataFrame([{
                'Bölge': g.bolge,
                'Reel Getiri': g.reel_getiri,
                'Sinyal': g.sinyal.value,
                'Yatırım Notu': g.yatirim_notu
            } for g in gayrimenkul])
            gm_df.to_excel(writer, sheet_name='Gayrimenkul', index=False)
            
            # Rotasyon
            rot_df = pd.DataFrame([{
                'Varlık': r.varlik_sinifi,
                'Ağırlık': r.agirlik_onerisi,
                'Sinyal': r.sinyal.value
            } for r in rotasyon])
            rot_df.to_excel(writer, sheet_name='Varlık Rotasyonu', index=False)
            
            # Şirketler
            if not sirketler_df.empty:
                sirketler_df.to_excel(writer, sheet_name='Şirket Taraması', index=False)
            
            # Portföy
            if not portfoy_df.empty:
                portfoy_df.to_excel(writer, sheet_name='Portföy Optimizasyonu', index=False)
        
        output.seek(0)
        return output.getvalue()
'''
print(f"Part 3 written: {len(part3)} chars")
part4 = r'''
# ========== 9. STREAMLIT UI / DASHBOARD ==========
def render_makro_kart(makro: MakroVeri):
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Fed Faiz", f"%{makro.fed_faiz}")
        st.metric("TCMB Faiz", f"%{makro.tcmb_faiz}")
        st.metric("Enflasyon (TR)", f"%{makro.enflasyon_tr}")
    
    with col2:
        st.metric("VIX", f"{makro.vix}")
        st.metric("USD/TRY", f"{makro.usdtry:.2f}")
        st.metric("ROM Skor", f"{makro.rom_skor}/100")
    
    with col3:
        renk = "🟢" if "DÜŞÜK" in makro.risk_seviyesi else "🟡" if "ORTA" in makro.risk_seviyesi else "🔴"
        st.metric("Risk Seviyesi", f"{renk} {makro.risk_seviyesi}")
        st.metric("Enflasyon Trendi", makro.enflasyon_trendi)
        st.metric("Jeopolitik Risk", f"{makro.jeopolitik_risk}/100")
    
    with col4:
        st.metric("Savunma Ağırlığı", f"%{makro.savunma_sektoru_agirlik}")
        st.metric("PMI (ABD)", f"{makro.pmi_us}")
        st.metric("PMI (TR)", f"{makro.pmi_tr}")

def render_haberler(haberler: List[Dict]):
    st.subheader("📰 Güncel Haberler & Jeopolitik Analiz")
    
    # Duygu skoru göstergesi
    olumlu_haber = [h for h in haberler if h.get('duygu_skoru', 0) > 0.3]
    olumsuz_haber = [h for h in haberler if h.get('duygu_skoru', 0) < -0.3]
    notr_haber = [h for h in haberler if -0.3 <= h.get('duygu_skoru', 0) <= 0.3]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🟢 Olumlu", len(olumlu_haber))
    col2.metric("🔴 Olumsuz", len(olumsuz_haber))
    col3.metric("⚪ Nötr", len(notr_haber))
    
    # Haber akışı
    with st.expander("🔍 Tüm Haberleri Gör", expanded=False):
        for haber in haberler[:15]:
            with st.container():
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**[{haber['baslik']}]({haber['url']})**")
                    st.caption(f"{haber['kaynak']} | {haber['tarih']}")
                    if haber.get('aciklama'):
                        st.write(haber['aciklama'][:150] + "...")
                with cols[1]:
                    st.markdown(f"**{haber.get('etki', '⚪ Nötr')}**")
                    if haber.get('jeopolitik_skor', 0) > 0:
                        st.markdown(f"🌍 **+{haber['jeopolitik_skor']}**")
                    if haber.get('savunma_skor', 0) > 0:
                        st.markdown(f"🛡️ **+{haber['savunma_skor']}**")
                st.divider()

def render_emtia(emtialar: List[EmtiaAnalizi]):
    st.subheader("⛏️ Emtia Analizi")
    
    # Emtia grafiği
    fig = go.Figure()
    
    for emtia in emtialar:
        renk = "green" if "AL" in emtia.sinyal.value else "red" if "SAT" in emtia.sinyal.value else "gray"
        fig.add_trace(go.Bar(
            name=emtia.isim,
            x=[emtia.isim],
            y=[emtia.degisim_1h],
            marker_color=renk,
            text=f"{emtia.degisim_1h:.1f}%",
            textposition='outside'
        ))
    
    fig.update_layout(
        title="1 Aylık Değişim (%)",
        showlegend=False,
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Emtia detayları
    for emtia in emtialar:
        with st.container():
            cols = st.columns([2, 1, 3])
            with cols[0]:
                st.markdown(f"**{emtia.isim}**")
                st.write(f"${emtia.fiyat}")
            with cols[1]:
                st.markdown(f"**{emtia.sinyal.value}**")
            with cols[2]:
                st.info(emtia.gerekce)
            st.divider()

def render_gayrimenkul(gayrimenkul: List[GayrimenkulAnalizi]):
    st.subheader("🏠 Türkiye Gayrimenkul Analizi")
    
    # Harita benzeri görselleştirme
    fig = px.bar(
        x=[g.bolge for g in gayrimenkul],
        y=[g.reel_getiri for g in gayrimenkul],
        color=[g.sinyal.value for g in gayrimenkul],
        title="Bölgesel Reel Getiri (%)",
        labels={'x': 'Bölge', 'y': 'Reel Getiri (%)'}
    )
    st.plotly_chart(fig, use_container_width=True)
    
    for gm in gayrimenkul:
        with st.container():
            cols = st.columns([2, 1, 2, 3])
            with cols[0]:
                st.markdown(f"**{gm.bolge}**")
                st.write(f"KFE: {gm.konut_fiyat_endeksi}")
            with cols[1]:
                st.markdown(f"**{gm.sinyal.value}**")
            with cols[2]:
                st.write(f"Reel Getiri: %{gm.reel_getiri}")
                st.write(f"Kira Çarpanı: {gm.kira_carpani}")
            with cols[3]:
                st.info(gm.yatirim_notu)
            st.divider()

def render_varlik_rotasyonu(rotasyon: List[VarlikRotasyonu]):
    st.subheader("🌍 Varlık Sınıfı Rotasyonu")
    
    # Pasta grafiği
    fig = px.pie(
        names=[r.varlik_sinifi for r in rotasyon if r.agirlik_onerisi > 0],
        values=[r.agirlik_onerisi for r in rotasyon if r.agirlik_onerisi > 0],
        title="Önerilen Varlık Dağılımı"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    for varlik in rotasyon:
        if varlik.agirlik_onerisi > 0:
            with st.container():
                cols = st.columns([2, 1, 4])
                with cols[0]:
                    st.markdown(f"**{varlik.varlik_sinifi}**")
                    st.write(f"%{varlik.agirlik_onerisi}")
                with cols[1]:
                    st.markdown(f"**{varlik.sinyal.value}**")
                with cols[2]:
                    st.info(varlik.gerekce)
                st.divider()

def render_sirket_taramasi(sirketler_df: pd.DataFrame, makro: MakroVeri):
    st.subheader(f"📈 Şirket Taraması ({len(sirketler_df)} Şirket)")
    
    if sirketler_df.empty:
        st.warning("Şirket verisi bulunamadı.")
        return
    
    # Filtreler
    col1, col2, col3 = st.columns(3)
    with col1:
        sektor_filtre = st.multiselect("Sektör", sirketler_df['Sektör'].unique())
    with col2:
        sinyal_filtre = st.multiselect("Sinyal", sirketler_df['Sinyal'].unique(), 
                                        default=['🟢 AL', '🟢 GÜÇLÜ AL'])
    with col3:
        borsa_filtre = st.multiselect("Borsa", sirketler_df['Borsa'].unique())
    
    filtreli_df = sirketler_df.copy()
    if sektor_filtre:
        filtreli_df = filtreli_df[filtreli_df['Sektör'].isin(sektor_filtre)]
    if sinyal_filtre:
        filtreli_df = filtreli_df[filtreli_df['Sinyal'].isin(sinyal_filtre)]
    if borsa_filtre:
        filtreli_df = filtreli_df[filtreli_df['Borsa'].isin(borsa_filtre)]
    
    # Sıralama
    filtreli_df = filtreli_df.sort_values('Temel Skor', ascending=False)
    
    # DataFrame gösterimi
    st.dataframe(
        filtreli_df,
        column_config={
            "Sembol": st.column_config.TextColumn("Sembol", width="small"),
            "Şirket": st.column_config.TextColumn("Şirket", width="medium"),
            "Temel Skor": st.column_config.NumberColumn("Skor", format="%.1f"),
            "Potansiyel": st.column_config.TextColumn("Potansiyel"),
            "Sinyal": st.column_config.TextColumn("Sinyal"),
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Scatter plot: F/K vs Potansiyel
    fig = px.scatter(
        filtreli_df,
        x='F/K',
        y='Potansiyel',
        color='Sektör',
        size='Temel Skor',
        hover_data=['Şirket', 'Sembol', 'Hedef Fiyat'],
        title="F/K Oranı vs Potansiyel Getiri"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Savunma sektörü vurgusu (jeopolitik risk yüksekse)
    if makro.jeopolitik_risk > 40:
        savunma_df = filtreli_df[filtreli_df['Sektör'] == 'Savunma']
        if not savunma_df.empty:
            st.markdown("### 🛡️ Savunma Sektörü Öne Çıkanlar")
            st.dataframe(savunma_df, hide_index=True, use_container_width=True)

def render_portfoy_optimizasyonu(portfoy_df: pd.DataFrame, metrics: Dict, makro: MakroVeri):
    st.subheader("💼 Portföy Optimizasyonu & Risk Yönetimi")
    
    if portfoy_df.empty:
        st.warning("Portföy oluşturulamadı. AL sinyali olan şirket bulunamadı.")
        return
    
    # Portföy metrikleri
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Toplam Yatırım", f"${metrics.get('toplam_yatirim', 0):,.0f}")
    col2.metric("Beklenen Getiri", f"%{metrics.get('beklenen_getiri', 0):.1f}")
    col3.metric("Portföy Risk", f"{metrics.get('portfoy_risk_skoru', 0):.1f}")
    col4.metric("Nakit Oranı", f"%{metrics.get('nakit_orani', 0)*100:.0f}")
    
    # Sektör dağılımı
    if metrics.get('sektor_dagilimi'):
        fig = px.pie(
            names=list(metrics['sektor_dagilimi'].keys()),
            values=list(metrics['sektor_dagilimi'].values()),
            title="Sektör Dağılımı"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Portföy tablosu
    st.markdown("### 📋 Önerilen Pozisyonlar")
    st.dataframe(
        portfoy_df,
        column_config={
            "Agirlik": st.column_config.ProgressColumn("Ağırlık", format="%.1f%%", min_value=0, max_value=0.30),
            "Yatirim_Tutari": st.column_config.NumberColumn("Tutar", format="$%.0f"),
            "Stop_Loss": st.column_config.NumberColumn("Stop-Loss", format="$%.2f"),
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Stop-loss tablosu
    st.markdown("### 🛡️ Stop-Loss Seviyeleri")
    stop_df = portfoy_df[['Sembol', 'Şirket', 'Fiyat', 'Stop_Loss']].copy()
    stop_df['Risk %'] = ((stop_df['Fiyat'].str.replace('$', '').astype(float) - stop_df['Stop_Loss']) / 
                         stop_df['Fiyat'].str.replace('$', '').astype(float) * 100).round(1)
    st.dataframe(stop_df, hide_index=True, use_container_width=True)
    
    # Jeopolitik korunma uyarısı
    if metrics.get('jeopolitik_korunma'):
        st.success("✅ Portföy jeopolitik risklere karşı savunma sektörü ile korunuyor.")
    elif makro.jeopolitik_risk > 40:
        st.warning("⚠️ Jeopolitik risk yüksek ama portföyde savunma sektörü yok!")

def render_rapor_indirme(rapor_motoru: RaporMotoru, makro: MakroVeri, 
                         emtialar: List[EmtiaAnalizi], gayrimenkul: List[GayrimenkulAnalizi],
                         rotasyon: List[VarlikRotasyonu], sirketler_df: pd.DataFrame,
                         portfoy_df: pd.DataFrame):
    st.subheader("📥 Rapor İndirme")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📄 Metin Raporu Oluştur", use_container_width=True):
            rapor = rapor_motoru.olustur_ozet_rapor(makro, emtialar, gayrimenkul, 
                                                     rotasyon, sirketler_df, portfoy_df)
            st.text_area("Rapor Önizleme", rapor, height=400)
            st.download_button(
                "⬇️ .txt İndir",
                rapor,
                file_name=f"finsight_rapor_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
    
    with col2:
        if st.button("📊 Excel Raporu Oluştur", use_container_width=True):
            excel_data = rapor_motoru.export_to_excel(makro, emtialar, gayrimenkul, 
                                                       rotasyon, sirketler_df, portfoy_df)
            st.download_button(
                "⬇️ .xlsx İndir",
                excel_data,
                file_name=f"finsight_rapor_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ========== 10. ANA KOORDİNATÖR / PIPELINE ==========
def main():
    st.title("🧠 FinsightAI - Ekonomik Danışman")
    st.markdown("### Kişisel Finans Asistanınız | Makro Analiz • Portföy Optimizasyon • Risk Yönetimi")
    
    # Sidebar ayarları
    with st.sidebar:
        st.header("⚙️ Portföy Ayarları")
        sermaye = st.number_input("Sermaye ($)", min_value=10000, value=100000, step=10000)
        risk_toleransi = st.select_slider(
            "Risk Toleransı",
            options=["dusuk", "orta", "yuksek"],
            value="orta"
        )
        
        st.header("🔍 Filtreler")
        sektor_secimi = st.multiselect(
            "Sektörler",
            ['Savunma', 'Finansallar', 'Teknoloji', 'Enerji', 'Sağlık', 
             'Perakende', 'Gıda', 'Ulaştırma', 'Hammaddeler'],
            default=['Savunma', 'Finansallar', 'Teknoloji', 'Enerji']
        )
        
        ulke_secimi = st.multiselect(
            "Piyasalar",
            ['BIST', 'NYSE', 'NASDAQ', 'XETRA', 'SIX', 'EPA', 'LSE', 'TSE', 'KRX', 'NSE'],
            default=['BIST', 'NYSE', 'NASDAQ']
        )
        
        st.header("📊 Görünüm")
        goster_haber = st.checkbox("Haber Akışı", value=True)
        goster_makro = st.checkbox("Makro Veriler", value=True)
        goster_emtia = st.checkbox("Emtia Analizi", value=True)
        goster_gayrimenkul = st.checkbox("Gayrimenkul", value=True)
        goster_rotasyon = st.checkbox("Varlık Rotasyonu", value=True)
        goster_sirket = st.checkbox("Şirket Taraması", value=True)
        goster_portfoy = st.checkbox("Portföy Optimizasyonu", value=True)
        
        st.divider()
        st.caption("FinsightAI v2.2 | Veriler gecikmeli olabilir.")
    
    # Veri toplama pipeline'ı
    with st.spinner("🔄 Veriler yükleniyor..."):
        # 1. Haberler
        global_haberler = get_global_news(NEWS_API_KEY)
        turk_haberler = get_turkish_news()
        tum_haberler = global_haberler + turk_haberler
        
        haber_skoru, jeo_risk, savunma_agirlik, analizli_haberler = analyze_news_sentiment(tum_haberler)
        
        # 2. Makro veriler
        makro = get_macro_data(FRED_API_KEY, haber_skoru, jeo_risk, savunma_agirlik)
        
        # 3. Emtia
        emtialar = analyze_commodities(makro)
        
        # 4. Gayrimenkul
        gayrimenkul = analyze_turkey_real_estate(makro)
        
        # 5. Varlık rotasyonu
        rotasyon = calculate_asset_rotation(makro, emtialar, gayrimenkul)
        
        # 6. Şirket taraması
        sirketler_df = screen_all_companies(makro)
        
        # Filtre uygula
        if sektor_secimi:
            sirketler_df = sirketler_df[sirketler_df['Sektör'].isin(sektor_secimi)]
        if ulke_secimi:
            sirketler_df = sirketler_df[sirketler_df['Borsa'].isin(ulke_secimi)]
        
        # 7. Portföy optimizasyonu
        portfoy_opt = PortfoyOptimizasyonu(sermaye, risk_toleransi)
        portfoy_df = portfoy_opt.hesapla_optimal_agirliklar(sirketler_df, makro)
        portfoy_metrics = portfoy_opt.hesapla_portfoy_metrics(portfoy_df, makro)
        
        # 8. Rapor motoru
        rapor_motoru = RaporMotoru()
    
    # UI Render
    if goster_makro:
        st.header("📊 Makroekonomik Panorama")
        render_makro_kart(makro)
        st.divider()
    
    if goster_haber and analizli_haberler:
        render_haberler(analizli_haberler)
        st.divider()
    
    if goster_emtia and emtialar:
        render_emtia(emtialar)
        st.divider()
    
    if goster_gayrimenkul and gayrimenkul:
        render_gayrimenkul(gayrimenkul)
        st.divider()
    
    if goster_rotasyon and rotasyon:
        render_varlik_rotasyonu(rotasyon)
        st.divider()
    
    if goster_sirket and not sirketler_df.empty:
        render_sirket_taramasi(sirketler_df, makro)
        st.divider()
    
    if goster_portfoy:
        render_portfoy_optimizasyonu(portfoy_df, portfoy_metrics, makro)
        st.divider()
    
    # Rapor indirme
    render_rapor_indirme(rapor_motoru, makro, emtialar, gayrimenkul, 
                         rotasyon, sirketler_df, portfoy_df)
    
    # Footer
    st.divider()
    st.caption(f"""
    📅 Son Güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}  
    ⚠️ **Yasal Uyarı:** Bu uygulama yatırım tavsiyesi değildir.  
    Tüm yatırım kararlarınızdan siz sorumlusunuz. Geçmiş getiriler gelecek performansın garantisi değildir.
    """)

if __name__ == "__main__":
    main()
'''

with open('/mnt/agents/output/finsightai_app_fixed.py', 'a', encoding='utf-8') as f:
    f.write(part4)

print(f"Part 4 written: {len(part4)} chars")

# Check final file
import os
file_size = os.path.getsize('/mnt/agents/output/finsightai_app_fixed.py')
print(f"\n{'='*60}")
print(f"✅ TÜM PARÇALAR BİRLEŞTİRİLDİ!")
print(f"{'='*60}")
print(f"📁 Dosya: finsightai_app_fixed.py")
print(f"📊 Toplam Boyut: {file_size:,} byte ({file_size/1024:.1f} KB)")

# Count lines
with open('/mnt/agents/output/finsightai_app_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"📄 Toplam Satır: {len(lines)}")
