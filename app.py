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

tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektorler"])

with tab1:
    st.header("🌍 Kuresel Makro Gostergeler")
    
    @st.cache_data(ttl=21600)
    def get_fred_data(series_id):
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=10"
            response = requests.get(url)
            data = response.json()
            if 'observations' in data and len(data['observations']) > 0:
                son = float(data['observations'][0]['value'])
                onceki = float(data['observations'][1]['value'])
                return son, onceki
            return None, None
        except:
            return None, None
    
    seriler = {
        'Fed Fonlari': 'FEDFUNDS', '10Y Hazine': 'DGS10', '2Y Hazine': 'DGS2',
        'VIX': 'VIXCLS', 'Brent Petrol': 'DCOILBRENTEU', 'Altin': 'GOLDAMGBD228NLBM'
    }
    
    col1, col2, col3 = st.columns(3)
    i = 0
    for isim, kod in seriler.items():
        son, onceki = get_fred_data(kod)
        if son is not None and onceki is not None:
            degisim = son - onceki
            target_col = [col1, col2, col3][i % 3]
            with target_col:
                st.metric(isim, f"{son:.2f}", f"{degisim:.3f}")
            i += 1
    
    st.subheader("📉 Getiri Egrisi (10Y - 2Y)")
    @st.cache_data(ttl=21600)
    def get_yield_curve():
        try:
            url_10y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            url_2y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            r10 = requests.get(url_10y).json()
            r2 = requests.get(url_2y).json()
            obs10 = {o['date']: o['value'] for o in r10['observations'] if o['value'] != '.'}
            obs2 = {o['date']: o['value'] for o in r2['observations'] if o['value'] != '.'}
            common_dates = sorted(list(set(obs10.keys()) & set(obs2.keys())), reverse=True)
            spreads = [float(obs10[d]) - float(obs2[d]) for d in common_dates]
            if not spreads: return None, 0
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=common_dates, y=spreads, mode='lines', name='Spread'))
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            fig.update_layout(height=400, template="plotly_dark")
            return fig, spreads[0]
        except: return None, 0
    
    f_yield, s_spread = get_yield_curve()
    if f_yield:
        st.plotly_chart(f_yield, use_container_width=True)
        if s_spread < 0: st.error(f"⚠️ Getiri egrisi tersine dondu: {s_spread:.2f}%")
        else: st.success(f"✅ Getiri egrisi normal: {s_spread:.2f}%")

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
    st.header("🏭 Sektor Rotasyonu (6 Aylik)")
    @st.cache_data(ttl=21600)
    def get_sector_momentum():
        etfler = {
            'Teknoloji': 'XLK', 'Finansal': 'XLF', 'Enerji': 'XLE',
            'Saglik': 'XLV', 'Tuketim': 'XLY', 'Kamu': 'XLU',
            'Hammadde': 'XLB', 'Sanayi': 'XLI', 'Gayrimenkul': 'XLRE', 'Iletisim': 'XLC'
        }
        sonuclar = {}
        for isim, sembol in etfler.items():
            try:
                df = yf.download(sembol, period="6mo", progress=False, auto_adjust=True)
                if not df.empty:
                    # MultiIndex yapısını düzleştirme (0-dim hatasını çözer)
                    close_data = df['Close']
                    if isinstance(close_data, pd.DataFrame):
                        close_series = close_data.iloc[:, 0]
                    else:
                        close_series = close_data
                    
                    ilk, son = float(close_series.iloc[0]), float(close_series.iloc[-1])
                    sonuclar[isim] = ((son / ilk) - 1) * 100
            except: continue
        return sonuclar

    momentum = get_sector_momentum()
    if momentum:
        sirali = dict(sorted(momentum.items(), key=lambda x: x[1], reverse=True))
        fig = go.Figure([go.Bar(x=list(sirali.keys()), y=list(sirali.values()),
                                marker_color=['green' if v > 0 else 'red' for v in sirali.values()])])
        fig.update_layout(height=500, template="plotly_dark", yaxis_title="Getiri (%)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(pd.DataFrame(sirali.items(), columns=['Sektor', 'Getiri (%)']), use_container_width=True)

st.divider()
st.caption("⚠️ Bilgilendirme amaclıdır, yatırım tavsiyesi degildir.")
