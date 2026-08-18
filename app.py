import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import traceback

from database_setup import veritabani_kur
from scraper import tjk_veri_cek
from feature_engineering import verileri_hazirla
from model_motoru import modeli_egit
from kupon_motoru import optimum_kupon

st.set_page_config(page_title="TJK Yapay Zeka Botu", page_icon="🐎", layout="wide")

st.title("🐎 TJK Yapay Zeka & Optimizasyon Merkezi")
st.markdown("Veri bilimi ve makine öğrenmesi destekli profesyonel altılı ganyan tahmin motoru.")

tab_kontrol, tab_analiz, tab_gecmis = st.tabs(["⚙️ Kontrol Paneli", "📊 Olasılık Analizi", "📜 Kupon Geçmişi"])

# --- TAB 1: KONTROL PANELİ ---
with tab_kontrol:
    with st.form("kontrol_formu"):
        col1, col2 = st.columns(2)
        
        with col1:
            tarih = st.date_input("Bülten Tarihi", datetime.today())
            hipodrom = st.selectbox("Hipodrom", ["Adana", "Ankara", "Antalya", "Bursa", "Diyarbakır", "Elazığ", "İstanbul", "İzmir", "Kocaeli", "Şanlıurfa"])
            model_tipi = st.selectbox("Yapay Zeka Motoru", ["XGBoost (Agresif ve Detaycı)", "Random Forest (Dengeli ve Çoğulcu)"])
        
        with col2:
            butce = st.number_input("Maksimum Bütçe (TL)", min_value=10, max_value=50000, value=300, step=50)
            risk = st.selectbox("Risk Profili", ["Güvenli (Favoriler)", "Dengeli", "Sürpriz Arayan (Bomba)"], index=1)
            
            varsayilan_fiyat = 1.00 if hipodrom in ["Elazığ", "Diyarbakır", "Şanlıurfa"] else 1.25
            birim_fiyat = st.number_input("Birim Fiyat (TL)", min_value=0.10, max_value=10.0, value=varsayilan_fiyat, step=0.05)

        baslat = st.form_submit_button("🚀 Motoru Başlat ve Şablon Üret", use_container_width=True)

    if baslat:
        durum_metni = st.empty()
        # 🚨 YENİ: İçi metin dolu ilerleme çubuğu
        ilerleme_cubugu = st.progress(0, text="%0 - Sistem Başlatılıyor...")
        
        # 🚨 YENİ: Callback (Geri Çağırım) Fonksiyonumuz
        def anlik_ilerleme(yuzde, mesaj):
            guvenli_yuzde = max(0, min(100, int(yuzde))) # Yüzdeyi 0-100 arasında sabitler
            ilerleme_cubugu.progress(guvenli_yuzde, text=f"%{guvenli_yuzde} - {mesaj}")
            durum_metni.info(mesaj)
        
        try:
            tarih_str = tarih.strftime("%Y-%m-%d")
            
            anlik_ilerleme(5, "Veritabanı bağlantıları kontrol ediliyor...")
            veritabani_kur()
            
            # TJK Veri Çekme Motoruna "anlik_ilerleme" fonksiyonumuzu gönderiyoruz!
            tjk_veri_cek(tarih_str, hipodrom, anlik_ilerleme)
            
            anlik_ilerleme(72, "Veritabanından geçmiş koşular okunuyor ve JOKEY ZEKASI hesaba katılıyor...")
            X, y = verileri_hazirla()
            
            if X is None or X.empty:
                st.error("❌ Model eğitimi için havuzda yeterli veri bulunamadı.")
                st.stop()
                
            anlik_ilerleme(75, f"Yapay Zeka ({model_tipi}) 14 Boyutlu Matris Üzerinden Öğreniyor...")
            yz_model = modeli_egit(X, y, model_tipi)
            
            anlik_ilerleme(85, "Bugünkü koşular analiz ediliyor...")
            
            conn = sqlite3.connect("tjk_arastirma_merkezi.db")
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT yaris_id FROM Sonuclar WHERE yaris_id LIKE ?", (f"{tarih_str}_{hipodrom}%",))
            kosular = cursor.fetchall()
            
            if len(kosular) < 6:
                st.error(f"❌ HATA: {tarih_str} tarihinde '{hipodrom}' hipodromu için 6 ayaklı yarış bülteni tam olarak bulunamadı.")
                conn.close()
                st.stop()
            
            gercek_olasiliklar = []
            for index, kosu in enumerate(kosular[:6]):
                # Her ayak analiz edildiğinde barı biraz daha doldur
                anlik_ilerleme(85 + int((index/6)*10), f"Yapay Zeka {index+1}. Ayağı süzgeçten geçiriyor...")
                
                yaris_id = kosu[0]
                cursor.execute("SELECT DISTINCT at_adi, kilo, hp, jokey FROM Sonuclar WHERE yaris_id = ?", (yaris_id,))
                atlar = cursor.fetchall()
                
                tum_kilolar = [float(a[1]) for a in atlar if a[1] is not None]
                tum_hpler = [float(a[2]) for a in atlar if a[2] is not None]
                ort_kilo_ayak = sum(tum_kilolar)/len(tum_kilolar) if tum_kilolar else 56.0
                max_hp_ayak = max(tum_hpler) if tum_hpler else 40.0
                
                ayak_listesi = []
                for t_at in atlar:
                    at_adi = t_at[0]
                    b_kilo = float(t_at[1]) if t_at[1] is not None else 56.0
                    b_hp = float(t_at[2]) if t_at[2] is not None else 40.0
                    b_jokey = t_at[3] if len(t_at) > 3 else "Bilinmiyor"
                    
                    kilo_fark = b_kilo - ort_kilo_ayak
                    hp_fark = max_hp_ayak - b_hp
                    
                    cursor.execute("""
                        SELECT genel_kazanma_orani, toplam_kosu, son_3_derece_ort, dinlenme_gunu, 
                               ort_hiz, max_hiz, kum_kazanma, cim_kazanma, sentetik_kazanma, son_1_ay_idman_sayisi 
                        FROM Ozet_At_Istatistik WHERE at_adi=?
                    """, (at_adi,))
                    at_ist = cursor.fetchone()
                    
                    at_kaz_oran = at_ist[0] if at_ist else 0.0
                    at_kosu_say = at_ist[1] if at_ist else 0.0
                    son_3_ort = at_ist[2] if at_ist else 99.0
                    dinlenme = at_ist[3] if at_ist else 30.0
                    ort_hiz = at_ist[4] if at_ist else 15.0
                    max_hiz = at_ist[5] if at_ist else 15.0
                    kum_kaz = at_ist[6] if at_ist else 0.0
                    cim_kaz = at_ist[7] if at_ist else 0.0
                    sentetik_kaz = at_ist[8] if at_ist else 0.0
                    idman_sayisi = at_ist[9] if at_ist else 0.0
                    
                    cursor.execute("SELECT jokey_kazanma_orani FROM Ozet_Jokey_Istatistik WHERE jokey=?", (b_jokey,))
                    j_ist = cursor.fetchone()
                    jokey_kaz_oran = float(j_ist[0]) if j_ist else 0.05 
                    
                    X_bugun = pd.DataFrame(
                        [[1200, at_kaz_oran, at_kosu_say, son_3_ort, dinlenme, kilo_fark, hp_fark, ort_hiz, max_hiz, kum_kaz, cim_kaz, sentetik_kaz, idman_sayisi, jokey_kaz_oran]], 
                        columns=['mesafe', 'genel_kazanma_orani', 'toplam_kosu', 'son_3_derece_ort', 'dinlenme_gunu', 'kilo_farki', 'hp_farki', 'ort_hiz', 'max_hiz', 'kum_kazanma', 'cim_kazanma', 'sentetik_kazanma', 'son_1_ay_idman_sayisi', 'jokey_kazanma_orani']
                    )
                    
                    ham_olasilik = yz_model.predict_proba(X_bugun)[0][1]
                    if ham_olasilik == 0: ham_olasilik = 0.01 
                        
                    if dinlenme > 120: ham_olasilik *= 0.30 
                    elif dinlenme > 60 and idman_sayisi < 3: ham_olasilik *= 0.50
                    elif dinlenme < 7: ham_olasilik *= 0.70
                        
                    ayak_listesi.append({"at": at_adi, "olasilik": ham_olasilik, "ganyan": 0.0})
                    
                toplam_olasilik = sum(at['olasilik'] for at in ayak_listesi)
                if toplam_olasilik == 0: toplam_olasilik = 1.0 
                    
                for at in ayak_listesi:
                    at['olasilik'] = at['olasilik'] / toplam_olasilik
                    at['ganyan'] = (1.0 / at['olasilik']) * 0.75 if at['olasilik'] > 0 else 80.0
                    if at['ganyan'] > 80.0: at['ganyan'] = 80.0
                
                ayak_listesi = sorted(ayak_listesi, key=lambda x: x['olasilik'], reverse=True)
                gercek_olasiliklar.append(ayak_listesi)
            
            conn.close()
            st.session_state['son_analiz'] = gercek_olasiliklar
            st.session_state['son_model_adi'] = model_tipi.split(" (")[0]

            anlik_ilerleme(96, "Bütçe ve Risk Profiline göre şablon kombinasyonu optimize ediliyor...")
            
            kupon, maliyet = optimum_kupon(gercek_olasiliklar, butce, risk, birim_fiyat)
            
            anlik_ilerleme(100, "✅ Şablon Başarıyla Üretildi!")
            durum_metni.success("✅ Şablon Başarıyla Üretildi!")
            
            st.subheader(f"🎯 2. ALTILI GANYAN ŞABLONU ({st.session_state['son_model_adi']})")
            st.write(f"**Hesaplanan Maliyet:** {maliyet:.2f} TL (Birim Fiyat: {birim_fiyat} TL)")
            
            kupon_metni_satirlar = []
            for i, ayak in enumerate(kupon):
                satir = f"**{i+1}. Ayak:** {', '.join([at['at'] for at in ayak])}"
                st.markdown(satir)
                kupon_metni_satirlar.append(f"{i+1}. Ayak: {', '.join([at['at'] for at in ayak])}")
            
            try:
                conn2 = sqlite3.connect("tjk_arastirma_merkezi.db")
                cur2 = conn2.cursor()
                cur2.execute("""
                    CREATE TABLE IF NOT EXISTS Kupon_Gecmisi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        olusturulma_zamani TEXT, bulten_tarihi TEXT, hipodrom TEXT,
                        maliyet REAL, risk_profili TEXT, kupon_detayi TEXT
                    )
                """)
                tam_zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                kupon_full_metin = "\n".join(kupon_metni_satirlar)
                genisletilmis_risk = f"[{st.session_state['son_model_adi']}] {risk} ({birim_fiyat}₺)"
                
                cur2.execute("""
                    INSERT INTO Kupon_Gecmisi 
                    (olusturulma_zamani, bulten_tarihi, hipodrom, maliyet, risk_profili, kupon_detayi)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (tam_zaman, tarih_str, hipodrom, maliyet, genisletilmis_risk, kupon_full_metin))
                
                conn2.commit()
                conn2.close()
                st.success("💾 Kupon başarıyla veritabanına kaydedildi! 'Kupon Geçmişi' sekmesinden inceleyebilirsiniz.")
            except Exception as e:
                st.warning(f"⚠️ Kupon kaydedilirken bir hata oluştu: {str(e)}")
            
        except Exception as e:
            hata_detayi = traceback.format_exc()
            st.error(f"❌ SİSTEM ÇÖKTÜ: {hata_detayi}")

# --- TAB 2: OLASILIK ANALİZİ ---
with tab_analiz:
    if 'son_analiz' in st.session_state:
        st.subheader(f"🐎 14 Boyutlu Yapay Zeka Raporu ({st.session_state['son_model_adi']})")
        for i, ayak in enumerate(st.session_state['son_analiz']):
            st.markdown(f"#### {i+1}. AYAK")
            df = pd.DataFrame(ayak)
            df['olasilik'] = (df['olasilik'] * 100).round(2).astype(str) + " %"
            df['ganyan'] = df['ganyan'].round(2)
            df.columns = ["At Adı", "Y.Z. Güç Endeksi", "Beklenen Ganyan"]
            df.index = df.index + 1
            st.dataframe(df, use_container_width=True)
    else:
        st.info("Sistem analiz için emrinizi bekliyor...")

# --- TAB 3: KUPON GEÇMİŞİ ---
with tab_gecmis:
    if st.button("🔄 Geçmişi Yenile"):
        st.rerun()
        
    try:
        conn = sqlite3.connect("tjk_arastirma_merkezi.db")
        df_gecmis = pd.read_sql_query("SELECT olusturulma_zamani, bulten_tarihi, hipodrom, maliyet, risk_profili, kupon_detayi FROM Kupon_Gecmisi ORDER BY id DESC", conn)
        conn.close()
        
        if not df_gecmis.empty:
            for index, row in df_gecmis.iterrows():
                with st.expander(f"📍 {row['hipodrom'].upper()} ({row['bulten_tarihi']}) - Maliyet: {row['maliyet']:.2f} TL"):
                    st.write(f"**Üretim Saati:** {row['olusturulma_zamani']}")
                    st.write(f"**Risk Profili:** {row['risk_profili']}")
                    st.text(row['kupon_detayi'])
        else:
            st.info("Henüz kaydedilmiş bir kupon bulunmuyor.")
    except Exception as e:
        st.info("Henüz geçmiş tablosu oluşturulmadı.")
