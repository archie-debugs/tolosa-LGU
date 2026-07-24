import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")

app = FastAPI(title="LGU Tolosa Mobile Scanner")


HTML_TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SB Tolosa Mobile Scanner</title>
    <style>
        :root { color-scheme: light; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        body { margin: 0; background: linear-gradient(160deg, #f8fafc 0%, #eef4fb 100%); color: #0f172a; }
        .wrap { max-width: 860px; margin: 0 auto; padding: 20px; }
        .card { background: rgba(255,255,255,.9); border: 1px solid #dbe4ee; border-radius: 20px; padding: 18px; box-shadow: 0 18px 50px rgba(15,23,42,.08); margin-bottom: 16px; }
        h1, h2 { margin: 0 0 12px; }
        label { display: block; font-size: 14px; margin: 10px 0 6px; color: #334155; }
        input, select, button { width: 100%; box-sizing: border-box; border-radius: 14px; border: 1px solid #cbd5e1; padding: 14px 16px; font-size: 16px; background: #fff; }
        button { background: #0f766e; color: white; font-weight: 700; border: none; margin-top: 12px; }
        button.secondary { background: #1d4ed8; }
        button.danger { background: #b91c1c; }
        .grid { display: grid; gap: 16px; grid-template-columns: 1.2fr .8fr; }
        .hidden { display: none; }
        video { width: 100%; border-radius: 18px; background: #000; aspect-ratio: 3/4; object-fit: cover; }
        .status { padding: 12px 14px; border-radius: 14px; background: #f1f5f9; margin-top: 12px; white-space: pre-wrap; }
        .success { background: #dcfce7; color: #14532d; }
        .error { background: #fee2e2; color: #991b1b; }
        .muted { color: #64748b; font-size: 14px; }
        .timeline { display: flex; flex-direction: column; gap: 10px; }
        .timeline-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 12px 14px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>QR Document Transit & Location Tracker</h1>
            <div class="muted">Login first, then scan document QR codes using the phone camera.</div>
        </div>

        <div class="card" id="loginCard">
            <h2>Scanner Login</h2>
            <label for="username">Username</label>
            <input id="username" autocomplete="username" />
            <label for="password">Password</label>
            <input id="password" type="password" autocomplete="current-password" />
            <button id="loginBtn">Login</button>
            <div id="loginStatus" class="status">Ready.</div>
        </div>

        <div class="card hidden" id="scannerCard">
            <div class="grid">
                <div>
                    <h2>Scan & Receive</h2>
                    <label for="office">Receiving Office</label>
                    <select id="office">
                        <option>Records Registry</option>
                        <option>Secretariat</option>
                        <option>Mayor's Office</option>
                        <option>Committee Chair</option>
                        <option>Committee Hearing Room</option>
                        <option>Session Hall</option>
                        <option>Legal Office</option>
                    </select>

                    <div style="margin-top:14px">
                        <video id="preview" playsinline muted></video>
                        <canvas id="canvas" class="hidden"></canvas>
                    </div>

                    <label for="uuid">Document UUID</label>
                    <input id="uuid" placeholder="Scan will fill this automatically" />
                    <button id="scanBtn" class="secondary">Start Camera</button>
                    <button id="receiveBtn">Receive Document</button>
                    <button id="logoutBtn" class="danger">Logout Scanner</button>
                    <div id="scanStatus" class="status">Camera not started.</div>
                </div>

                <div>
                    <h2>Selected Document Timeline</h2>
                    <div id="timelineSummary" class="muted">Scan a document to load its movement history.</div>
                    <div id="timeline" class="timeline" style="margin-top:12px"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const params = new URLSearchParams(window.location.search);
        const backend = params.get('api_base') || '__BACKEND_URL__';
        const preloadedUuid = params.get('uuid') || '';
        const loginCard = document.getElementById('loginCard');
        const scannerCard = document.getElementById('scannerCard');
        const loginStatus = document.getElementById('loginStatus');
        const scanStatus = document.getElementById('scanStatus');
        const timelineSummary = document.getElementById('timelineSummary');
        const timeline = document.getElementById('timeline');
        const preview = document.getElementById('preview');
        const uuidInput = document.getElementById('uuid');
        const officeSelect = document.getElementById('office');
        const loginBtn = document.getElementById('loginBtn');
        const scanBtn = document.getElementById('scanBtn');
        const receiveBtn = document.getElementById('receiveBtn');
        const logoutBtn = document.getElementById('logoutBtn');
        const usernameInput = document.getElementById('username');
        const passwordInput = document.getElementById('password');

        let scannerToken = localStorage.getItem('sb_tolosa_scanner_token') || '';
        let scanning = false;
        let stream = null;
        let detector = null;

        if (preloadedUuid) {
            uuidInput.value = preloadedUuid;
        }

        function showScanner() {
            loginCard.classList.add('hidden');
            scannerCard.classList.remove('hidden');
        }

        function showLogin() {
            scannerCard.classList.add('hidden');
            loginCard.classList.remove('hidden');
        }

        function setStatus(el, message, kind) {
            el.className = 'status' + (kind ? ' ' + kind : '');
            el.textContent = message;
        }

        function renderTimeline(items, documentTitle, currentLocation) {
            timelineSummary.textContent = `${documentTitle} is currently at ${currentLocation}.`;
            timeline.innerHTML = '';
            if (!items.length) {
                timeline.innerHTML = '<div class="timeline-item">No scan history yet for this document.</div>';
                return;
            }
            for (const entry of items) {
                const when = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : 'Unknown time';
                const node = document.createElement('div');
                node.className = 'timeline-item';
                node.textContent = `${entry.previous_location} → ${entry.new_location}\nReceived by ${entry.receiving_office}\n${when} • ${entry.logged_in_user}`;
                timeline.appendChild(node);
            }
        }

        async function loadTimeline(uuid) {
            if (!uuid) return;
            const response = await fetch(`${backend}/documents/history/${encodeURIComponent(uuid)}`);
            if (!response.ok) return;
            const payload = await response.json();
            renderTimeline(payload.items || [], payload.document?.title || 'Untitled Document', payload.document?.current_location || 'Records Registry');
        }

        function loadTimelineInBackground(uuid) {
            void loadTimeline(uuid).catch(() => {});
        }

        async function performLogin() {
            const username = usernameInput.value.trim();
            const password = passwordInput.value;
            if (!username || !password) {
                setStatus(loginStatus, 'Enter username and password.', 'error');
                return;
            }
            const params = new URLSearchParams({ username, password });
            const response = await fetch(`${backend}/auth/scanner/login?${params.toString()}`, { method: 'POST' });
            const payload = await response.json();
            if (!response.ok) {
                setStatus(loginStatus, payload.detail || 'Login failed.', 'error');
                return;
            }
            scannerToken = payload.token;
            localStorage.setItem('sb_tolosa_scanner_token', scannerToken);
            setStatus(loginStatus, `Logged in as ${payload.username} (${payload.role}).`, 'success');
            showScanner();
            if (uuidInput.value.trim()) {
                loadTimelineInBackground(uuidInput.value.trim());
            }
            startCamera();
        }

        async function logoutScanner() {
            if (scannerToken) {
                await fetch(`${backend}/auth/scanner/logout?token=${encodeURIComponent(scannerToken)}`, { method: 'POST' });
            }
            scannerToken = '';
            localStorage.removeItem('sb_tolosa_scanner_token');
            stopCamera();
            setStatus(scanStatus, 'Scanner logged out.', '');
            showLogin();
        }

        function stopCamera() {
            scanning = false;
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                stream = null;
            }
        }

        async function startCamera() {
            if (!scannerToken) {
                setStatus(scanStatus, 'Login required before scanning.', 'error');
                return;
            }
            if (!('BarcodeDetector' in window)) {
                setStatus(scanStatus, 'BarcodeDetector is not supported in this browser. Use manual UUID entry or Chrome on Android.', 'error');
                return;
            }
            detector = detector || new BarcodeDetector({ formats: ['qr_code'] });
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
                preview.srcObject = stream;
                await preview.play();
                scanning = true;
                setStatus(scanStatus, 'Camera started. Point at a document QR code.', 'success');
                requestAnimationFrame(scanLoop);
            } catch (error) {
                setStatus(scanStatus, `Camera start failed: ${error.message}`, 'error');
            }
        }

        async function scanLoop() {
            if (!scanning || !stream) return;
            try {
                const codes = await detector.detect(preview);
                if (codes && codes.length) {
                    const code = codes[0].rawValue.trim();
                    uuidInput.value = code;
                    stopCamera();
                    void receiveDocument();
                    return;
                }
            } catch (error) {
                setStatus(scanStatus, `Scan error: ${error.message}`, 'error');
            }
            requestAnimationFrame(scanLoop);
        }

        async function receiveDocument() {
            const trackingUuid = uuidInput.value.trim();
            if (!trackingUuid) {
                setStatus(scanStatus, 'Scan a document QR code first.', 'error');
                return;
            }
            const office = officeSelect.value || 'Records Registry';
            const params = new URLSearchParams({ receiving_office: office, scanner_token: scannerToken });
            const response = await fetch(`${backend}/documents/receive/${encodeURIComponent(trackingUuid)}?${params.toString()}`, { method: 'POST' });
            const payload = await response.json();
            if (!response.ok) {
                setStatus(scanStatus, payload.detail || payload.message || 'Receive failed.', 'error');
                return;
            }
            setStatus(scanStatus, `${payload.document_title}\n${payload.previous_location} → ${payload.new_location}`, 'success');
            uuidInput.value = '';
            loadTimelineInBackground(trackingUuid);
            requestAnimationFrame(() => uuidInput.focus());
        }

        loginBtn.addEventListener('click', performLogin);
        scanBtn.addEventListener('click', startCamera);
        receiveBtn.addEventListener('click', receiveDocument);
        logoutBtn.addEventListener('click', logoutScanner);
        uuidInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                receiveDocument();
            }
        });

        if (scannerToken) {
            showScanner();
            setStatus(loginStatus, 'Restored scanner session.', 'success');
            if (uuidInput.value.trim()) {
                loadTimelineInBackground(uuidInput.value.trim());
            }
            startCamera();
        }
    </script>
</body>
</html>'''


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/scanner/mobile", status_code=307)


@app.get("/scanner/mobile")
def mobile_scanner_page(api_base: str | None = None, uuid: str | None = None):
    html = HTML_TEMPLATE.replace("__BACKEND_URL__", BACKEND_URL)
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8002")), reload=False)