#!/usr/bin/env python3
"""
OctoIQ CRM Cost-Effective FSBO Scraper
Sahibinden.com'dan FSBO ilanlarını otomatik çeker - API maliyeti yok
Cloud Run üzerinde çalışır
"""

import os
import json
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from typing import List, Dict, Any
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartFSBOScraper:
    """
    Cost-effective FSBO scraper with intelligent bot avoidance
    """
    def __init__(self):
        self.init_firebase()
        self.init_sessions()
        
    def init_firebase(self):
        """Firebase bağlantısı"""
        try:
            if not firebase_admin._apps:
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.info("✅ Firebase connected")
        except Exception as e:
            logger.error(f"❌ Firebase error: {e}")
            self.db = None
    
    def init_sessions(self):
        """Multiple sessions with rotating user agents"""
        self.sessions = []
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]
        
        for ua in user_agents:
            session = requests.Session()
            session.headers.update({
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            self.sessions.append(session)
        
        logger.info(f"✅ {len(self.sessions)} sessions ready")
    
    def smart_request(self, url: str, max_retries: int = 3) -> str:
        """Smart request with retry and rotation"""
        for attempt in range(max_retries):
            try:
                session = random.choice(self.sessions)
                
                # Random delay
                delay = 2 + random.uniform(0.5, 2.5)
                if attempt > 0:
                    delay += attempt * 2
                time.sleep(delay)
                
                response = session.get(url, timeout=15)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Bot protection check
                    bot_indicators = ['bir dakika', 'please wait', 'cloudflare', 'captcha']
                    if any(indicator in content.lower() for indicator in bot_indicators):
                        logger.warning(f"🤖 Bot protection detected (attempt {attempt + 1})")
                        continue
                    
                    logger.info("✅ Request successful")
                    return content
                
                logger.warning(f"❌ HTTP {response.status_code} (attempt {attempt + 1})")
                
            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
        
        return None
    
    def parse_listings(self, html: str, source_url: str) -> List[Dict]:
        """Enhanced listing parser"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            listings = []
            
            # Find listing rows
            rows = soup.select('tr[data-id]')
            logger.info(f"📊 Found {len(rows)} potential listings")
            
            for row in rows[:20]:  # Process max 20
                try:
                    listing = self.extract_listing_data(row)
                    if listing and listing.get('title'):
                        listing['fsbo_score'] = self.calculate_fsbo_score(listing)
                        listing['source_url'] = source_url
                        listing['scraped_at'] = datetime.now().isoformat()
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Parse error: {e}")
                    continue
            
            logger.info(f"✅ Parsed {len(listings)} valid listings")
            return listings
            
        except Exception as e:
            logger.error(f"HTML parsing failed: {e}")
            return []
    
    def extract_listing_data(self, row) -> Dict:
        """Extract data from listing row"""
        data = {}
        
        try:
            # Title and URL
            title_link = row.select_one('a[title]')
            if title_link:
                data['title'] = title_link.get('title', '').strip()
                href = title_link.get('href', '')
                if href:
                    data['url'] = f"https://www.sahibinden.com{href}" if href.startswith('/') else href
            
            # Price
            price_elem = row.select_one('.searchResultsPriceValue')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                data['price_text'] = price_text
                data['price'] = self.extract_price(price_text)
            
            # Location
            location_elem = row.select_one('.searchResultsLocationValue')
            if location_elem:
                data['location'] = location_elem.get_text(strip=True)
            
            # Property details
            attrs = row.select('.searchResultsAttributeValue')
            if len(attrs) >= 3:
                data['rooms'] = attrs[0].get_text(strip=True) if attrs[0] else None
                data['sqm'] = self.extract_number(attrs[1].get_text(strip=True)) if attrs[1] else None
                data['age'] = self.extract_number(attrs[2].get_text(strip=True)) if attrs[2] else None
            
            # Date
            date_elem = row.select_one('.searchResultsDateValue')
            if date_elem:
                data['posted_date'] = date_elem.get_text(strip=True)
            
            return data
            
        except Exception as e:
            logger.error(f"Data extraction failed: {e}")
            return {}
    
    def calculate_fsbo_score(self, listing: Dict) -> int:
        """Advanced FSBO detection scoring"""
        score = 0
        title = listing.get('title', '').lower()
        location = listing.get('location', '').lower()
        text = f"{title} {location}"
        
        # Strong FSBO indicators
        strong_keywords = [
            ('sahibinden', 3), ('sahipten', 3), ('acil', 2), 
            ('ihtiyaçtan', 3), ('kelepir', 2), ('değişim', 2),
            ('takas', 2), ('aracısız', 2), ('komisyonsuz', 2)
        ]
        
        # Negative indicators (agents)
        negative_keywords = [
            ('emlak', -1), ('gayrimenkul', -1), ('ofis', -1),
            ('danışman', -1), ('acentesi', -1), ('grup', -1),
            ('şirket', -1), ('ltd', -1)
        ]
        
        # Apply scoring
        for keyword, weight in strong_keywords + negative_keywords:
            if keyword in text:
                score += weight
        
        # Price analysis
        price = listing.get('price')
        if price and price % 1000 != 0:  # Non-round prices suggest individuals
            score += 1
        
        # Recent posting
        posted = listing.get('posted_date', '').lower()
        if any(recent in posted for recent in ['bugün', 'dün', '1 gün', '2 gün']):
            score += 1
        
        return max(0, min(10, score))
    
    def extract_price(self, price_text: str) -> int:
        """Extract numeric price"""
        try:
            import re
            clean = price_text.replace('TL', '').replace('₺', '').replace('.', '').replace(',', '')
            numbers = re.findall(r'\d+', clean)
            return int(''.join(numbers)) if numbers else None
        except:
            return None
    
    def extract_number(self, text: str) -> int:
        """Extract first number from text"""
        try:
            import re
            numbers = re.findall(r'\d+', text)
            return int(numbers[0]) if numbers else None
        except:
            return None
    
    def save_to_firebase(self, listings: List[Dict], location: str) -> Dict:
        """Save listings to Firebase"""
        if not self.db:
            logger.error("Firebase not available")
            return {'saved': 0, 'fsbo': 0}
        
        try:
            saved_count = 0
            fsbo_count = 0
            
            for listing in listings:
                # Generate unique ID
                import hashlib
                unique_data = f"{listing.get('title', '')}-{listing.get('location', '')}"
                doc_id = hashlib.md5(unique_data.encode('utf-8')).hexdigest()[:16]
                
                # Add metadata
                listing.update({
                    'found_at': firestore.SERVER_TIMESTAMP,
                    'source_location': location,
                    'is_active': True,
                    'version': 'cost_effective_v2'
                })
                
                # Save
                self.db.collection('fsbo_listings').document(doc_id).set(listing, merge=True)
                saved_count += 1
                
                if listing.get('fsbo_score', 0) >= 5:
                    fsbo_count += 1
            
            logger.info(f"✅ Saved {saved_count} listings, {fsbo_count} FSBO candidates")
            return {'saved': saved_count, 'fsbo': fsbo_count}
            
        except Exception as e:
            logger.error(f"Firebase save error: {e}")
            return {'saved': 0, 'fsbo': 0}
    
    def scrape_location(self, city: str, district: str = None) -> Dict:
        """Scrape specific location"""
        logger.info(f"🔍 Scraping {city} {district or ''}")
        
        # Build URL
        city_clean = city.lower().replace('i̇', 'i')
        url = f"https://www.sahibinden.com/satilik-daire/{city_clean}"
        if district:
            url += f"-{district.lower()}"
        url += "?sorting=date_desc"
        
        # Make request
        html = self.smart_request(url)
        if not html:
            return {'success': False, 'error': 'Failed to fetch data'}
        
        # Parse listings
        listings = self.parse_listings(html, url)
        if not listings:
            return {'success': False, 'error': 'No listings found'}
        
        # Save to Firebase
        location_key = f"{city}_{district}" if district else city
        save_result = self.save_to_firebase(listings, location_key)
        
        # Analyze results
        fsbo_listings = [l for l in listings if l.get('fsbo_score', 0) >= 5]
        
        return {
            'success': True,
            'location': f"{city} {district or ''}",
            'total_listings': len(listings),
            'fsbo_candidates': len(fsbo_listings),
            'saved_to_firebase': save_result['saved'],
            'url': url,
            'top_fsbo': sorted(fsbo_listings, key=lambda x: x.get('fsbo_score', 0), reverse=True)[:3]
        }
    
    def multi_location_scrape(self) -> Dict:
        """Scrape multiple high-value locations"""
        locations = [
            ('istanbul', 'kadikoy'),
            ('istanbul', 'atasehir'), 
            ('istanbul', 'besiktas'),
            ('istanbul', 'beylikduzu'),
            ('ankara', 'cankaya')
        ]
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'locations': [],
            'summary': {'total_listings': 0, 'total_fsbo': 0, 'locations_scraped': 0}
        }
        
        for city, district in locations:
            try:
                result = self.scrape_location(city, district)
                results['locations'].append(result)
                
                if result['success']:
                    results['summary']['total_listings'] += result['total_listings']
                    results['summary']['total_fsbo'] += result['fsbo_candidates']
                    results['summary']['locations_scraped'] += 1
                
                # Delay between locations
                time.sleep(random.uniform(3, 7))
                
            except Exception as e:
                logger.error(f"Location scrape failed: {e}")
                continue
        
        return results

# Flask App
app = Flask(__name__)
scraper = SmartFSBOScraper()

@app.route('/')
def home():
    return jsonify({
        'service': 'OctoIQ Cost-Effective FSBO Scraper',
        'version': '2.0',
        'features': [
            'Smart bot avoidance',
            'No API costs', 
            'Enhanced FSBO detection',
            'Firebase integration',
            'Multi-location support'
        ],
        'status': 'ready',
        'cost_model': 'infrastructure_only'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'firebase': scraper.db is not None,
        'sessions': len(scraper.sessions),
        'cost_effective': True
    })

@app.route('/scrape')
def scrape_all():
    """Run multi-location scrape"""
    try:
        results = scraper.multi_location_scrape()
        return jsonify({
            'success': True,
            'results': results,
            'cost_analysis': {
                'api_costs': '$0',
                'monthly_estimate': '$20-50 (Cloud Run only)'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/scrape/<city>')
def scrape_city(city):
    """Scrape specific city"""
    try:
        result = scraper.scrape_location(city)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/scrape/<city>/<district>')
def scrape_district(city, district):
    """Scrape specific city-district"""
    try:
        result = scraper.scrape_location(city, district)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)