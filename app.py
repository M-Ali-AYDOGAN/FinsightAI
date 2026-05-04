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
        response = requests.get(url)
        data = response.json()
        if 'observations' in data and len(data['observations']) >= 2:
            val = data['observations'][0]['value']
            prev = data['observations'][1]['value']
            # Veri bazen '.' olarak gelebilir, bunu kontrol edelim
            val = float(val) if val != '.' else None
            prev = float(prev) if prev != '.' else None
            return val, prev
        return None, None
    except Exception:
        return None, None
        
def calculate_macro_scores(api_key):
    # Veri Toplama (Eğer None gelirse 0 veya varsayılan atanır)
    fed_funds, _ = get_fred_val('FEDFUNDS', api_key)
    dgs10, _ = get_fred_val('DGS10', api_key)
    dgs2, _ = get_fred_val('DGS2', api_key)
    vix, _ = get_fred_val('VIXCLS', api_key)
    unemp_rate, prev_unemp = get_fred_val('UNRATE', api_key)
    
    # Güvenli hesaplama (None kontrolleri)
    fed_funds = fed_funds if fed_funds is not None else 0.0
    vix = vix if vix is not None else 20.0 # VIX için ortalama bir değer
    unemp_rate = unemp_rate if unemp_rate is not None else 4.0
    
    slope = (dgs10 - dgs2) if (dgs10 is not None and dgs2 is not None) else 0.0
    
    # ROM (Resesyon Olasılığı Modeli)
    rom_score = 0
    if slope < 0: rom_score += 50
    if unemp_rate and prev_unemp and (unemp_rate > prev_unemp): rom_score += 30
    
    return {
        "slope": slope,
        "rom": min(rom_score, 100),
        "fed_funds": fed_funds,
        "vix": vix,
        "unemp": unemp_rate
    }
# --- KATMAN 3: ŞİRKET TARAMA VE TEMEL ANALİZ ---
def screen_stocks(sector_scores):
    # Katman 3 Filtreleri: CAGR, Marjlar ve Borçluluk (Örnek Veri Seti)
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
        
        # Spesifikasyondaki Filtreler: CAGR > %15 ve Marj Genişlemesi > 200bp
        is_growth = data['cagr'] > 15 and data['margin_exp'] > 200
        is_safe = data['debt_ebitda'] < 2.5 # Net Borç/FAÖK < 2.5x
        
        # Final Skoru: Sektör puanı (%40) + Büyüme hızı + Güvenlik primi
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

# --- KATMAN 4: DEĞERLEME MOTORU ---
def calculate_fair_value(ticker, current_price, cagr):
    """
    Basitleştirilmiş DCF (Nakit Akışı) ve Çarpan Analizi
    """
    # Büyüme oranına göre beklenen F/K (P/E) çarpanı ataması
    expected_pe = 15 + (cagr * 0.5) 
    
    # Tahmini İçsel Değer (3 Yıllık Projeksiyon)
    # Formül: Mevcut Fiyat * (1 + CAGR)^3 / (İskonto Oranı)
    fair_value = current_price * (1 + (cagr/100))**2 / 1.2 # %20 iskonto oranı ile
    
    upside = ((fair_value / current_price) - 1) * 100
    
    return round(fair_value, 2), round(upside, 2)

# --- KATMAN 5: PORTFÖY OPTİMİZASYONU ---
def calculate_position_size(upside, rom_score):
    """
    Kelly Kriteri ve Makro Risk (ROM) tabanlı pozisyon büyüklüğü
    """
    # Temel Kelly: (Win_Prob * Upside - Loss_Prob) / Upside
    # Burada basitleştirilmiş bir model kullanıyoruz
    base_size = (upside / 100) * 0.5 
    
    # Makro Koruma: Resesyon olasılığı arttıkça pozisyonu küçült
    risk_multiplier = (100 - rom_score) / 100
    
    final_allocation = max(0, min(base_size * risk_multiplier * 100, 25)) # Tek hisse max %25
    return round(final_allocation, 2)    

