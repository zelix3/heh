from flask import Flask, request, render_template_string
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_autoinstaller
import os

app = Flask(__name__)

# Template
TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Headless Browser</title>
<style>
body { font-family: sans-serif; background:#f8fafc; padding:1em; }
form { margin-bottom:1em; display:flex; gap:4px; }
input[type=url]{flex:1;padding:6px;}
button{padding:6px;}
textarea{width:100%;height:70vh;}
</style>
</head>
<body>
<h1>Headless Browser</h1>
<form action="/go">
  <input type="url" name="url" placeholder="https://example.com" value="{{ url or '' }}" required>
  <button type="submit">Go</button>
</form>
{% if html %}
<h2>Rendered HTML</h2>
<textarea readonly>{{ html }}</textarea>
{% endif %}
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(TEMPLATE, url=None, html=None)

@app.route("/go")
def go():
    url = request.args.get("url")
    if not url:
        return render_template_string(TEMPLATE, url=None, html=None)
    if not url.startswith("http"):
        url = "https://" + url

    # Install ChromeDriver automatically
    chromedriver_autoinstaller.install()

    # Configure headless Chrome
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")       # needed on Render
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        html = driver.page_source
        driver.quit()
        return render_template_string(TEMPLATE, url=url, html=html)
    except Exception as e:
        return render_template_string(TEMPLATE, url=url, html=f"Error: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
