import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import datetime
import io
import difflib

def turkce_buyuk_harf(metin):
    if not isinstance(metin, str): return ""
    return metin.replace("i", "İ").replace("ı", "I").upper()

def sahip_eslesiyor_mu(csv_sahip, web_sahip):
    c_clean = turkce_buyuk_harf(str(csv_sahip)).replace(".", " ").replace(",", " ").strip()
    w_clean = turkce_buyuk_harf(str(web_sahip)).replace(".", " ").replace(",", " ").strip()
    
    c_clean = " ".join(c_clean.split())
    w_clean = " ".join(w_clean.split())
    
    if c_clean == w_clean: return True
    if c_clean in w_clean or w_clean in c_clean: return True
        
    c_kelimeler = c_clean.split()
    w_kelimeler = w_clean.split()
    
    ortak_kelimeler = set(c_kelimeler).intersection(set(w_kelimeler))
    min_kelime = min(len(c_kelimeler), len(w_kelimeler))
    
    if min_kelime > 0 and len(ortak_kelimeler) >= min_kelime: return True
    if difflib.SequenceMatcher(None, c_clean, w_clean).ratio() > 0.85: return True
        
    return False

# --- BULUT (LINUX) UYUMLU HEADLESS AYARLARI ---
def get_driver():
    options = Options()
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox') 
    options.add_argument('--disable-dev-shm-usage') 
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # Streamlit Cloud'daki gömülü Chromium ve Driver yolları
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    
    return webdriver.Chrome(service=service, options=options)

def tjk_verilerini_cek(driver, tarih, hipodrom, durum_metni):
    at_listesi = []
    driver.get("https://www.tjk.org/TR/yarissever/Info/Page/GunlukYarisProgrami")
    
    try:
        durum_metni.info("⏳ [TJK] Takvime tarih giriliyor ve yarışlar aranıyor...")
        tarih_kutu = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "QueryParameter_Tarih")))
        driver.execute_script(f"arguments[0].value = '{tarih}';", tarih_kutu)
        tarih_kutu.send_keys(Keys.ENTER)
        time.sleep(4) 
        
        try:
            hipodrom_sekmesi = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, hipodrom)))
            driver.execute_script("arguments[0].click();", hipodrom_sekmesi)
            time.sleep(3) 
        except:
            durum_metni.error(f"❌ DİKKAT: {tarih} tarihinde '{hipodrom}' için yarış bulunamadı.")
            return []

        durum_metni.info("⏳ [TJK] O günkü yarış tabloları analiz ediliyor ve atlar listeleniyor...")
        kosu_divleri = driver.find_elements(By.XPATH, "//div[contains(@class, 'races-panes')]/div")
        kosacak_atlar_set = set()
        
        for kosu_div in kosu_divleri:
            try:
                baslik_elementi = kosu_div.find_element(By.XPATH, ".//div[contains(@class, 'race-details')]//h3[@class='race-no']/a")
                kosu_baslik = baslik_elementi.text.strip().replace('\n', ' ')
                
                satirlar = kosu_div.find_elements(By.XPATH, ".//table[contains(@class, 'tablesorter')]/tbody/tr")
                
                for satir in satirlar:
                    try:
                        sira_no = satir.find_element(By.CLASS_NAME, "gunluk-GunlukYarisProgrami-SiraId").text.strip()
                        yas_bilgisi = satir.find_element(By.CLASS_NAME, "gunluk-GunlukYarisProgrami-Yas").text.strip()
                        sahip_ismi = satir.find_element(By.CLASS_NAME, "gunluk-GunlukYarisProgrami-SahipAdi").text.strip()
                        
                        at_isim_hucresi = satir.find_element(By.CLASS_NAME, "gunluk-GunlukYarisProgrami-AtAdi")
                        at_ismi_linki = at_isim_hucresi.find_element(By.TAG_NAME, "a")
                        at_ismi = at_ismi_linki.text.strip().split("\n")[0] 
                        
                        if at_ismi and at_ismi not in kosacak_atlar_set:
                            kosacak_atlar_set.add(at_ismi)
                            at_listesi.append({
                                "kosu_baslik": kosu_baslik,
                                "n_no": sira_no,
                                "at_ismi": at_ismi,
                                "yas": yas_bilgisi,
                                "sahip": sahip_ismi
                            })
                    except:
                        continue 
            except:
                continue
        return at_listesi
    except Exception as e:
        durum_metni.error(f"❌ TJK sitesine bağlanılamadı: {e}")
        return []

