from flask import Flask, request, render_template_string, session, redirect, url_for
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os

app = Flask(__name__)
app.secret_key = "change-me-please"  # replace with a strong random string

# Initialize history in session
def init_history():
    if "hist" not in session:
        session["hist"] = {"back": [], "current": None, "forward": []}

def visit(url):
    init_history()
    h = session["hist"]
    if h["current"]:
        h["back"].append(h["current"])
        h["forward"] = []
    h["current"] = url
    session.modified = True

def nav(which):
    init_history()
    h = session["hist"]
    if which == "back" and h["back"]:
        h["forward"].append(h["current"])
        h["current"] = h["back"].pop()
    elif which == "forward" and h["forward"]:
        h["back"].append(h["current"])
        h["current"] = h["forward"].pop()
    session.modified = True

def current_url():
    init_history()
    return session["hist"].get("current")

# HTML template
TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Virtual Browser</title>
<style>
body { font-family: sans-serif; background:#f8fafc; padding:1em; }
form { margin-bottom:1em; display:flex; gap:4px; }
input[type=url]{flex:1;padding:6px;}
button{padding:6px;}
textarea{width:100%;height:70vh;}
a{color:#0ea5e9;}
</style>
</head>
<body>
<h1>Virtual Browser</h1>
<form action="{{ url_for('go') }}" method="get">
  <input type="url" name="url" placeholder="https://example.org" value="{{ current or '' }}" required>
  <button type="submit">Go</button>
  <button formaction="{{ url_for('navigate') }}" name="nav" value="back">⟵ Back</button>
  <button formaction="{{ url_for('navigate') }}" name="nav" value="forward">Forward ⟶</button>
</form>
{% if html %}
<h2>Fetched HTML</h2>
<textarea readonly>{{ html }}</textarea>
{% endif %}
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(TEMPLATE, current=current_url(), html=None)

@app.route("/navigate", methods=["POST"])
def navigate():
    which = request.form.get("nav")
    nav(which)
    cur = current_url()
    if cur:
        return redirect(url_for("go", url=cur))
    return redirect(url_for("index"))

@app.route("/go")
def go():
    url = request.args.get("url")
    if not url:
        return redirect(url_for("index"))
    if not urlparse(url).scheme:
        url = "https://" + url
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script","style","iframe","object","embed"]):
            tag.decompose()
        visit(url)
        return render_template_string(TEMPLATE, current=url, html=str(soup))
    except Exception as e:
        return render_template_string(TEMPLATE, current=url, html=f"Error fetching page: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