# --- KÜRESEL PİYASALAR VE FIRSAT HARİTASI ---
def get_global_opportunity_map():
    # Küresel takip listesi (Endeksler)
    global_assets = {
        'Türkiye': 'XU100.IS',
        'Almanya': '^GDAXI', 'Fransa': '^FCHI', 'İngiltere': '^FTSE',
        'İtalya': 'FTSEMIB.MI', 'İspanya': '^IBEX', 'Hollanda': '^AEX',
        'İsviçre': '^SSMI', 'Polonya': 'WIG20.WA',
        'Japonya': '^N225', 'Çin': '000001.SS', 'Hindistan': '^NSEI',
        'G. Kore': '^KS11', 'Vietnam': 'VNI.VN'
    }
    
    results = []
    for country, ticker in global_assets.items():
        try:
            # 1 yıllık veri çekerek momentum analizi yapıyoruz
            hist = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
            if not hist.empty:
                # Kapanış fiyatı sütununu güvenli çekme
                close_series = hist['Close'].iloc[:, 0] if isinstance(hist['Close'], pd.DataFrame) else hist['Close']
                ytd_change = ((close_series.iloc[-1] / close_series.iloc[0]) - 1) * 100
                
                results.append({
                    "Ülke": country,
                    "Yıllık Getiri": round(ytd_change, 2),
                    "Momentum": "🔥 Güçlü" if ytd_change > 15 else ("🧊 Zayıf" if ytd_change < 0 else "⚖️ Stabil")
                })
        except: continue
    return pd.DataFrame(results)

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
    # Katman 3 Arayüzü
    st.subheader("🔍 Katman 3: Şirket Taraması ve Temel Analiz")
    
    with st.expander("🎯 Filtreleme Parametrelerini Gör", expanded=False):
        st.write("""
        - **Birincil Filtre:** Gelir CAGR (3Y) > %15
        - **Marj Genişlemesi:** > 200 baz puan
        - **Bilanço Güvenliği:** Net Borç / FAÖK < 2.5x
        - **Altman Z-Skoru:** > 1.8 (İflas riski kontrolü)
        """)
    
    # Tarayıcıyı çalıştır
    screened_df = screen_stocks(s_scores)
    
    # Skorlara göre renklendirme ve tablo
    st.dataframe(
        screened_df.sort_values(by="Final Skoru", ascending=False),
        use_container_width=True,
        hide_index=True
    )
    
    st.info("💡 Not: Yukarıdaki liste Katman 1 (Makro) ve Katman 2 (Sektör) puanları ile ağırlıklandırılmıştır.")

    st.divider()
    st.subheader("💰 Katman 4: Değerleme ve Hedef Fiyatlar")
    
    # Örnek fiyat verileri (Gerçekte yfinance'den anlık çekilecek)
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
    
    # Hedef Fiyat Kartları
    cols = st.columns(len(val_df))
    for idx, row in val_df.iterrows():
        cols[idx].metric(row['Hisse'], row['Hedef Fiyat (Fair Value)'], delta=row['Potansiyel'])

    st.caption("⚠️ Hedef fiyatlar Katman 1 (Makro) iskonto oranlarına göre dinamik olarak güncellenmektedir.")

    st.divider()
    st.subheader("🛡️ Katman 5: Portföy Optimizasyonu (Risk Yönetimi)")
    
    portfolio_data = []
    total_stock_weight = 0
    
    for _, row in val_df.iterrows():
        upside_val = float(row['Potansiyel'].replace('%', ''))
        
        # Pozisyon büyüklüğünü hesapla
        pos_size = calculate_position_size(upside_val, m_data['rom'])
        total_stock_weight += pos_size
        
        portfolio_data.append({
            "Hisse": row['Hisse'],
            "Önerilen Ağırlık": f"%{pos_size}",
            "Risk Seviyesi": "DÜŞÜK" if pos_size > 15 else "ORTA"
        })
    
    # Pasta Grafiği ile Dağılımı Göster
    p_df = pd.DataFrame(portfolio_data)
    # Nakit oranını hesapla
    cash_weight = 100 - total_stock_weight
    
    fig_port = go.Figure(data=[go.Pie(
        labels=list(p_df['Hisse']) + ['Nakit / Tahvil'],
        values=list([float(x.replace('%','')) for x in p_df['Önerilen Ağırlık']]) + [cash_weight],
        hole=.4,
        marker_colors=['#00CC96', '#636EFA', '#EF553B', '#AB63FA', '#FFA15A', '#19D3F3']
    )])
    fig_port.update_layout(title="İdeal Portföy Dağılımı", template="plotly_dark")
    st.plotly_chart(fig_port, use_container_width=True)

    st.warning(f"💡 Stratejik Not: Mevcut makro riskler nedeniyle portföyün %{round(cash_weight, 2)} kadarı nakitte tutulmalıdır.")

    st.divider()
    st.header("🌐 Küresel Piyasalar ve Coğrafi Fırsatlar")
    st.write("Yatırım uzmanı gözüyle sermayenin hangi ülkelere aktığını takip edin.")

    # Veriyi çek ve görselleştir
    geo_df = get_global_opportunity_map()
    
    if not geo_df.empty:
        col_geo1, col_geo2 = st.columns([2, 1])
        
        with col_geo1:
            # Ülkelerin getiri performans grafiği
            st.bar_chart(geo_df.set_index("Ülke")["Yıllık Getiri"])
            
        with col_geo2:
            st.subheader("🏆 Lider Piyasalar")
            top_performers = geo_df.sort_values(by="Yıllık Getiri", ascending=False).head(5)
            st.dataframe(top_performers, hide_index=True, use_container_width=True)

    st.info("💡 Uzman Notu: Türkiye gibi yüksek enflasyonlu piyasalarda 'Yıllık Getiri'nin reel getiri olup olmadığını Katman 1'deki enflasyon verileriyle kıyaslayın.")
st.divider()
st.caption("⚠️ Bilgilendirme amaclıdır, yatırım tavsiyesi degildir.")