def cip_numarasi_getir(driver, at_ismi, sahip_ismi, deneme=1):
    try:
        arama_kutusu = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "txtAdCip")))
        driver.execute_script("arguments[0].value = '';", arama_kutusu) 
        time.sleep(0.2)
        arama_kutusu.send_keys(at_ismi)
        time.sleep(0.2)
        arama_kutusu.send_keys(Keys.ENTER)
        time.sleep(0.5) 
        
        arama_butonu = driver.find_element(By.ID, "btnIslem")
        driver.execute_script("arguments[0].click();", arama_butonu)
        
        time.sleep(0.5)
        WebDriverWait(driver, 15).until(EC.invisibility_of_element_located((By.CLASS_NAME, "se-pre-con")))
        time.sleep(2) 
        
        satirlar = driver.find_elements(By.XPATH, "//table[@id='DtTpSonuclar']/tbody/tr")
        if len(satirlar) == 0: return "Sonuç Bulunamadı"
        
        if len(satirlar) == 1:
            hucreler = satirlar[0].find_elements(By.TAG_NAME, "td")
            if len(hucreler) >= 10:
                sitedeki_cip = str(hucreler[2].text).strip()
                return sitedeki_cip if sitedeki_cip else "Çip Sitede Boş"
            return "Sonuç Bulunamadı" 
        else:
            eslesen_cipler = []
            eslesen_boslar = False
            for satir in satirlar:
                hucreler = satir.find_elements(By.TAG_NAME, "td")
                if len(hucreler) >= 10: 
                    sitedeki_cip = str(hucreler[2].text).strip()   
                    sitedeki_sahip = str(hucreler[9].text).strip() 
                    if sahip_eslesiyor_mu(sahip_ismi, sitedeki_sahip):
                        if sitedeki_cip: eslesen_cipler.append(sitedeki_cip)
                        else: eslesen_boslar = True
                            
            if len(eslesen_cipler) > 0: return eslesen_cipler[0]
            elif eslesen_boslar: return "Çip Sitede Boş"
            
            alternatif_cipler = []
            for satir in satirlar:
                hucreler = satir.find_elements(By.TAG_NAME, "td")
                if len(hucreler) >= 10:
                    s_at = turkce_buyuk_harf(hucreler[1].text).strip()
                    s_cip = str(hucreler[2].text).strip()
                    if s_at == turkce_buyuk_harf(at_ismi).strip() and s_cip:
                        alternatif_cipler.append(s_cip)
            
            if len(alternatif_cipler) == 1: return alternatif_cipler[0]
            return "Eşleşme Bulunamadı (Çoklu Sonuç)"
            
    except Exception as e:
        if deneme == 1:
            driver.get("https://modul.ykk.gov.tr/AtSorgulama")
            time.sleep(2)
            return cip_numarasi_getir(driver, at_ismi, sahip_ismi, deneme=2)
        else:
            return "Sorgu Hatası"

# --- STREAMLIT WEB ARAYÜZÜ ---
st.set_page_config(page_title="YKK & TJK Otonom Bot", page_icon="🏇🏿", layout="centered")

st.title("🏇🏿 Otonom Yarış Programı Çip Bulucu", layout="centered")
st.markdown("Bu sistem **TJK** yarış programını tarar ve **YKK** üzerinden çip numaralarını bularak hazır bir Excel raporu oluşturur.")

st.divider()

col1, col2, col3 = st.columns(3)
bugun = datetime.date.today()

