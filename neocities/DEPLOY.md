# Pocket Willow — Neocities Deployment

Static frontend hosted on Neocities, connected to your Willow server via cloud relay.

## Architecture

```
[Neocities]  ──HTTPS──>  [Cloud Relay]  ──>  [Willow Server]
 index.html               Oracle/tunnel       127.0.0.1:8420
```

## Setup

### 1. Upload to Neocities

Upload `index.html` to your Neocities site (seancampbell.neocities.org).
Put it at `/willow/index.html` or replace the root `index.html`.

### 2. Expose Willow to the Internet (pick one)

**Option A: Cloudflare Tunnel (free, recommended for now)**

```bash
# Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://127.0.0.1:8420
```

This gives you a temporary `https://xxxxx.trycloudflare.com` URL.
Paste that URL into the "server" config on the Neocities page.

**Option B: Oracle Cloud Always Free (persistent)**

1. Sign up: https://cloud.oracle.com/free
2. Provision an ARM VM (4 cores, 24GB RAM — Always Free tier)
3. Clone Willow repo, install deps, run server:
   ```bash
   git clone <your-willow-repo> && cd Willow
   pip install -r requirements.txt
   uvicorn server:app --host 0.0.0.0 --port 8420
   ```
4. Open port 8420 in Oracle security list
5. Set the public IP in the Neocities config: `http://<oracle-ip>:8420`

**Option C: ngrok (free tier, temporary)**

```bash
ngrok http 8420
```

### 3. CORS

Add your Neocities origin to `server.py` CORS middleware:

```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://seancampbell.neocities.org",
],
```

### 4. Configure the Page

1. Open `https://seancampbell.neocities.org/willow/`
2. Click "server" button
3. Enter your relay URL (cloudflared/Oracle/ngrok)
4. The URL is saved in your browser's localStorage

## Security Notes

- The API key (if any) is never in the HTML — it stays on your server
- CORS restricts which origins can call your server
- Cloudflare tunnel encrypts transit automatically
- For Oracle: use HTTPS via Let's Encrypt + nginx reverse proxy in production
