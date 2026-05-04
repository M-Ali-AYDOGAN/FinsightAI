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

# ========== ASIL UYGULAMA ==========
st.title("📊 Kisisel Finans AI")
st.caption(f"Son guncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# API anahtarları (Secrets yoksa yedekler devreye girer)
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
        data = requests.get(url).json()
        if 'observations' in data and len(data['observations']) >= 2:
            val = float(data['observations'][0]['value'])
            prev = float(data['observations'][1]['value'])
            return val, prev
    except: return None, None

def calculate_macro_scores(api_key):
    # Veri Toplama
    fed_funds, _ = get_fred_val('FEDFUNDS', api_key)
    dgs10, _ = get_fred_val('DGS10', api_key)
    dgs2, _ = get_fred_val('DGS2', api_key)
    vix, _ = get_fred_val('VIXCLS', api_key)
    unemp_rate, prev_unemp = get_fred_val('UNRATE', api_key)
    
    slope = (dgs10 - dgs2) if (dgs10 and dgs2) else 0
    
    # ROM (Resesyon Olasılığı Modeli) Mantığı
    rom_score = 0
    if slope < 0: rom_score += 50 # Getiri eğrisi tersse
    if unemp_rate and prev_unemp and (unemp_rate > prev_unemp): rom_score += 30 # İşsizlik artışı
    if vix and vix > 30: rom_score += 20 # Yüksek volatilite
    
    return {
        "slope": slope,
        "rom": min(rom_score, 100),
        "fed_funds": fed_funds,
        "vix": vix,
        "unemp": unemp_rate
    }

tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektorler"])

with tab1:
    st.header("🌍 Katman 1: Küresel Makro Komuta Merkezi")
    
    # Verileri hesapla
    m_data = calculate_macro_scores(FRED_API_KEY)
    
    # Gösterge Paneli
    col_score1, col_score2 = st.columns(2)
    
    with col_score1:
        # Resesyon Olasılığı Kadranı (Gauge)
        fig_rom = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = m_data['rom'],
            title = {'text': "ROM: Resesyon Olasılığı (%)", 'font': {'size': 20}},
            gauge = {
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkred"},
                'steps': [
                    {'range': [0, 30], 'color': "#00CC96"},
                    {'range': [30, 70], 'color': "#FFA15A"},
                    {'range': [70, 100], 'color': "#EF553B"}]
            }
        ))
        fig_rom.update_layout(height=350, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
        st.plotly_chart(fig_rom, use_container_width=True)

    with col_score2:
        st.write("### 📡 Anlık Makro Sinyaller")
        slope_val = m_data['slope']
        
        # Getiri Eğrisi Durumu
        delta_msg = "TERSİNE DÖNÜŞ (⚠️)" if slope_val < 0 else "NORMAL"
        st.metric("Getiri Eğrisi (10Y-2Y)", f"{slope_val:.2f}%", delta=delta_msg, delta_color="inverse" if slope_val < 0 else "normal")
        
        st.divider()
        
        # Diğer Önemli Veriler
        c1, c2 = st.columns(2)
        c1.metric("Fed Faiz", f"%{m_data['fed_funds']}")
        c2.metric("VIX Endeksi", f"{m_data['vix']}")
        st.metric("İşsizlik Oranı", f"%{m_data['unemp']}")

    st.subheader("📊 Stratejik Parametre Matrisi")
    # Manuel sinyal tablosu (İleride bunlar tam otomatik olacak)
    param_df = pd.DataFrame([
        {"Parametre": "Politika Faizi", "Ağırlık": "%25", "Durum": "Sıkılaştırıcı", "Sinyal": "🔴"},
        {"Parametre": "Getiri Eğrisi", "Ağırlık": "%20", "Durum": "Riskli", "Sinyal": "🔴"},
        {"Parametre": "İşsizlik Momentumu", "Ağırlık": "%15", "Durum": "Yükseliş", "Sinyal": "🟡"},
        {"Parametre": "VIX (FX Stres)", "Ağırlık": "%10", "Durum": "Stabil", "Sinyal": "🟢"}
    ])
    st.table(param_df)
    
    st.caption(f"🕒 Veri Döngüsü: 6 Saatlik | Son Tarama: {datetime.now().strftime('%H:%M')}")

with tab2:
    st.header("📰 Ekonomi Haberleri")
    @st.cache_data(ttl=1800)
    def get_news():
        try:
            # Haberleri bugüne kısıtlamak yerine "en güncel" olacak şekilde çekiyoruz
            url = f"https://newsapi.org/v2/everything?q=finance+OR+economy&language=en&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json().get('articles', [])
            return []
        except: return []
    
    haberler = get_news()
    if haberler:
        for haber in haberler:
            col_img, col_text = st.columns([1, 4])
            with col_img:
                if haber.get('urlToImage'): st.image(haber['urlToImage'], width=150)
            with col_text:
                st.markdown(f"**[{haber['title']}]({haber['url']})**")
                st.caption(f"{haber['source']['name']} — {haber['publishedAt'][:10]}")
                st.write(haber.get('description', '')[:150] + "...")
            st.divider()
    else: st.warning("Guncel haber bulunamadi.")

with tab3:
    st.header("🏭 Katman 2: Sektör Rotasyonu ve Tahminleme")
    
    # Sektör Duyarlılık Veritabanı (Senin Spesifikasyonun)
    # 1: Düşük, 2: Orta, 3: Yüksek Duyarlılık
    sector_meta = {
        'Teknoloji': {'faiz': 3, 'enflasyon': 1, 'etf': 'XLK'},
        'Finansallar': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLF'},
        'Enerji': {'faiz': 1, 'enflasyon': 3, 'etf': 'XLE'},
        'Sağlık': {'faiz': 2, 'enflasyon': 1, 'etf': 'XLV'},
        'Kamu Hizmetleri': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLU'},
        'Gayrimenkul': {'faiz': 3, 'enflasyon': 2, 'etf': 'XLRE'}
    }

    @st.cache_data(ttl=21600)
    def calculate_sector_scores(macro_data):
        scores = {}
        for isim, meta in sector_meta.items():
            try:
                # Fiyat Momentumu (6 Aylık)
                df = yf.download(meta['etf'], period="6mo", progress=False, auto_adjust=True)
                close_series = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                momentum = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100
                
                # --- STRATEJİK PUANLAMA (Katman 2 Mantığı) ---
                puan = 50 # Baz puan
                puan += (momentum * 0.5) # Momentum ağırlığı %50
                
                # Faiz Duyarlılığı Ayarlaması
                if macro_data['fed_funds'] > 3.5: # Faizler yüksekse
                    if meta['faiz'] == 3: puan -= 15 # Faiz hassasiyeti yüksek olanı cezalandır
                    if isim == 'Finansallar': puan += 10 # Bankalar için pozitif
                
                # Resesyon Risk Ayarlaması (ROM)
                if macro_data['rom'] > 50:
                    if isim in ['Teknoloji', 'Enerji']: puan -= 20 # Döngüsel sektörler
                    if isim == 'Sağlık': puan += 15 # Savunmacı sektörler
                
                scores[isim] = {"Skor": round(puan, 2), "Momentum": round(momentum, 2)}
            except: continue
        return scores

    # Verileri Katman 1'den alıp işle
    s_scores = calculate_sector_scores(m_data) # m_data Katman 1'den geliyor
    
    if s_scores:
        # Görselleştirme: Isı Haritası Tadında Bar Grafik
        sirali_sektor = sorted(s_scores.items(), key=lambda x: x[1]['Skor'], reverse=True)
        isimler = [x[0] for x in sirali_sektor]
        skorlar = [x[1]['Skor'] for x in sirali_sektor]
        
        fig_sec = go.Figure(go.Bar(
            x=skorlar, y=isimler, orientation='h',
            marker=dict(color=skorlar, colorscale='RdYlGn')
        ))
        fig_sec.update_layout(title="Yapay Zeka Destekli Sektör Skorları (3-6 Aylık Ufuk)", 
                             height=400, template="plotly_dark", xaxis_title="Kompozit Skor")
        st.plotly_chart(fig_sec, use_container_width=True)

        # Sektör Detay Tablosu
        st.subheader("📋 Sektörel Duyarlılık ve Tahmin Matrisi")
        detay_df = pd.DataFrame([
            {"Sektör": k, "AI Skoru": v['Skor'], "6A Momentum": f"%{v['Momentum']}", 
             "Durum": "GÜÇLÜ AL" if v['Skor'] > 65 else ("ZAYIF" if v['Skor'] < 45 else "NÖTR")}
            for k, v in s_scores.items()
        ]).sort_values(by="AI Skoru", ascending=False)
        
        st.dataframe(detay_df, use_container_width=True, hide_index=True)

st.divider()
st.caption("⚠️ Bilgilendirme amaclıdır, yatırım tavsiyesi degildir.")