with col1:
    sec_gun = st.selectbox("Gün", [str(i).zfill(2) for i in range(1, 32)], index=bugun.day-1)
with col2:
    sec_ay = st.selectbox("Ay", [str(i).zfill(2) for i in range(1, 13)], index=bugun.month-1)
with col3:
    sec_yil = st.selectbox("Yıl", [str(i) for i in range(2024, 2030)], index=[str(i) for i in range(2024, 2030)].index(str(bugun.year)))

hipodromlar = ["Adana", "Ankara", "Antalya", "Bursa", "Diyarbakır", "Elazığ", "İstanbul", "İzmir", "Kocaeli", "Şanlıurfa", "Karma"]
sec_hipodrom = st.selectbox("Hipodrom Seçin", hipodromlar, index=8) 

st.write("") 

if st.button("☁ BULUTTA SORGULAMAYI BAŞLAT", use_container_width=True, type="primary"):
    tarih_str = f"{sec_gun}/{sec_ay}/{sec_yil}"
    
    durum_metni = st.empty()
    ilerleme_cubugu = st.empty()
    
    try:
        driver = get_driver()
        
        at_listesi = tjk_verilerini_cek(driver, tarih_str, sec_hipodrom, durum_metni)
        
        if not at_listesi:
            durum_metni.error("TJK'dan at listesi alınamadı. O gün yarış olmayabilir.")
            driver.quit()
            st.stop()
            
        durum_metni.success(f"✅ TJK'dan {len(at_listesi)} at başarıyla çekildi. YKK Çip modülüne bağlanılıyor...")
        
        driver.get("https://modul.ykk.gov.tr/AtSorgulama")
        time.sleep(2)
        
        sonuclar = []
        toplam_at = len(at_listesi)
        
        for i, at in enumerate(at_listesi, 1):
            at_ismi = at["at_ismi"]
            sahip = at["sahip"]
            
            yuzde = int((i / toplam_at) * 100)
            ilerleme_metni = f"İlerleme: %{yuzde} | {at_ismi} sorgulanıyor... ({i}/{toplam_at})"
            
            ilerleme_cubugu.progress(i / toplam_at, text=ilerleme_metni)
            
            cip = cip_numarasi_getir(driver, at_ismi, sahip)
            
            sonuclar.append({
                "kosu_baslik": at["kosu_baslik"],
                "n_no": at["n_no"],
                "at_ismi": at_ismi,
                "yas": at["yas"],
                "cip": cip
            })

        driver.quit()
        
        ilerleme_cubugu.progress(1.0, text="✅ Tüm sorgulamalar tamamlandı! Excel dosyası hazırlanıyor...")
        durum_metni.empty() 

        excel_satirlari = []
        mevcut_kosu = ""
        for at in sonuclar:
            if at["kosu_baslik"] != mevcut_kosu:
                if mevcut_kosu != "":
                    excel_satirlari.append(["", "", "", ""]) 
                mevcut_kosu = at["kosu_baslik"]
                excel_satirlari.append([mevcut_kosu, "", "", ""]) 
                excel_satirlari.append(["N", "At İsmi", "Yaş", "Çip Bilgisi"]) 
            excel_satirlari.append([at["n_no"], at["at_ismi"], at["yas"], at["cip"]])

        df = pd.DataFrame(excel_satirlari)
        
        output = io.BytesIO()
        df.to_excel(output, index=False, header=False, engine='openpyxl')
        output.seek(0)
        
        dosya_adi = f"Yaris_Programi_{tarih_str.replace('/','-')}_{sec_hipodrom}.xlsx"
        
        st.balloons()
        st.success("🎉 Raporunuz başarıyla hazırlandı! Aşağıdaki butona tıklayarak indirebilirsiniz.")
        
        st.download_button(
            label="📥 EXCEL DOSYASINI İNDİR",
            data=output,
            file_name=dosya_adi,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    except Exception as e:
        durum_metni.error(f"Sistemsel bir hata oluştu: {e}")
        try: driver.quit()
        except: pass
