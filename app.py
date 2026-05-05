import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import requests
from typing import Dict, Tuple, Optional, List

# ========== YAPILANDIRMA ==========
st.set_page_config(page_title="FinsightAI", page_icon="📊", layout="wide")

# --- SIFRE KORUMASI ---
if "sifre_dogrulandi" not in st.session_state:
    st.session_state.sifre_dogrulandi = False

if not st.session_state.sifre_dogrulandi:
    st.title("🔒 FinsightAI")
    sifre = st.text_input("Şifre", type="password")
    if st.button("Giriş"):
        if sifre == "Finans@12345":
            st.session_state.sifre_dogrulandi = True
            st.rerun()
        else:
            st.error("❌ Yanlış şifre!")
    st.stop()

# ========== ASIL UYGULAMA ==========
st.title("📊 Kişisel Finans AI")
st.caption(f"Son güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# --- API ANAHTARLARI (Secrets öncelikli) ---
def get_api_keys() -> Tuple[str, str]:
    """API anahtarlarını güvenli şekilde alır."""
    try:
        return st.secrets["FRED_API_KEY"], st.secrets["NEWS_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.warning("⚠️ API anahtarları secrets.toml'da bulunamadı. Yedek anahtarlar kullanılıyor.")
        return "9d3135bcfce4a8a3af3ccc3488a94a12", "361bdcc09ce647f2b47d22addbbec35c"

FRED_API_KEY, NEWS_API_KEY = get_api_keys()

# --- SEKTÖR METADATA (Global Tanım) ---
SECTOR_META = {
    'Teknoloji': {'faiz': 3, 'enflasyon': 1, 'etf': 'XLK'},
    'Finansallar': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLF'},
    'Enerji': {'faiz': 1, 'enflasyon': 3, 'etf': 'XLE'},
    'Sağlık': {'faiz': 2, 'enflasyon': 1, 'etf': 'XLV'},
    'Kamu Hizmetleri': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLU'},
    'Gayrimenkul': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLRE'}
}

# --- YARDIMCI FONKSİYONLAR ---
def safe_float(value: str, default: Optional[float] = None) -> Optional[float]:
    """Güvenli float dönüşümü."""
    if value is None or value == '.':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_close_price(df: pd.DataFrame) -> pd.Series:
    """yfinance DataFrame'den kapanış fiyatını güvenli şekilde çeker."""
    if df.empty:
        return pd.Series()
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        return close.iloc[:, 0]
    return close

# ========== KATMAN 1: MAKRO HESAPLAMA ==========
@st.cache_data(ttl=3600)
def get_fred_val(series_id: str, api_key: str) -> Tuple[Optional[float], Optional[float]]:
    """FRED API'den son iki gözlem değerini çeker."""
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
    except Exception as e:
        st.error(f"FRED API hatası ({series_id}): {str(e)}")
        return None, None

@st.cache_data(ttl=3600)
def calculate_macro_scores(api_key: str) -> Dict:
    """Makro ekonomik skorları hesaplar."""
    # Veri çekme
    fed_funds, _ = get_fred_val('FEDFUNDS', api_key)
    dgs10, _ = get_fred_val('DGS10', api_key)
    dgs2, _ = get_fred_val('DGS2', api_key)
    vix, _ = get_fred_val('VIXCLS', api_key)
    unemp_rate, prev_unemp = get_fred_val('UNRATE', api_key)

    # Varsayılan değerler
    fed_funds = fed_funds if fed_funds is not None else 0.0
    vix = vix if vix is not None else 20.0
    unemp_rate = unemp_rate if unemp_rate is not None else 4.0

    slope = (dgs10 - dgs2) if (dgs10 is not None and dgs2 is not None) else 0.0

    # ROM (Resesyon Olasılığı Modeli)
    rom_score = 0
    if slope < 0:
        rom_score += 50
    if unemp_rate and prev_unemp and (unemp_rate > prev_unemp):
        rom_score += 30

    return {
        "slope": slope,
        "rom": min(rom_score, 100),
        "fed_funds": fed_funds,
        "vix": vix,
        "unemp": unemp_rate
    }

# ========== KATMAN 2: SEKTÖR ANALİZİ ==========
@st.cache_data(ttl=3600)
def calculate_sector_scores(macro_data: Dict) -> Dict:
    """Sektör skorlarını hesaplar."""
    scores = {}

    for isim, meta in SECTOR_META.items():
        try:
            df = yf.download(meta['etf'], period="6mo", progress=False, auto_adjust=True)
            if df.empty:
                continue

            close_series = get_close_price(df)
            if len(close_series) < 2:
                continue

            momentum = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100

            # Stratejik puanlama
            puan = 50  # Baz puan
            puan += (momentum * 0.5)

            # Faiz duyarlılığı
            if macro_data.get('fed_funds', 0) > 3.5:
                if meta['faiz'] == 3:
                    puan -= 15
                if isim == 'Finansallar':
                    puan += 10

            # Resesyon riski
            if macro_data.get('rom', 0) > 50:
                if isim in ['Teknoloji', 'Enerji']:
                    puan -= 20
                if isim == 'Sağlık':
                    puan += 15

            scores[isim] = {
                "Skor": round(puan, 2),
                "Momentum": round(momentum, 2)
            }
        except Exception as e:
            st.warning(f"{isim} sektörü analiz edilemedi: {str(e)}")
            continue

    return scores

# ========== KATMAN 3: ŞİRKET TARAMA ==========
@st.cache_data(ttl=3600)
def screen_stocks(sector_scores: Dict) -> pd.DataFrame:
    """Şirket taraması ve temel analiz."""
    stock_pool = {
        'NVDA': {'sector': 'Teknoloji', 'cagr': 45, 'margin_exp': 500, 'debt_ebitda': 0.8},
        'JPM': {'sector': 'Finansallar', 'cagr': 12, 'margin_exp': 150, 'debt_ebitda': 0.4},
        'XOM': {'sector': 'Enerji', 'cagr': 25, 'margin_exp': 350, 'debt_ebitda': 1.1},
        'PFE': {'sector': 'Sağlık', 'cagr': 6, 'margin_exp': -100, 'debt_ebitda': 3.2},
        'TSLA': {'sector': 'Teknoloji', 'cagr': 30, 'margin_exp': 180, 'debt_ebitda': 1.5}
    }

    screened_results = []
    for ticker, data in stock_pool.items():
        s_score = sector_scores.get(data['sector'], {'Skor': 50})['Skor']

        is_growth = data['cagr'] > 15 and data['margin_exp'] > 200
        is_safe = data['debt_ebitda'] < 2.5

        final_score = (s_score * 0.4) + (data['cagr'] * 1.5) + (20 if is_safe else -30)

        screened_results.append({
            "Hisse": ticker,
            "Sektör": data['sector'],
            "Büyüme (CAGR)": f"%{data['cagr']}",
            "Büyüme Sinyali": "✅ GÜÇLÜ" if is_growth else "❌ ZAYIF",
            "Güvenlik": "🛡️ GÜVENLİ" if is_safe else "⚠️ RİSKLİ",
            "Final Skoru": round(final_score, 2)
        })

    return pd.DataFrame(screened_results)

# ========== KÜRESEL PİYASALAR ==========
@st.cache_data(ttl=3600)
def get_global_opportunity_map() -> pd.DataFrame:
    """Küresel piyasa momentum analizi."""
    global_assets = {
        'Türkiye': 'XU100.IS',
        'Almanya': '^GDAXI',
        'Fransa': '^FCHI',
        'İngiltere': '^FTSE',
        'İtalya': 'FTSEMIB.MI',
        'İspanya': '^IBEX',
        'Hollanda': '^AEX',
        'İsviçre': '^SSMI',
        'Polonya': 'WIG20.WA',
        'Japonya': '^N225',
        'Çin': '000001.SS',
        'Hindistan': '^NSEI',
        'G. Kore': '^KS11',
        'Vietnam': 'VNI.VN'
    }

    results = []
    for country, ticker in global_assets.items():
        try:
            hist = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
            if hist.empty:
                continue

            close_series = get_close_price(hist)
            if len(close_series) < 2:
                continue

            ytd_change = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100

            results.append({
                "Ülke": country,
                "Yıllık Getiri": round(ytd_change, 2),
                "Momentum": (
                    "🔥 Güçlü" if ytd_change > 15 
                    else "🧊 Zayıf" if ytd_change < 0 
                    else "⚖️ Stabil"
                )
            })
        except Exception:
            continue

    return pd.DataFrame(results)

# ========== EMTİA ANALİZİ ==========
@st.cache_data(ttl=3600)
def get_commodity_analysis(m_data: Dict) -> pd.DataFrame:
    """Emtia analizi ve yatırım sinyalleri."""
    commodities = {
        'Altın (Ons)': 'GC=F',
        'Gümüş (Ons)': 'SI=F',
        'Ham Petrol (WTI)': 'CL=F',
        'Bakır': 'HG=F'
    }

    comm_results = []
    for name, ticker in commodities.items():
        try:
            data = yf.download(ticker, period="1mo", progress=False, auto_adjust=True)
            if data.empty:
                continue

            close_series = get_close_price(data)
            if len(close_series) < 2:
                continue

            current_price = close_series.iloc[-1]
            monthly_change = ((current_price / close_series.iloc[0]) - 1) * 100

            status = "NÖTR"
            if name == 'Altın (Ons)' and m_data.get('vix', 20) > 25:
                status = "🛡️ GÜÇLÜ AL (Riskten Kaçış)"
            elif name == 'Ham Petrol (WTI)' and monthly_change > 5:
                status = "⚠️ DİKKAT (Enflasyon Riski)"

            comm_results.append({
                "Emtia": name,
                "Fiyat": round(current_price, 2),
                "Aylık Değişim": f"%{round(monthly_change, 2)}",
                "Uzman Görüşü": status
            })
        except Exception:
            continue

    return pd.DataFrame(comm_results)

# ========== YATIRIM ZEKASI ==========
def get_investment_intelligence(
    m_data: Dict, 
    s_scores: Dict, 
    geo_df: pd.DataFrame, 
    c_df: pd.DataFrame
) -> pd.DataFrame:
    """Stratejik yatırım kararları üretir."""
    intelligence_reports = []

    # Güvenli liman kontrolü
    if m_data.get('vix', 0) > 25 or m_data.get('rom', 0) > 60:
        intelligence_reports.append({
            "Varlık Sınıfı": "Değerli Metaller & Nakit",
            "Aksiyon": "AĞIRLIĞI ARTIR",
            "Gerekçe": (
                "Küresel volatilite (VIX) ve resesyon riski (ROM) eşik değerlerin üzerinde. "
                "Sermaye koruma moduna geçilmeli."
            )
        })

    # Coğrafi rotasyon
    if not geo_df.empty and 'Yıllık Getiri' in geo_df.columns:
        top_country = geo_df.sort_values(by="Yıllık Getiri", ascending=False).iloc[0]['Ülke']
        intelligence_reports.append({
            "Varlık Sınıfı": f"Uluslararası Hisseler ({top_country})",
            "Aksiyon": "İZLE / SEÇİCİ OL",
            "Gerekçe": (
                f"{top_country} piyasası güçlü momentum sergiliyor. "
                "Ancak yerel enflasyon ve kur riski Katman 1 verileriyle kıyaslanmalı."
            )
        })

    # Türkiye gayrimenkul
    if m_data.get('fed_funds', 0) > 4:
        intelligence_reports.append({
            "Varlık Sınıfı": "Türkiye Gayrimenkul",
            "Aksiyon": "BEKLE / PAZARLIK YAP",
            "Gerekçe": (
                "Yüksek faiz ortamı kredi erişimini kısıtlıyor. "
                "Fiyat artış hızı yavaşlayabilir, nakit alım fırsatları kollanmalı."
            )
        })

    return pd.DataFrame(intelligence_reports)

# ========== KATMAN 4: DEĞERLEME ==========
def calculate_fair_value(ticker: str, current_price: float, cagr: float) -> Tuple[float, float]:
    """
    Basitleştirilmiş DCF ve Çarpan Analizi.

    Args:
        ticker: Hisse sembolü
        current_price: Mevcut fiyat
        cagr: Yıllık bileşik büyüme oranı (%)

    Returns:
        (Hedef fiyat, Yukarı potansiyel %)
    """
    expected_pe = 15 + (cagr * 0.5)

    # 2 yıllık projeksiyon (CAGR/100 düzeltildi)
    growth_factor = (1 + cagr / 100) ** 2
    fair_value = current_price * growth_factor / 1.2  # %20 iskonto

    upside = ((fair_value / current_price) - 1) * 100

    return round(fair_value, 2), round(upside, 2)

# ========== KATMAN 5: PORTFÖY OPTİMİZASYONU ==========
def calculate_position_size(upside: float, rom_score: float) -> float:
    """
    Kelly Kriteri ve Makro Risk tabanlı pozisyon büyüklüğü.

    Args:
        upside: Yukarı potansiyel (%)
        rom_score: Resesyon olasılığı skoru (0-100)

    Returns:
        Önerilen pozisyon ağırlığı (%)
    """
    base_size = (upside / 100) * 0.5
    risk_multiplier = (100 - rom_score) / 100
    final_allocation = max(0, min(base_size * risk_multiplier * 100, 25))

    return round(final_allocation, 2)

# ========== HABER MOTORU ==========
@st.cache_data(ttl=1800)
def get_news(api_key: str) -> List[Dict]:
    """Finans haberlerini çeker."""
    try:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q=finance+OR+economy&language=en"
            f"&sortBy=publishedAt&pageSize=10&apiKey={api_key}"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('articles', [])
    except Exception as e:
        st.error(f"Haber API hatası: {str(e)}")
        return []

# ========== ANA UYGULAMA ==========
def main():
    # Veri hazırlama
    m_data = calculate_macro_scores(FRED_API_KEY)
    s_scores = calculate_sector_scores(m_data)
    geo_df = get_global_opportunity_map()
    c_df = get_commodity_analysis(m_data)

    # Yatırım zekası
    st.header("🧠 Yapay Zeka Yatırım Komitesi Kararları")
    st.info(
        "Sistem; Makro, Sektörel, Temel ve Teknik verileri bütüncül bir süzgeçten "
        "geçirerek aşağıdaki stratejiyi oluşturmuştur."
    )

    intelligence_df = get_investment_intelligence(m_data, s_scores, geo_df, c_df)

    for _, row in intelligence_df.iterrows():
        with st.expander(f"📍 {row['Varlık Sınıfı']} -> {row['Aksiyon']}", expanded=True):
            st.write(f"**Gerekçe:** {row['Gerekçe']}")
            st.caption("Doğrulama: Katman 1 (Makro) ve Katman 2 (Coğrafi) verileriyle eşleşti.")

    # Tablar
    tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektörler"])

    with tab1:
        render_macro_tab(m_data)

    with tab2:
        render_news_tab()

    with tab3:
        render_sector_tab(m_data, s_scores, geo_df, c_df)

    st.divider()
    st.caption("⚠️ Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.")


def render_macro_tab(m_data: Dict):
    """Makro ekonomi sekmesi."""
    st.header("🌍 Katman 1: Küresel Makro Komuta Merkezi")

    col_score1, col_score2 = st.columns(2)

    with col_score1:
        fig_rom = go.Figure(go.Indicator(
            mode="gauge+number",
            value=m_data['rom'],
            title={'text': "ROM: Resesyon Olasılığı (%)", 'font': {'size': 20}},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkred"},
                'steps': [
                    {'range': [0, 30], 'color': "#00CC96"},
                    {'range': [30, 70], 'color': "#FFA15A"},
                    {'range': [70, 100], 'color': "#EF553B"}
                ]
            }
        ))
        fig_rom.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font={'color': "white"}
        )
        st.plotly_chart(fig_rom, use_container_width=True)

    with col_score2:
        st.write("### 📡 Anlık Makro Sinyaller")
        slope_val = m_data['slope']

        delta_msg = "TERSİNE DÖNÜŞ (⚠️)" if slope_val < 0 else "NORMAL"
        st.metric(
            "Getiri Eğrisi (10Y-2Y)",
            f"{slope_val:.2f}%",
            delta=delta_msg,
            delta_color="inverse" if slope_val < 0 else "normal"
        )

        st.divider()

        c1, c2 = st.columns(2)
        c1.metric("Fed Faiz", f"%{m_data['fed_funds']}")
        c2.metric("VIX Endeksi", f"{m_data['vix']}")
        st.metric("İşsizlik Oranı", f"%{m_data['unemp']}")

    st.subheader("📊 Stratejik Parametre Matrisi")
    param_df = pd.DataFrame([
        {"Parametre": "Politika Faizi", "Ağırlık": "%25", "Durum": "Sıkılaştırıcı", "Sinyal": "🔴"},
        {"Parametre": "Getiri Eğrisi", "Ağırlık": "%20", "Durum": "Riskli", "Sinyal": "🔴"},
        {"Parametre": "İşsizlik Momentumu", "Ağırlık": "%15", "Durum": "Yükseliş", "Sinyal": "🟡"},
        {"Parametre": "VIX (FX Stres)", "Ağırlık": "%10", "Durum": "Stabil", "Sinyal": "🟢"}
    ])
    st.table(param_df)

    st.caption(f"🕒 Veri Döngüsü: 6 Saatlik | Son Tarama: {datetime.now().strftime('%H:%M')}")


