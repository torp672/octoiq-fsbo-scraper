# 🚀 OctoIQ Cloud FSBO Scraper

Sahibinden.com'dan FSBO (For Sale By Owner) ilanlarını otomatik çeken cloud-based scraper.

## 🏗️ Architecture

```
Cloud Scheduler → Cloud Run (Python) → Firestore
     (Daily)         (Scraper)         (Data)
```

## 📋 Prerequisites

1. **Google Cloud CLI kurulu olmalı:**
   ```bash
   # Windows
   https://cloud.google.com/sdk/docs/install

   # Verify
   gcloud --version
   ```

2. **Google Cloud login:**
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

3. **Firebase project:**
   - Project ID: `emlakiq` ✅

## 🚀 Deploy

### Option 1: PowerShell (Windows)
```powershell
cd cloud-scraper
.\deploy.ps1
```

### Option 2: Bash (Linux/Mac)
```bash
cd cloud-scraper
chmod +x deploy.sh
./deploy.sh
```

### Option 3: Manual
```bash
gcloud run deploy fsbo-scraper \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 1Gi \
    --timeout 3600
```

## 🧪 Test

```bash
# Health check
curl https://fsbo-scraper-xxx.run.app/health

# Manual scrape (1 page)
curl "https://fsbo-scraper-xxx.run.app?pages=1"
```

## ⏰ Schedule (Otomatik Çalışma)

```bash
gcloud scheduler jobs create http fsbo-daily-job \
    --schedule="0 9 * * *" \
    --uri="https://fsbo-scraper-xxx.run.app" \
    --http-method=POST \
    --location=us-central1
```

## 📊 Monitoring

- **Cloud Run Logs:** Google Cloud Console → Cloud Run → fsbo-scraper → Logs
- **Firestore Data:** Firebase Console → Firestore → fsbo_listings
- **Scheduler:** Cloud Console → Cloud Scheduler

## ⚙️ Configuration

### Environment Variables
- `GOOGLE_CLOUD_PROJECT`: emlakiq (otomatik)
- `PORT`: 8080 (otomatik)

### Scraper Settings
```python
# fsbo_scraper.py içinde düzenleyebilirsiniz:
max_pages = 3  # Kaç sayfa taranacak
delay = random.uniform(2, 4)  # Sayfalar arası bekleme
```

## 🔧 Troubleshooting

### 1. Deploy Errors
```bash
# API enable
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Permissions
gcloud projects add-iam-policy-binding emlakiq \
    --member="user:your-email@gmail.com" \
    --role="roles/run.developer"
```

### 2. Scraping Issues
- Cloud Run logs kontrol edin
- Chrome driver sorunları için memory artırın
- Rate limiting için delay'leri artırın

### 3. Firestore Connection
- Service account permissions kontrol edin
- Firebase project ID doğru mu kontrol edin

## 📈 Performance

- **Memory:** 1GB (Chrome için)
- **CPU:** 1 vCPU
- **Timeout:** 1 hour
- **Concurrency:** 1 (rate limiting için)

## 💰 Cost Estimation

- **Cloud Run:** ~$2-5/month (günlük 1 çalışma)
- **Cloud Scheduler:** Free tier
- **Firestore:** Existing usage

## 🔒 Security

- ✅ Rate limiting (2-6 saniye delay)
- ✅ User agent rotation
- ✅ Headless browser
- ✅ Firebase security rules
- ✅ Unauthenticated endpoint (scheduler için)