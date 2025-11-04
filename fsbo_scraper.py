#!/usr/bin/env python3
"""
OctoIQ Cloud FSBO Scraper
Sahibinden.com'dan FSBO ilanlarını otomatik çeker
Cloud Run üzerinde çalışır
"""

import os
import json
import time
import random
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

class FSBOCloudScraper:
    def __init__(self):
        self.init_firebase()
        self.db = firestore.client()
        self.scraped_count = 0
        self.error_count = 0
        
    def init_firebase(self):
        """Firebase Admin SDK başlatma"""
        try:
            # Cloud Run ortamında service account otomatik yüklenir
            if not firebase_admin._apps:
                # Eğer GOOGLE_APPLICATION_CREDENTIALS yoksa default credentials kullan
                if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
                    cred = credentials.Certificate(os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))
                    firebase_admin.initialize_app(cred)
                else:
                    # Cloud Run'da default service account
                    firebase_admin.initialize_app()
            logger.info("✅ Firebase Admin SDK başlatıldı")
        except Exception as e:
            logger.error(f"❌ Firebase init hatası: {e}")
            raise

    def get_chrome_driver(self):
        """Headless Chrome driver oluştur"""
        try:
            chrome_options = Options()
            # Temel headless ayarları
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            
            # Memory ve performance optimizasyonu
            chrome_options.add_argument("--memory-pressure-off")
            chrome_options.add_argument("--max_old_space_size=4096")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            
            # Stability artırıcı
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-javascript")
            chrome_options.add_argument("--no-first-run")
            
            chrome_options.add_argument("--window-size=1280,720")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Cloud Run için binary path
            chrome_options.binary_location = "/usr/bin/google-chrome"
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            logger.info("✅ Chrome driver başlatıldı")
            return driver
        except Exception as e:
            logger.error(f"❌ Chrome driver hatası: {e}")
            return None

    def scrape_sahibinden_fsbo(self, max_pages: int = 3) -> List[Dict[str, Any]]:
        """Sahibinden.com'dan FSBO ilanlarını çek"""
        listings = []
        driver = None
        
        try:
            driver = self.get_chrome_driver()
            if not driver:
                logger.error("Chrome driver oluşturulamadı")
                return listings

            # Sahibinden.com emlak satılık sayfası
            base_url = "https://www.sahibinden.com/satilik-daire"
            
            for page in range(1, max_pages + 1):
                try:
                    url = f"{base_url}?pageno={page}"
                    logger.info(f"🔍 Sayfa {page} taranıyor: {url}")
                    
                    driver.get(url)
                    time.sleep(random.uniform(2, 4))  # Random delay
                    
                    # İlan listesi konteynerini bekle
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "searchResultsItem"))
                    )
                    
                    # Sayfayı parse et
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    page_listings = self.parse_listings_page(soup, page)
                    listings.extend(page_listings)
                    
                    logger.info(f"✅ Sayfa {page}: {len(page_listings)} ilan bulundu")
                    
                    # Rate limiting
                    time.sleep(random.uniform(3, 6))
                    
                except Exception as e:
                    logger.error(f"❌ Sayfa {page} scraping hatası: {e}")
                    self.error_count += 1
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Scraping genel hatası: {e}")
            
        finally:
            if driver:
                driver.quit()
                logger.info("🔒 Chrome driver kapatıldı")
                
        return listings

    def parse_listings_page(self, soup: BeautifulSoup, page_num: int) -> List[Dict[str, Any]]:
        """Sayfa HTML'ini parse ederek ilan bilgilerini çıkar"""
        listings = []
        
        try:
            # İlan konteynerlerini bul
            listing_items = soup.find_all("tr", {"class": "searchResultsItem"})
            
            for item in listing_items:
                try:
                    listing_data = self.parse_single_listing(item)
                    if listing_data and self.is_fsbo_candidate(listing_data):
                        listing_data['source_page'] = page_num
                        listing_data['scraped_at'] = datetime.now()
                        listings.append(listing_data)
                        self.scraped_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ Tek ilan parse hatası: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Sayfa parse hatası: {e}")
            
        return listings

    def parse_single_listing(self, item) -> Dict[str, Any]:
        """Tek bir ilan elementini parse et"""
        try:
            # Başlık ve link
            title_elem = item.find("a", {"class": "classifiedTitle"})
            if not title_elem:
                return None
                
            title = title_elem.get_text(strip=True)
            url = "https://www.sahibinden.com" + title_elem.get('href', '')
            
            # Fiyat
            price_elem = item.find("td", {"class": "searchResultsPriceValue"})
            price_text = price_elem.get_text(strip=True) if price_elem else "0"
            price = self.clean_price(price_text)
            
            # Lokasyon
            location_elem = item.find("td", {"class": "searchResultsLocationValue"})
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # İlan detayları
            details_elem = item.find("td", {"class": "searchResultsAttributeValue"})
            details = details_elem.get_text(strip=True) if details_elem else ""
            
            # Tarih
            date_elem = item.find("td", {"class": "searchResultsDateValue"})
            date_text = date_elem.get_text(strip=True) if date_elem else ""
            
            return {
                'title': title,
                'price': price,
                'location': location,
                'details': details,
                'date_text': date_text,
                'url': url,
                'opportunity_score': self.calculate_opportunity_score(title, price, location)
            }
            
        except Exception as e:
            logger.error(f"❌ Listing parse hatası: {e}")
            return None

    def clean_price(self, price_text: str) -> int:
        """Fiyat metnini temizleyip sayıya çevir"""
        try:
            # "₺ 850.000" -> 850000
            cleaned = price_text.replace('₺', '').replace('.', '').replace(' ', '').replace('TL', '')
            return int(cleaned) if cleaned.isdigit() else 0
        except:
            return 0

    def is_fsbo_candidate(self, listing: Dict[str, Any]) -> bool:
        """FSBO adayı olup olmadığını kontrol et"""
        title = listing.get('title', '').lower()
        
        # FSBO anahtar kelimeleri
        fsbo_keywords = [
            'sahibinden', 'acil', 'takas', 'değişen', 'tahliye', 
            'ihtiyaçtan', 'krediye uygun', 'acele', 'ivedi'
        ]
        
        # Emlakçı blacklist
        agent_keywords = ['emlak', 'gayrimenkul', 'danışman', 'broker', 'ofis']
        
        # FSBO anahtar kelimesi var mı?
        has_fsbo_keyword = any(keyword in title for keyword in fsbo_keywords)
        
        # Emlakçı kelimesi var mı?
        has_agent_keyword = any(keyword in title for keyword in agent_keywords)
        
        # Fiyat aralığı kontrolü (çok düşük veya çok yüksek fiyatları filtrele)
        price = listing.get('price', 0)
        price_ok = 100000 <= price <= 10000000  # 100K - 10M TL arası
        
        return has_fsbo_keyword and not has_agent_keyword and price_ok

    def calculate_opportunity_score(self, title: str, price: int, location: str) -> int:
        """Fırsat skoru hesapla (1-10)"""
        score = 5  # Base score
        
        title_lower = title.lower()
        
        # Acil satış kelimeleri (+2 puan)
        if any(word in title_lower for word in ['acil', 'acele', 'ivedi']):
            score += 2
            
        # Takas/değişim (+1 puan)
        if any(word in title_lower for word in ['takas', 'değişen']):
            score += 1
            
        # İhtiyaçtan satış (+2 puan)
        if any(word in title_lower for word in ['ihtiyaçtan', 'tahliye']):
            score += 2
            
        # Lokasyon bonusu
        location_lower = location.lower()
        if any(loc in location_lower for loc in ['kadıköy', 'beşiktaş', 'şişli']):
            score += 1
            
        # Fiyat bonusu (ortalama altı fiyatlar)
        if 200000 <= price <= 500000:
            score += 1
            
        return min(max(score, 1), 10)  # 1-10 arasında sınırla

    def save_to_firestore(self, listings: List[Dict[str, Any]]) -> int:
        """İlanları Firestore'a kaydet"""
        saved_count = 0
        
        try:
            batch = self.db.batch()
            
            for listing in listings:
                # Duplicate kontrolü için URL hash
                doc_id = f"fsbo_{hash(listing['url'])}"
                doc_ref = self.db.collection('fsbo_listings').document(doc_id)
                
                # Firestore format
                firestore_data = {
                    'title': listing['title'],
                    'price': listing['price'],
                    'location': listing['location'],
                    'url': listing['url'],
                    'opportunityScore': listing['opportunity_score'],
                    'details': listing.get('details', ''),
                    'dateText': listing.get('date_text', ''),
                    'sourcePage': listing.get('source_page', 1),
                    'scrapedAt': listing['scraped_at'],
                    'isActive': True,
                    'reason': f"Cloud scraper - Score: {listing['opportunity_score']}"
                }
                
                batch.set(doc_ref, firestore_data, merge=True)
                saved_count += 1
                
                # Batch size limit
                if saved_count % 100 == 0:
                    batch.commit()
                    batch = self.db.batch()
                    
            # Son batch'i commit et
            if saved_count % 100 != 0:
                batch.commit()
                
            logger.info(f"✅ {saved_count} ilan Firestore'a kaydedildi")
            
        except Exception as e:
            logger.error(f"❌ Firestore kaydetme hatası: {e}")
            
        return saved_count

    def run_scraping_job(self, max_pages: int = 3) -> Dict[str, Any]:
        """Ana scraping job'unu çalıştır"""
        start_time = datetime.now()
        logger.info(f"🚀 FSBO Cloud Scraper başlatıldı - {start_time}")
        
        try:
            # Scraping yap
            listings = self.scrape_sahibinden_fsbo(max_pages)
            
            # Firestore'a kaydet
            saved_count = self.save_to_firestore(listings)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            result = {
                'success': True,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'total_scraped': self.scraped_count,
                'total_saved': saved_count,
                'errors': self.error_count,
                'pages_processed': max_pages
            }
            
            logger.info(f"✅ Scraping tamamlandı: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Scraping job hatası: {e}")
            return {
                'success': False,
                'error': str(e),
                'scraped_count': self.scraped_count,
                'error_count': self.error_count
            }

# Flask Routes
@app.route('/', methods=['GET', 'POST'])
def run_scraper():
    """Cloud Run endpoint - scraper'ı çalıştır"""
    try:
        # Query parametrelerini al
        max_pages = int(request.args.get('pages', 3))
        
        logger.info(f"🌐 Cloud Run scraper endpoint çağrıldı - pages: {max_pages}")
        
        # Scraper'ı çalıştır
        scraper = FSBOCloudScraper()
        result = scraper.run_scraping_job(max_pages)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Endpoint hatası: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'fsbo-cloud-scraper'})

if __name__ == '__main__':
    # Local development
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