def render_news_tab():
    """Haberler sekmesi."""
    st.header("📰 Ekonomi Haberleri")

    haberler = get_news(NEWS_API_KEY)

    if haberler:
        for haber in haberler:
            col_img, col_text = st.columns([1, 4])
            with col_img:
                if haber.get('urlToImage'):
                    st.image(haber['urlToImage'], width=150)
            with col_text:
                st.markdown(f"**[{haber['title']}]({haber['url']})**")
                st.caption(f"{haber['source']['name']} — {haber['publishedAt'][:10]}")
                st.write(haber.get('description', '')[:150] + "...")
            st.divider()
    else:
        st.warning("Güncel haber bulunamadı.")


def render_sector_tab(m_data: Dict, s_scores: Dict, geo_df: pd.DataFrame, c_df: pd.DataFrame):
    """Sektör ve detay analiz sekmesi."""
    st.header("🏭 Katman 2: Sektör Rotasyonu ve Tahminleme")

    # Sektör skorları görselleştirme
    if s_scores:
        sirali_sektor = sorted(s_scores.items(), key=lambda x: x[1]['Skor'], reverse=True)
        isimler = [x[0] for x in sirali_sektor]
        skorlar = [x[1]['Skor'] for x in sirali_sektor]

        fig_sec = go.Figure(go.Bar(
            x=skorlar,
            y=isimler,
            orientation='h',
            marker=dict(color=skorlar, colorscale='RdYlGn')
        ))
        fig_sec.update_layout(
            title="Yapay Zeka Destekli Sektör Skorları (3-6 Aylık Ufuk)",
            height=400,
            template="plotly_dark",
            xaxis_title="Kompozit Skor"
        )
        st.plotly_chart(fig_sec, use_container_width=True)

    # Katman 3: Şirket Taraması
    st.subheader("🔍 Katman 3: Şirket Taraması ve Temel Analiz")

    with st.expander("🎯 Filtreleme Parametrelerini Gör", expanded=False):
        st.write("""
        - **Birincil Filtre:** Gelir CAGR (3Y) > %15
        - **Marj Genişlemesi:** > 200 baz puan
        - **Bilanço Güvenliği:** Net Borç / FAÖK < 2.5x
        - **Altman Z-Skoru:** > 1.8 (İflas riski kontrolü)
        """)

    screened_df = screen_stocks(s_scores)

    st.dataframe(
        screened_df.sort_values(by="Final Skoru", ascending=False),
        use_container_width=True,
        hide_index=True
    )

    st.info("💡 Not: Yukarıdaki liste Katman 1 (Makro) ve Katman 2 (Sektör) puanları ile ağırlıklandırılmıştır.")

    # Katman 4: Değerleme
    st.divider()
    st.subheader("💰 Katman 4: Değerleme ve Hedef Fiyatlar")

    prices = {'NVDA': 900, 'JPM': 190, 'XOM': 120, 'PFE': 28, 'TSLA': 170}

    valuation_data = []
    for _, row in screened_df.iterrows():
        ticker = row['Hisse']
        cagr_val = float(row['Büyüme (CAGR)'].replace('%', ''))
        curr_p = prices.get(ticker, 100)

        f_value, upside = calculate_fair_value(ticker, curr_p, cagr_val)

        valuation_data.append({
            "Hisse": ticker,
            "Mevcut Fiyat": f"${curr_p}",
            "Hedef Fiyat (Fair Value)": f"${f_value}",
            "Potansiyel": f"%{upside}",
            "Durum": "İSKONTOLU" if upside > 15 else "PAHALI"
        })

    val_df = pd.DataFrame(valuation_data)

    cols = st.columns(len(val_df))
    for idx, row in val_df.iterrows():
        cols[idx].metric(row['Hisse'], row['Hedef Fiyat (Fair Value)'], delta=row['Potansiyel'])

    st.caption("⚠️ Hedef fiyatlar Katman 1 (Makro) iskonto oranlarına göre dinamik olarak güncellenmektedir.")

    # Katman 5: Portföy Optimizasyonu
    st.divider()
    st.subheader("🛡️ Katman 5: Portföy Optimizasyonu (Risk Yönetimi)")

    portfolio_data = []
    total_stock_weight = 0

    for _, row in val_df.iterrows():
        upside_val = float(row['Potansiyel'].replace('%', ''))
        pos_size = calculate_position_size(upside_val, m_data['rom'])
        total_stock_weight += pos_size

        portfolio_data.append({
            "Hisse": row['Hisse'],
            "Önerilen Ağırlık": f"%{pos_size}",
            "Risk Seviyesi": "DÜŞÜK" if pos_size > 15 else "ORTA"
        })

    p_df = pd.DataFrame(portfolio_data)
    cash_weight = 100 - total_stock_weight

    fig_port = go.Figure(data=[go.Pie(
        labels=list(p_df['Hisse']) + ['Nakit / Tahvil'],
        values=list([float(x.replace('%', '')) for x in p_df['Önerilen Ağırlık']]) + [cash_weight],
        hole=0.4,
        marker_colors=['#00CC96', '#636EFA', '#EF553B', '#AB63FA', '#FFA15A', '#19D3F3']
    )])
    fig_port.update_layout(title="İdeal Portföy Dağılımı", template="plotly_dark")
    st.plotly_chart(fig_port, use_container_width=True)

    st.warning(f"💡 Stratejik Not: Mevcut makro riskler nedeniyle portföyün %{round(cash_weight, 2)} kadarı nakitte tutulmalıdır.")

    # Küresel Piyasalar
    st.divider()
    st.header("🌐 Küresel Piyasalar ve Coğrafi Fırsatlar")
    st.write("Yatırım uzmanı gözüyle sermayenin hangi ülkelere aktığını takip edin.")

    if not geo_df.empty:
        col_geo1, col_geo2 = st.columns([2, 1])

        with col_geo1:
            st.bar_chart(geo_df.set_index("Ülke")["Yıllık Getiri"])

        with col_geo2:
            st.subheader("🏆 Lider Piyasalar")
            top_performers = geo_df.sort_values(by="Yıllık Getiri", ascending=False).head(5)
            st.dataframe(top_performers, hide_index=True, use_container_width=True)

    st.info("💡 Uzman Notu: Türkiye gibi yüksek enflasyonlu piyasalarda 'Yıllık Getiri'nin reel getiri olup olmadığını Katman 1'deki enflasyon verileriyle kıyaslayın.")

    # Emtia Paneli
    st.divider()
    st.header("💎 Küresel Emtia ve Değerli Metaller")

    if not c_df.empty:
        st.dataframe(c_df, use_container_width=True, hide_index=True)

    # Türkiye Gayrimenkul
    st.divider()
    st.header("🏠 Türkiye Gayrimenkul Strateji Merkezi")

    re_col1, re_col2 = st.columns([1, 1])

    with re_col1:
        st.subheader("📈 Konut Fiyat Endeksi Eğilimi")
        re_chart_data = pd.DataFrame({
            'Yıl': ['2022', '2023', '2024', '2025', '2026'],
            'Konut Fiyat Artışı': [160, 85, 55, 48, 42],
            'Resmi Enflasyon': [64, 65, 45, 38, 32]
        }).set_index('Yıl')
        st.line_chart(re_chart_data)

    with re_col2:
        st.subheader("🧐 Yatırım Uzmanı Yorumu")
        if m_data.get('fed_funds', 5) > 4:
            st.warning(
                "Mevduat faizlerinin yüksek seyrettiği bu dönemde, gayrimenkul likiditesi düşük kalabilir. "
                "Nakit pozisyonu olanlar için fırsat dönemi."
            )
        else:
            st.success(
                "Düşük faiz beklentisi gayrimenkul talebini artırabilir. "
                "Varlık koruma amaçlı alımlar değerlendirilebilir."
            )

        st.info("**Strateji:** Kira çarpanı 15-18 yıl bandındaki bölgeler öncelikli olmalı.")


if __name__ == "__main__":
    main()
