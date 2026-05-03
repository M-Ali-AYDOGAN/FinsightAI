import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import requests

# ========== SIFRE KORUMASI ==========
st.set_page_config(page_title="Finans AI", page_icon=":lock:", layout="wide")

if "sifre_dogrulandi" not in st.session_state:
    st.session_state.sifre_dogrulandi = False

if not st.session_state.sifre_dogrulandi:
    st.title(":lock: Finans AI")
    st.write("Lutfen sifrenizi girin:")
    
    sifre = st.text_input("Sifre", type="password")
    
    if st.button("Giris"):
        if sifre == "Finans@12345":  # KENDI SIFRENIZ
            st.session_state.sifre_dogrulandi = True
            st.rerun()
        else:
            st.error(":x: Yanlis sifre!")
    
    st.stop()

# ========== ASIL UYGULAMA ==========
st.title(":bar_chart: Kisisel Finans AI")
st.caption(f"Son guncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# API anahtarlari
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
except:
    FRED_API_KEY = "9d3135bcfce4a8a3af3ccc3488a94a12"
    NEWS_API_KEY = "361bdcc09ce647f2b47d22addbec35c"

tab1, tab2, tab3 = st.tabs([":earth_americas: Makro", ":newspaper: Haberler", ":factory: Sektorler"])

with tab1:
    st.header("Kuresel Makro Gostergeler")
    
    @st.cache_data(ttl=21600)
    def get_fred_data(series_id):
        """FRED API'den veri cek"""
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
    
    # Makro verileri
    seriler = {
        'Fed Fonlari': 'FEDFUNDS',
        '10Y Hazine': 'DGS10',
        '2Y Hazine': 'DGS2',
        'VIX': 'VIXCLS',
        'Brent Petrol': 'DCOILBRENTEU',
        'Altin': 'GOLDAMGBD228NLBM'
    }
    
    col1, col2, col3 = st.columns(3)
    i = 0
    
    for isim, kod in seriler.items():
        son, onceki = get_fred_data(kod)
        if son and onceki:
            degisim = son - onceki
            if i % 3 == 0:
                with col1:
                    st.metric(isim, f"{son:.2f}", f"{degisim:.3f}")
            elif i % 3 == 1:
                with col2:
                    st.metric(isim, f"{son:.2f}", f"{degisim:.3f}")
            else:
                with col3:
                    st.metric(isim, f"{son:.2f}", f"{degisim:.3f}")
            i += 1
    
    # Getiri Egrisi
    st.subheader(":chart_with_downwards_trend: Getiri Egrisi")
    
    @st.cache_data(ttl=21600)
    def get_yield_curve():
        try:
            url_10y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            url_2y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            
            r10 = requests.get(url_10y).json()
            r2 = requests.get(url_2y).json()
            
            if 'observations' not in r10 or 'observations' not in r2:
                return None, 0
            
            # Verileri isle
            dates_10y = [obs['date'] for obs in r10['observations'] if obs['value'] != '.']
            values_10y = [float(obs['value']) for obs in r10['observations'] if obs['value'] != '.']
            
            dates_2y = [obs['date'] for obs in r2['observations'] if obs['value'] != '.']
            values_2y = [float(obs['value']) for obs in r2['observations'] if obs['value'] != '.']
            
            # Ortak tarihler
            common_dates = []
            spreads = []
            for d10, v10 in zip(dates_10y, values_10y):
                if d10 in dates_2y:
                    idx = dates_2y.index(d10)
                    common_dates.append(d10)
                    spreads.append(v10 - values_2y[idx])
            
            if not spreads:
                return None, 0
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=common_dates, y=spreads,
                                    mode='lines', name='10Y-2Y Farki',
                                    line=dict(color='blue', width=2)))
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            
            # Negatif bolgeler
            neg_dates = [d for d, s in zip(common_dates, spreads) if s < 0]
            neg_vals = [s for s in spreads if s < 0]
            if neg_vals:
                fig.add_trace(go.Scatter(x=neg_dates, y=neg_vals,
                                        mode='markers', name='Tersine Donme',
                                        marker=dict(color='red', size=6)))
            
            fig.update_layout(height=400, xaxis_title="Tarih", yaxis_title="%")
            return fig, spreads[0]
        except Exception as e:
            st.error(f"Getiri egrisi hatasi: {str(e)}")
            return None, 0
    
    fig_yield, son_spread = get_yield_curve()
    if fig_yield:
        st.plotly_chart(fig_yield, use_container_width=True)
        if son_spread < 0:
            st.error(f":warning: GETIRI EGRISI TERSINE DONDU: {son_spread:.2f}% — Resesyon riski!")
        else:
            st.success(f":white_check_mark: Getiri egrisi normal: {son_spread:.2f}%")

