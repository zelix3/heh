from flask import Flask, request, render_template_string
from playwright.sync_api import sync_playwright
import urllib.parse
import os

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Virtual Browser</title>
  <style>
    body { font-family: sans-serif; padding: 1em; background: #f8fafc; }
    form { margin-bottom: 1em; }
    textarea { width: 100%; height: 70vh; }
  </style>
</head>
<body>
  <h1>Virtual Browser</h1>
  <form action="/go">
    <input type="url" name="url" placeholder="https://example.org" size="50" required>
    <button type="submit">Go</button>
  </form>
  {% if html %}
    <h2>Rendered HTML (after JS):</h2>
    <textarea readonly>{{ html }}</textarea>
  {% endif %}
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(TEMPLATE)

@app.route("/go")
def go():
    url = request.args.get("url")
    if not url:
        return render_template_string(TEMPLATE)

    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            content = page.content()
            browser.close()
        return render_template_string(TEMPLATE, html=content)
    except Exception as e:
        return render_template_string(TEMPLATE, html=f"Error: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use Render's port if provided
    app.run(host="0.0.0.0", port=port, debug=True)
