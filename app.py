import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import requests

# ========== SIFRE KORUMASI ==========
st.set_page_config(page_title="FinsightAI", page_icon="📊", layout="wide")

if "sifre_dogrulandi" not in st.session_state:
    st.session_state.sifre_dogrulandi = False

if not st.session_state.sifre_dogrulandi:
    st.title("🔒 FinsightAI")
    sifre = st.text_input("Sifre", type="password")
    if st.button("Giris"):
        if sifre == "Finans@12345":
            st.session_state.sifre_dogrulandi = True
            st.rerun()
        else:
            st.error("❌ Yanlis sifre!")
    st.stop()

# ========== GLOBAL TANIMLAMALAR (Kritik Hata Düzeltme) ==========
# sector_meta'yı fonksiyonların erişebileceği en üst seviyeye taşıdık.
sector_meta = {
    'Teknoloji': {'faiz': 3, 'enflasyon': 1, 'etf': 'XLK'},
    'Finansallar': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLF'},
    'Enerji': {'faiz': 1, 'enflasyon': 3, 'etf': 'XLE'},
    'Sağlık': {'faiz': 2, 'enflasyon': 1, 'etf': 'XLV'},
    'Kamu Hizmetleri': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLU'},
    'Gayrimenkul': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLRE'}
}

# API anahtarları
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
except:
    FRED_API_KEY = "9d3135bcfce4a8a3af3ccc3488a94a12"
    NEWS_API_KEY = "361bdcc09ce647f2b47d22addbbec35c"

# --- KATMAN 1 HESAPLAMA MOTORLARI ---
def get_fred_val(series_id, api_key):
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
        response = requests.get(url)
        data = response.json()
        if 'observations' in data and len(data['observations']) >= 2:
            val = data['observations'][0]['value']
            prev = data['observations'][1]['value']
            val = float(val) if val != '.' else None
            prev = float(prev) if prev != '.' else None
            return val, prev
        return None, None
    except Exception:
        return None, None
        
def calculate_macro_scores(api_key):
    fed_funds, _ = get_fred_val('FEDFUNDS', api_key)
    dgs10, _ = get_fred_val('DGS10', api_key)
    dgs2, _ = get_fred_val('DGS2', api_key)
    vix, _ = get_fred_val('VIXCLS', api_key)
    unemp_rate, prev_unemp = get_fred_val('UNRATE', api_key)
    
    fed_funds = fed_funds if fed_funds is not None else 0.0
    vix = vix if vix is not None else 20.0
    unemp_rate = unemp_rate if unemp_rate is not None else 4.0
    slope = (dgs10 - dgs2) if (dgs10 is not None and dgs2 is not None) else 0.0
    
    rom_score = 0
    if slope < 0: rom_score += 50
    if unemp_rate and prev_unemp and (unemp_rate > prev_unemp): rom_score += 30
    
    return {"slope": slope, "rom": min(rom_score, 100), "fed_funds": fed_funds, "vix": vix, "unemp": unemp_rate}

def calculate_sector_scores(macro_data):
    scores = {}
    for isim, meta in sector_meta.items():
        try:
            df = yf.download(meta['etf'], period="6mo", progress=False, auto_adjust=True)
            if df.empty: continue
            close_series = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            momentum = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100
            
            puan = 50 
            puan += (momentum * 0.5) 
            
            if macro_data['fed_funds'] > 3.5:
                if meta['faiz'] == 3: puan -= 15
                if isim == 'Finansallar': puan += 10
            
            if macro_data['rom'] > 50:
                if isim in ['Teknoloji', 'Enerji']: puan -= 20
                if isim == 'Sağlık': puan += 15
            
            scores[isim] = {"Skor": round(puan, 2), "Momentum": round(momentum, 2)}
        except: continue
    return scores
    
def screen_stocks(sector_scores):
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
            "Hisse": ticker, "Sektör": data['sector'], "Büyüme (CAGR)": f"%{data['cagr']}",
            "Büyüme Sinyali": "✅ GÜÇLÜ" if is_growth else "❌ ZAYIF",
            "Güvenlik": "🛡️ GÜVENLİ" if is_safe else "⚠️ RİSKLİ", "Final Skoru": round(final_score, 2)
        })
    return pd.DataFrame(screened_results)

def get_global_opportunity_map():
    global_assets = {
        'Türkiye': 'XU100.IS', 'Almanya': '^GDAXI', 'Fransa': '^FCHI', 'İngiltere': '^FTSE',
        'İtalya': 'FTSEMIB.MI', 'İspanya': '^IBEX', 'Hollanda': '^AEX', 'Japonya': '^N225'
    }
    results = []
    for country, ticker in global_assets.items():
        try:
            hist = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
            if not hist.empty:
                close_series = hist['Close'].iloc[:, 0] if isinstance(hist['Close'], pd.DataFrame) else hist['Close']
                ytd_change = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100
                results.append({
                    "Ülke": country, "Yıllık Getiri": round(ytd_change, 2),
                    "Momentum": "🔥 Güçlü" if ytd_change > 15 else ("🧊 Zayıf" if ytd_change < 0 else "⚖️ Stabil")
                })
        except: continue
    return pd.DataFrame(results)