with tab2:
    st.header(":newspaper: Ekonomi Haberleri")
    
    @st.cache_data(ttl=3600)
    def get_news():
        try:
            url = f"https://newsapi.org/v2/everything?q=economy+finance+fed&language=en&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}"
            response = requests.get(url)
            haberler = response.json()
            return haberler.get('articles', [])
        except:
            return []
    
    haberler = get_news()
    st.write(f"Haber sayisi: {len(haberler)}")
    for haber in haberler:
        with st.container():
            col_img, col_text = st.columns([1, 4])
            with col_img:
                if haber.get('urlToImage'):
                    st.image(haber['urlToImage'], width=120)
            with col_text:
                st.markdown(f"**[{haber['title']}]({haber['url']})**")
                st.caption(f"{haber['source']['name']} — {haber['publishedAt'][:10]}")
                st.write(haber.get('description', '')[:200] + "...")
            st.divider()

with tab3:
    st.header(":factory: Sektor Rotasyonu")
    
    @st.cache_data(ttl=21600)
    def get_sector_momentum():
        etfler = {
            'Teknoloji': 'XLK',
            'Finansal': 'XLF', 
            'Enerji': 'XLE',
            'Saglik': 'XLV',
            'Tuketim': 'XLY',
            'Kamu Hizmetleri': 'XLU',
            'Hammaddeler': 'XLB',
            'Sanayi': 'XLI',
            'Gayrimenkul': 'XLRE',
            'Iletisim': 'XLC',
            'S&P 500': 'SPY'
        }
        
        sonuclar = {}
        for isim, sembol in etfler.items():
            try:
                data = yf.download(sembol, period="6mo", progress=False)
                if not data.empty:
                 ilk_fiyat = float(data['Close'].iloc[0]) 
                 son_fiyat = float(data['Close'].iloc[-1])
                 getiri = (son_fiyat / ilk_fiyat - 1) * 100
                sonuclar[isim] = getiri
            except:
                continue
        return sonuclar
    
    momentum = get_sector_momentum()
    st.write(f"Sektor sayisi: {len(momentum)}")
    
    if momentum:
        sirali = dict(sorted(momentum.items(), key=lambda x: x[1], reverse=True))
        
        col1, col2 = st.columns(2)
        with col1:
            st.success(f":trophy: En Iyi: {list(sirali.keys())[0]} (+{list(sirali.values())[0]:.1f}%)")
        with col2:
            st.error(f":warning: En Kotu: {list(sirali.keys())[-1]} ({list(sirali.values())[-1]:.1f}%)")
        
        fig = go.Figure([go.Bar(
            x=list(sirali.keys()),
            y=list(sirali.values()),
            marker_color=['green' if v > 0 else 'red' for v in sirali.values()]
        )])
        fig.update_layout(height=500, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
        df_momentum = pd.DataFrame(list(sirali.items()), columns=['Sektor', '6 Aylik Getiri (%)'])
        st.dataframe(df_momentum, use_container_width=True)

st.divider()
st.caption(":warning: Bu uygulama yalnizca bilgilendirme amaclidir. Yatirim tavsiyesi degildir.")
