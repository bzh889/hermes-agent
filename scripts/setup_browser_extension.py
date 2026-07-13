"""One-shot: open Chrome with extensions, navigate to Hermes extension sidepanel,
fill API key, click connect, close."""
import sys, os, time, json

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

from playwright.sync_api import sync_playwright

API_KEY = os.environ.get('API_SERVER_KEY', '')
if not API_KEY:
    print("ERROR: API_SERVER_KEY not set in environment (see ~/.hermes/.env)", flush=True)
    sys.exit(1)
EXT_ID = 'fkpiioklhoejanmepmfaljanjmeoafkk'
HOST = 'http://127.0.0.1:8642'
RESULT_PATH = r'D:/01_Job/Tool/Hermes Agent/ext_config_result.json'

with sync_playwright() as p:
    print("Launching Chrome...", flush=True)
    browser = p.chromium.launch_persistent_context(
        user_data_dir=r'C:/Users/mtk12265/AppData/Local/Google/Chrome/User Data',
        headless=False,
        channel='chrome',
        args=['--disable-blink-features=AutomationControlled'],
        ignore_default_args=['--disable-extensions'],
    )
    print("Chrome launched OK", flush=True)

    # Wait for extensions to load
    time.sleep(3)

    # Open a blank page then navigate to the extension
    page = browser.pages[0] if browser.pages else browser.new_page()
    
    # Try multiple possible entry points
    ext_page = None
    for path in ['sidepanel.html', 'popup.html', 'options.html']:
        url = f'chrome-extension://{EXT_ID}/{path}'
        try:
            print(f"Trying {path}...", flush=True)
            test_page = browser.new_page()
            test_page.goto(url, timeout=5000, wait_until='domcontentloaded')
            title = test_page.title()
            print(f"  Loaded: title={title}", flush=True)
            if title or test_page.query_selector('body'):
                ext_page = test_page
                break
            test_page.close()
        except Exception as e:
            print(f"  Failed: {e}", flush=True)

    if not ext_page:
        print("Could not load extension page - trying JavaScript injection via page", flush=True)
        # Inject the settings via chrome.storage API by using a content script approach
        # This won't work from a regular page due to permissions
        # Let's try a different approach: use CDP to evaluate in extension context
        
        result = {"error": "extension page not accessible", "host": HOST, "key": API_KEY[:4]+"..."}
        with open(RESULT_PATH, 'w') as f:
            json.dump(result, f, indent=2)
        browser.close()
        sys.exit(1)

    print(f"Extension page loaded: {ext_page.url}", flush=True)

    # Take a screenshot for debugging
    ext_page.screenshot(path=r'D:/01_Job/Tool/Hermes Agent/ext_screenshot.png')
    print("Screenshot saved", flush=True)

    # Inject settings directly via chrome.storage.local
    # Side panel pages have access to chrome.storage
    try:
        ext_page.evaluate("""
            () => new Promise((resolve, reject) => {
                if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
                    reject('chrome.storage.local not available');
                    return;
                }
                chrome.storage.local.get('hermesBrowserSettings', (old) => {
                    const settings = old.hermesBrowserSettings || {};
                    settings.apiKey = '%API_KEY%';
                    settings.agentDiscoveryHost = '127.0.0.1';
                    settings.agentDiscoveryScheme = 'http';
                    chrome.storage.local.set({hermesBrowserSettings: settings}, () => {
                        resolve('Settings saved');
                    });
                });
            })
        """.replace('%API_KEY%', API_KEY))
        print("SETTINGS_INJECTED_VIA_CHROME_STORAGE", flush=True)
    except Exception as e:
        print(f"Chrome storage inject failed: {e}", flush=True)
        
        # Fallback: find and fill form fields
        inputs = ext_page.query_selector_all('input')
        print(f"Found {len(inputs)} input fields", flush=True)
        
        for inp in inputs:
            itype = inp.get_attribute('type') or ''
            iid = inp.get_attribute('id') or ''
            ival = ''
            try: ival = inp.input_value()
            except: pass
            print(f"  input: id={iid} type={itype} val={ival}", flush=True)
        
        # Fill by matching common patterns
        for inp in inputs:
            iid = (inp.get_attribute('id') or '').lower()
            itype = inp.get_attribute('type') or ''
            aria = (inp.get_attribute('aria-label') or '').lower()
            ph = (inp.get_attribute('placeholder') or '').lower()
            
            keywords = iid + aria + ph
            if any(kw in keywords for kw in ['api', 'key', 'token', 'secret']) or itype == 'password':
                try:
                    inp.fill(API_KEY)
                    print(f"FILLED_API_KEY in {iid}", flush=True)
                except Exception as e:
                    print(f"Fill error: {e}", flush=True)

        # Click connect/save
        buttons = ext_page.query_selector_all('button')
        for btn in buttons:
            t = (btn.text_content() or '').lower().strip()
            if any(kw in t for kw in ['connect', 'save', 'apply']):
                try:
                    btn.click()
                    print(f"CLICKED_{t}", flush=True)
                except: pass
                break

    time.sleep(3)

    # Verify settings
    try:
        result = ext_page.evaluate("""
            () => new Promise((resolve) => {
                chrome.storage.local.get('hermesBrowserSettings', (data) => {
                    resolve(data.hermesBrowserSettings || {});
                });
            })
        """)
        print(f"VERIFIED_SETTINGS: apiKey={'***' if result.get('apiKey') else 'EMPTY'} host={result.get('agentDiscoveryHost','?')}", flush=True)
        with open(RESULT_PATH, 'w') as f:
            # Don't write the actual key to file
            r = dict(result)
            if 'apiKey' in r:
                r['apiKey'] = '***configured***'
            json.dump(r, f, indent=2, default=str)
    except Exception as e:
        print(f"Verify failed: {e}", flush=True)

    time.sleep(2)
    browser.close()
    print("DONE", flush=True)
