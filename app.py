import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
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

# API anahtarlari
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
except:
    FRED_API_KEY = "9d3135bcfce4a8a3af3ccc3488a94a12"
    NEWS_API_KEY = "361bdcc09ce647f2b47d22addbbec35c"

tab1, tab2, tab3 = st.tabs(["🌍 Makro", "📰 Haberler", "🏭 Sektorler"])

# ... (Tab 1 Makro kısmı sendekiyle aynı kalabilir) ...

with tab2:
    st.header("📰 Ekonomi Haberleri")
    
    # ttl=3600 (1 saat) yerine daha taze olması için süreyi düşürdük veya cache temizledik
    @st.cache_data(ttl=1800) 
    def get_news():
        try:
            # Bugünün ve dünün tarihini alarak en güncel haberleri zorlayalım
            today = datetime.now().strftime('%Y-%m-%d')
            url = f"https://newsapi.org/v2/everything?q=economy+OR+finance+OR+stock+market&language=en&sortBy=publishedAt&from={today}&pageSize=10&apiKey={NEWS_API_KEY}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json().get('articles', [])
            return []
        except:
            return []
    
    haberler = get_news()
    if haberler:
        for haber in haberler:
            with st.container():
                col_img, col_text = st.columns([1, 4])
                with col_img:
                    if haber.get('urlToImage'):
                        st.image(haber['urlToImage'], width=150)
                with col_text:
                    st.markdown(f"**[{haber['title']}]({haber['url']})**")
                    st.caption(f"{haber['source']['name']} — {haber['publishedAt'][:16].replace('T', ' ')}")
                    st.write(haber.get('description', '')[:200] + "...")
                st.divider()
    else:
        st.warning("Bugüne ait güncel haber bulunamadı veya API limiti doldu.")

with tab3:
    st.header("🏭 Sektor Rotasyonu (6 Aylik Momentum)")
    
    @st.cache_data(ttl=21600)
    def get_sector_momentum():
        etfler = {
            'Teknoloji': 'XLK', 'Finansal': 'XLF', 'Enerji': 'XLE',
            'Saglik': 'XLV', 'Tuketim': 'XLY', 'Kamu Hizmetleri': 'XLU',
            'Hammaddeler': 'XLB', 'Sanayi': 'XLI', 'Gayrimenkul': 'XLRE',
            'Iletisim': 'XLC'
        }
        
        sonuclar = {}
        for isim, sembol in etfler.items():
            try:
                # auto_adjust=True ve group_by="column" ile veriyi sadeleştiriyoruz
                df = yf.download(sembol, period="6mo", interval="1d", progress=False, auto_adjust=True)
                
                if not df.empty and len(df) > 1:
                    # Yfinance MultiIndex hatasını çözmek için 'Close' kolonunu düzleştiriyoruz
                    close_data = df['Close']
                    
                    # Eğer hala dataframe ise (MultiIndex durumu), ilk kolonu seç
                    if isinstance(close_data, pd.DataFrame):
                        close_series = close_data.iloc[:, 0]
                    else:
                        close_series = close_data
                    
                    ilk = float(close_series.iloc[0])
                    son = float(close_series.iloc[-1])
                    
                    getiri = ((son / ilk) - 1) * 100
                    sonuclar[isim] = getiri
            except Exception as e:
                continue
        return sonuclar

    momentum = get_sector_momentum()
    
    if momentum:
        sirali = dict(sorted(momentum.items(), key=lambda x: x[1], reverse=True))
        
        fig = go.Figure([go.Bar(
            x=list(sirali.keys()),
            y=list(sirali.values()),
            marker_color=['#00CC96' if v > 0 else '#EF553B' for v in sirali.values()]
        )])
        fig.update_layout(height=500, template="plotly_dark", title="Sektörel Performans (%)")
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(pd.DataFrame(sirali.items(), columns=['Sektör', 'Getiri (%)']), use_container_width=True)
    else:
        st.error("Sektör verileri çekilemedi. Lütfen sayfayı yenileyin.")
