import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import requests

# ========== SIFRE KORUMASI ==========
st.set_page_config(page_title="FinsightAI", page_icon="🔒", layout="wide")

if "sifre_dogrulandi" not in st.session_state:
    st.session_state.sifre_dogrulandi = False

if not st.session_state.sifre_dogrulandi:
    st.title("🔒 FinsightAI")
    st.write("Lutfen sifrenizi girin:")
    
    sifre = st.text_input("Sifre", type="password")
    
    if st.button("Giris"):
        if sifre == "Finan@12345":
            st.session_state.sifre_dogrulandi = True
            st.rerun()
        else:
            st.error("❌ Yanlis sifre!")
    
    st.stop()

# ========== ASIL UYGULAMA ==========
st.title("📊 Kisisel Finans AI")
st.caption(f"Son guncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# API anahtarlari
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
except:
    FRED_API_KEY = "9d3135bcfce4a8a3af3ccc3488a94a12"
    NEWS_API_KEY = "361bdcc09ce647f2b47d22addbec35c"

tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektorler"])

with tab1:
    st.header("🌍 Kuresel Makro Gostergeler")
    
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
    
    st.subheader("📉 Getiri Egrisi")
    
    @st.cache_data(ttl=21600)
    def get_yield_curve():
        try:
            url_10y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            url_2y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=100"
            
            r10 = requests.get(url_10y).json()
            r2 = requests.get(url_2y).json()
            
            if 'observations' not in r10 or 'observations' not in r2:
                return None, 0
            
            dates_10y = [obs['date'] for obs in r10['observations'] if obs['value'] != '.']
            values_10y = [float(obs['value']) for obs in r10['observations'] if obs['value'] != '.']
            
            dates_2y = [obs['date'] for obs in r2['observations'] if obs['value'] != '.']
            values_2y = [float(obs['value']) for obs in r2['observations'] if obs['value'] != '.']
            
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
            
            neg_dates = [d for d, s in zip(common_dates, spreads) if s < 0]
            neg_vals = [s for s in spreads if s < 0]
            if neg_vals:
                fig.add_trace(go.Scatter(x=neg_dates, y=neg_vals,
                                        mode='markers', name='Tersine Donme',
                                        marker=dict(color='red', size=6)))
            
            fig.update_layout(height=400, xaxis_title="Tarih", yaxis_title="%")
            return fig, spreads[0]
        except:
            return None, 0
    
    fig_yield, son_spread = get_yield_curve()
    if fig_yield:
        st.plotly_chart(fig_yield, use_container_width=True)
        if son_spread < 0:
            st.error(f"⚠️ GETIRI EGRISI TERSINE DONDU: {son_spread:.2f}% — Resesyon riski!")
        else:
            st.success(f"✅ Getiri egrisi normal: {son_spread:.2f}%")

with tab2:
    st.header("📰 Ekonomi Haberleri")
    
    st.write(f"NewsAPI key uzunlugu: {len(NEWS_API_KEY)}")
    
    @st.cache_data(ttl=3600)
    def get_news():
        try:
            url = f"https://newsapi.org/v2/everything?q=economy+finance&language=en&sortBy=publishedAt&pageSize=5&apiKey={NEWS_API_KEY}"
            response = requests.get(url, timeout=10)
            st.write(f"API status: {response.status_code}")
            
            if response.status_code == 200:
                haberler = response.json()
                st.write(f"API status: {haberler.get('status')}")
                return haberler.get('articles', [])
            else:
                st.error(f"API hatasi: {response.status_code}")
                return []
        except Exception as e:
            st.error(f"Hata: {str(e)}")
            return []
    
    haberler = get_news()
    st.write(f"Haber sayisi: {len(haberler)}")
    
    if haberler:
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
    else:
        st.warning("Haber bulunamadi.")

with tab3:
    st.header("🏭 Sektor Rotasyonu")
    
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
                st.write(f"Deneniyor: {isim}")
                data = yf.download(sembol, period="6mo", progress=False)
                st.write(f"Veri boyutu: {len(data)}")
                
                if not data.empty and len(data) > 1:
                    ilk = float(data['Close'].iloc[0])
                    son = float(data['Close'].iloc[-1])
                    getiri = (son / ilk - 1) * 100
                    sonuclar[isim] = getiri
                    st.write(f"✅ {isim}: %{getiri:.1f}")
            except Exception as e:
                st.write(f"❌ Hata {isim}: {str(e)}")
                continue
        
        return sonuclar
    
    momentum = get_sector_momentum()
    st.write(f"Sektor sayisi: {len(momentum)}")
    
    if momentum:
        sirali = dict(sorted(momentum.items(), key=lambda x: float(x[1]), reverse=True))
        
        col1, col2 = st.columns(2)
        with col1:
            en_iyi = list(sirali.keys())[0]
            en_iyi_deger = float(list(sirali.values())[0])
            st.success(f"🏆 En Iyi: {en_iyi} (+{en_iyi_deger:.1f}%)")
        with col2:
            en_kotu = list(sirali.keys())[-1]
            en_kotu_deger = float(list(sirali.values())[-1])
            st.error(f"⚠️ En Kotu: {en_kotu} ({en_kotu_deger:.1f}%)")
        
        isimler = list(sirali.keys())
        degerler = [float(v) for v in sirali.values()]
        
        fig = go.Figure([go.Bar(
            x=isimler,
            y=degerler,
            marker_color=['green' if v > 0 else 'red' for v in degerler]
        )])
        fig.update_layout(height=500, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
        df_momentum = pd.DataFrame({
            'Sektor': isimler,
            '6 Aylik Getiri (%)': [f"{v:.2f}" for v in degerler]
        })
        st.dataframe(df_momentum, use_container_width=True)
    else:
        st.warning("Sektor verisi cekilemedi.")

st.divider()
st.caption("⚠️ Bu uygulama yalnizca bilgilendirme amaclidir. Yatirim tavsiyesi degildir.")