def get_commodity_analysis(m_data):
    commodities = {'Altın (Ons)': 'GC=F', 'Gümüş (Ons)': 'SI=F', 'Ham Petrol (WTI)': 'CL=F', 'Bakır': 'HG=F'}
    comm_results = []
    for name, ticker in commodities.items():
        try:
            data = yf.download(ticker, period="1mo", progress=False, auto_adjust=True)
            if not data.empty:
                close_series = data['Close'].iloc[:, 0] if isinstance(data['Close'], pd.DataFrame) else data['Close']
                current_price = close_series.iloc[-1]
                monthly_change = ((current_price / close_series.iloc[0]) - 1) * 100
                status = "NÖTR"
                if name == 'Altın (Ons)' and m_data.get('vix', 20) > 25: status = "🛡️ GÜÇLÜ AL"
                elif name == 'Ham Petrol (WTI)' and monthly_change > 5: status = "⚠️ DİKKAT"
                comm_results.append({"Emtia": name, "Fiyat": round(current_price, 2), "Aylık Değişim": f"%{round(monthly_change, 2)}", "Uzman Görüşü": status})
        except: continue
    return pd.DataFrame(comm_results)

def get_investment_intelligence(m_data, s_scores, geo_df, c_df):
    intelligence_reports = []
    if m_data['vix'] > 25 or m_data['rom'] > 60:
        intelligence_reports.append({"Varlık Sınıfı": "Değerli Metaller", "Aksiyon": "AĞIRLIĞI ARTIR", "Gerekçe": "Küresel risk (VIX) yüksek."})
    
    if not geo_df.empty:
        top_country = geo_df.sort_values(by="Yıllık Getiri", ascending=False).iloc[0]['Ülke']
        intelligence_reports.append({"Varlık Sınıfı": f"Uluslararası ({top_country})", "Aksiyon": "İZLE", "Gerekçe": f"{top_country} güçlü momentumda."})
    
    return pd.DataFrame(intelligence_reports)

def calculate_fair_value(ticker, current_price, cagr):
    fair_value = current_price * (1 + (cagr/100))**2 / 1.2
    upside = ((fair_value / current_price) - 1) * 100
    return round(fair_value, 2), round(upside, 2)

def calculate_position_size(upside, rom_score):
    base_size = (upside / 100) * 0.5 
    risk_multiplier = (100 - rom_score) / 100
    return round(max(0, min(base_size * risk_multiplier * 100, 25)), 2)

# --- VERİ HAZIRLIK SÜRECİ ---
m_data = calculate_macro_scores(FRED_API_KEY)
s_scores = calculate_sector_scores(m_data)
geo_df = get_global_opportunity_map()
c_df = get_commodity_analysis(m_data)
intelligence_df = get_investment_intelligence(m_data, s_scores, geo_df, c_df)

# --- ARAYÜZ ---
st.title("📊 Kisisel Finans AI")
st.caption(f"Son guncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

st.header("🧠 Yapay Zeka Yatırım Komitesi Kararları")
for idx, row in intelligence_df.iterrows():
    with st.expander(f"📍 {row['Varlık Sınıfı']} -> {row['Aksiyon']}", expanded=True):
        st.write(f"**Gerekçe:** {row['Gerekçe']}")

tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektorler"])

with tab1:
    col_score1, col_score2 = st.columns(2)
    with col_score1:
        fig_rom = go.Figure(go.Indicator(
            mode = "gauge+number", value = m_data['rom'],
            title = {'text': "ROM: Resesyon Olasılığı (%)"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "darkred"}}
        ))
        st.plotly_chart(fig_rom, use_container_width=True)
    with col_score2:
        st.metric("Getiri Eğrisi (10Y-2Y)", f"{m_data['slope']:.2f}%")
        st.metric("Fed Faiz", f"%{m_data['fed_funds']}")
        st.metric("VIX Endeksi", f"{m_data['vix']}")

with tab2:
    @st.cache_data(ttl=1800)
    def get_news(api_key):
        try:
            url = f"https://newsapi.org/v2/everything?q=finance+OR+economy&language=en&sortBy=publishedAt&pageSize=10&apiKey={api_key}"
            r = requests.get(url, timeout=10)
            return r.json().get('articles', [])
        except: return []

    haberler = get_news(NEWS_API_KEY)
    if haberler:
        for h in haberler:
            st.markdown(f"**[{h['title']}]({h['url']})**")
            st.caption(f"{h['source']['name']} — {h['publishedAt'][:10]}")
            st.divider()

with tab3:
    if s_scores:
        sirali = sorted(s_scores.items(), key=lambda x: x[1]['Skor'], reverse=True)
        fig_sec = go.Figure(go.Bar(x=[x[1]['Skor'] for x in sirali], y=[x[0] for x in sirali], orientation='h'))
        st.plotly_chart(fig_sec, use_container_width=True)

    screened_df = screen_stocks(s_scores)
    st.subheader("🔍 Şirket Taraması")
    st.dataframe(screened_df, use_container_width=True, hide_index=True)

    st.subheader("🛡️ Portföy Optimizasyonu")
    prices = {'NVDA': 900, 'JPM': 190, 'XOM': 120, 'PFE': 28, 'TSLA': 170}
    portfolio_labels = []
    portfolio_values = []
    for _, row in screened_df.iterrows():
        ticker = row['Hisse']
        cagr_val = float(row['Büyüme (CAGR)'].replace('%', ''))
        _, upside = calculate_fair_value(ticker, prices.get(ticker, 100), cagr_val)
        pos_size = calculate_position_size(upside, m_data['rom'])
        portfolio_labels.append(ticker)
        portfolio_values.append(pos_size)
    
    fig_port = go.Figure(data=[go.Pie(labels=portfolio_labels + ['Nakit'], values=portfolio_values + [100-sum(portfolio_values)], hole=.4)])
    st.plotly_chart(fig_port, use_container_width=True)

st.divider()
st.header("🌐 Küresel Piyasalar ve Emtia")
col_g1, col_g2 = st.columns(2)
with col_g1: st.dataframe(geo_df, hide_index=True)
with col_g2: st.dataframe(c_df, hide_index=True)

st.caption("⚠️ Bilgilendirme amaclıdır, yatırım tavsiyesi degildir.")
