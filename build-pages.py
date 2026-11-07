#!/usr/bin/env python3
"""
RajRebel Creations - builds one page per prompt for Google search and link previews.

Run by GitHub Actions (.github/workflows/prompt-pages.yml) every 30 minutes.
Reads the public posts from Firebase (read-only), then writes:
  p/<post-id>/index.html   one page per post (title, photo, description, steps, prompts)
  p/img/<post-id>.jpg      the post photo, sized for WhatsApp / Facebook previews
  sitemap.xml              list of all pages for Google
Nothing in Firebase is changed. Posts and old ?post= links are not touched.
"""
import base64, html, io, json, os, re, shutil, sys, urllib.request
from datetime import datetime, timezone

DB = os.environ.get("RRC_DB", "https://rajrebel-prompts-default-rtdb.firebaseio.com")
SITE = "https://rajrebelcreations.com"
OUT = os.environ.get("RRC_OUT", ".")
LOCAL_JSON = os.environ.get("RRC_LOCAL_JSON")          # for testing without network
ADSENSE = "ca-pub-6259806536022165"
CHATGPT = "https://chatgpt.com/"
FLOW = "https://labs.google/fx/tools/flow"

CATS = [
    ("Photo Prompts", "photo", ["AI Photo Prompts", "Gemini AI"]),
    ("Video Prompts", "video", ["AI Video Prompts", "Google Flow"]),
    ("Couple Photo Prompts", "photo", ["AI Couple Prompts"]),
    ("Couple Video Prompts", "video", []),
    ("Girls Photo Prompts", "photo", []),
    ("Boys Photo Prompts", "photo", []),
    ("Wishes Photo Prompts", "photo", []),
    ("Wishes Video Prompts", "video", []),
    ("Devotional Photo Prompts", "photo", ["Gods Photo Prompts"]),
    ("Devotional Video Prompts", "video", ["Gods Video Prompts"]),
    ("Tips & Tutorials", "tutorial", ["Tips & Tricks"]),
]


def cat_of(name):
    for label, typ, old in CATS:
        if name == label or name in old:
            return label, typ
    return (name or "Photo Prompts"), "photo"


def fetch(path):
    req = urllib.request.Request(f"{DB}/{path}.json", headers={"User-Agent": "rrc-pages"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def load_posts():
    if LOCAL_JSON:
        data = json.load(open(LOCAL_JSON, encoding="utf-8"))
        posts = data.get("posts", data)
        return {k: v for k, v in posts.items() if not k.startswith("__") and isinstance(v, dict)}
    shallow = json.loads(urllib.request.urlopen(f"{DB}/posts.json?shallow=true", timeout=60).read().decode("utf-8")) or {}
    out = {}
    for k in sorted(shallow):
        if k.startswith("__"):
            continue
        v = fetch("posts/" + k)
        if isinstance(v, dict):
            out[k] = v
    return out


def safe_id(k):
    return re.sub(r"[^A-Za-z0-9_-]", "-", k)[:80]


def yt_id(url):
    m = re.search(r"(?:youtu\.be/|v=|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", str(url or ""))
    return m.group(1) if m else ""


def prompts_of(p):
    pr = p.get("prompts")
    if isinstance(pr, list) and any(pr):
        return [x for x in pr if x]
    return [p["prompt"]] if p.get("prompt") else []


def post_time(k, p):
    m = re.search(r"(\d{12,13})", k)
    ms = int(m.group(1)) if m else 0
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def save_image(k, p, img_dir):
    """Returns the public image URL for previews (or None)."""
    src = p.get("image") or ""
    data = None
    if src.startswith("data:image"):
        try:
            data = base64.b64decode(src.split(",", 1)[1])
        except Exception:
            data = None
    elif src.startswith("http"):
        try:
            data = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "rrc-pages"}), timeout=60).read()
        except Exception:
            return src  # use the link as it is
    if not data:
        yid = yt_id(p.get("videoUrl"))
        return f"https://i.ytimg.com/vi/{yid}/hqdefault.jpg" if yid else None
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((1200, 1200))
        q = 82
        while True:
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
            if buf.tell() <= 280_000 or q <= 50:
                break
            q -= 8
        out = buf.getvalue()
    except Exception:
        out = data  # Pillow missing: keep original bytes
    name = safe_id(k) + ".jpg"
    path = os.path.join(img_dir, name)
    old = open(path, "rb").read() if os.path.exists(path) else None
    if old != out:
        open(path, "wb").write(out)
    return f"{SITE}/p/img/{name}"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


PAGE_CSS = """*{box-sizing:border-box}body{margin:0;background:#07090e;color:#f3f4f6;font-family:Roboto,system-ui,-apple-system,"Segoe UI",Arial,sans-serif;line-height:1.55}
a{color:inherit}.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid #1d2333;position:sticky;top:0;background:rgba(7,9,14,.92);backdrop-filter:blur(8px);z-index:5}
header .wrap{display:flex;align-items:center;gap:10px;height:60px}header img{width:38px;height:38px;border-radius:11px}
header b{font-size:19px;background:linear-gradient(90deg,#a99bff,#f07bb5,#f5c518);-webkit-background-clip:text;background-clip:text;color:transparent}
.media{margin:16px 0 0;border-radius:18px;overflow:hidden;border:1px solid #232a3d;background:#0f1320}.media img{display:block;width:100%;height:auto}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}.tag{font-size:12.5px;font-weight:700;padding:5px 11px;border-radius:999px;background:#151b2b;color:#cfd3dc}.tag.y{background:#f5c518;color:#1a1400}.tag.v{background:#8b7bff;color:#120a33}
h1{font-size:26px;line-height:1.25;margin:6px 0 10px}h2{font-size:18px;margin:26px 0 10px}
.desc{color:#c7cbd6;white-space:pre-line}.box{background:#0f1320;border:1px solid #232a3d;border-radius:16px;padding:14px 16px;white-space:pre-line}
.pr{background:#0f1320;border:1px solid #232a3d;border-radius:16px;margin:12px 0;overflow:hidden}.pr .h{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #232a3d}
.pr .h b{color:#f5c518;font-size:14px;letter-spacing:.3px}.pr pre{margin:0;padding:14px;white-space:pre-wrap;word-break:break-word;font:14px/1.6 ui-monospace,Menlo,Consolas,monospace;color:#e6e8ee}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;border-radius:12px;font:inherit;font-weight:800;cursor:pointer;text-decoration:none}
.copy{background:transparent;color:#f5c518;border:1.5px solid #f5c518;padding:7px 14px;font-size:14px}
.cta{display:grid;gap:10px;margin:22px 0}.bar{position:fixed;left:0;right:0;bottom:0;padding:10px 0 calc(10px + env(safe-area-inset-bottom));background:linear-gradient(transparent,#07090e 35%);z-index:6}.bar .big{width:100%;background:#f5c518;color:#1a1400;min-height:54px;font-size:17px;box-shadow:0 8px 30px rgba(245,197,24,.35)}body{padding-bottom:90px}.cta .big{background:#f5c518;color:#1a1400;min-height:54px;font-size:17px}.cta .alt{background:#151b2b;color:#fff;min-height:48px;border:1px solid #2a3248}
.yt{position:relative;display:block}.yt span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}.yt span i{width:72px;height:72px;border-radius:50%;background:#d71920;display:flex;align-items:center;justify-content:center}
.yt span i:after{content:"";border-left:24px solid #fff;border-top:15px solid transparent;border-bottom:15px solid transparent;margin-left:6px}
footer{margin:34px 0 24px;color:#8a90a2;font-size:13px;text-align:center}footer a{margin:0 8px;color:#a9aec0}
.appbar{display:flex;align-items:center;gap:10px;margin:12px 0 0;padding:10px 10px 10px 12px;border-radius:14px;background:linear-gradient(135deg,#1b1f33,#241a33);border:1px solid #3a2f55}
.appbar[hidden],.apptip[hidden]{display:none}.appbar img{width:40px;height:40px;border-radius:10px;flex:none}.appbar .t{flex:1;min-width:0;line-height:1.25}
.appbar .t b{display:block;font-size:13.5px}.appbar .t span{font-size:11.5px;color:#9aa0b2}.appbar .go{border:0;border-radius:10px;background:#f5c518;color:#1a1400;font:inherit;font-weight:800;font-size:13px;padding:9px 14px;cursor:pointer;flex:none}
.appbar .x{border:0;background:transparent;color:#7d8396;font-size:18px;line-height:1;padding:4px 6px;cursor:pointer;flex:none}
.apptip{margin:8px 2px 0;font-size:12.5px;line-height:1.45;color:#b7bccb;background:#121726;border:1px solid #232a3d;border-radius:12px;padding:10px 12px}.apptip b{color:#f5c518}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#f5c518;color:#1a1400;font-weight:800;padding:10px 18px;border-radius:12px;opacity:0;transition:opacity .2s;pointer-events:none}.toast.on{opacity:1}"""

PAGE_JS = r"""
const CHATGPT="%CHATGPT%",FLOW="%FLOW%";
const and=/android/i.test(navigator.userAgent);
function toast(t){const e=document.getElementById("toast");e.textContent=t;e.classList.add("on");clearTimeout(window._t);window._t=setTimeout(()=>e.classList.remove("on"),1800)}
async function copyText(t){try{await navigator.clipboard.writeText(t)}catch(e){const a=document.createElement("textarea");a.value=t;document.body.appendChild(a);a.select();document.execCommand("copy");a.remove()}}
let last="";
document.querySelectorAll("[data-copy]").forEach(b=>b.addEventListener("click",async()=>{const t=document.getElementById(b.dataset.copy).textContent;last=t;await copyText(t);toast("Prompt copied ✓");b.textContent="Copied"}));
function appLink(web,pkg){if(!and)return web;return"intent://"+web.replace(/^https:\/\//,"")+"#Intent;scheme=https;package="+pkg+";S.browser_fallback_url="+encodeURIComponent(web)+";end"}
const g=document.getElementById("openGpt");if(g)g.addEventListener("click",async e=>{e.preventDefault();const t=last||(document.querySelector("pre")||{}).textContent||"";if(t)await copyText(t);const enc=encodeURIComponent(t);location.href=appLink(enc&&enc.length<=6000?CHATGPT+"?prompt="+enc:CHATGPT,"com.openai.chatgpt")});
const f=document.getElementById("openFlow");if(f)f.addEventListener("click",async e=>{e.preventDefault();const t=last||(document.querySelector("pre")||{}).textContent||"";if(t)await copyText(t);location.href=appLink(FLOW,"com.google.android.apps.labs.whisk")});

let installEvt=null;
const UA=navigator.userAgent,isIOS=/iphone|ipad|ipod/i.test(UA),isAnd=/android/i.test(UA);
const inApp=/Instagram|FBAN|FBAV|FB_IAB|Line\/|Snapchat|TikTok|musical_ly|; wv\)/i.test(UA);
const standalone=()=>matchMedia("(display-mode: standalone)").matches||navigator.standalone===true;
const KEY="rrcAppBarHidden";
function dismissed(){try{return Date.now()-Number(localStorage.getItem(KEY)||0)<3*864e5}catch(e){return false}}
function tip(){if(inApp&&isAnd)return"Tap <b>⋮</b> (top right) and choose <b>Open in Chrome</b> or <b>Open in browser</b>, then tap <b>Install</b> again.";if(inApp&&isIOS)return"Tap <b>⋯</b> and choose <b>Open in Safari</b>. Then tap <b>Share</b> → <b>Add to Home Screen</b>.";if(isIOS)return"Tap the <b>Share</b> button at the bottom, then <b>Add to Home Screen</b>.";return"Tap <b>⋮</b> in Chrome (top right), then <b>Install app</b> or <b>Add to Home screen</b>."}
function showBar(){const b=document.getElementById("appBar");if(!b||standalone()||dismissed()||!(isIOS||isAnd))return;b.hidden=false}
function hideBar(){document.getElementById("appBar").hidden=true;document.getElementById("appTip").hidden=true}
addEventListener("beforeinstallprompt",e=>{e.preventDefault();installEvt=e;showBar()});
addEventListener("appinstalled",()=>{installEvt=null;hideBar()});
showBar();
document.getElementById("appBarGo").addEventListener("click",async()=>{if(installEvt){installEvt.prompt();try{await installEvt.userChoice}catch(e){}installEvt=null;hideBar();return}const t=document.getElementById("appTip");t.innerHTML=tip();t.hidden=!t.hidden});
document.getElementById("appBarX").addEventListener("click",()=>{try{localStorage.setItem(KEY,String(Date.now()))}catch(e){}hideBar()});
if("serviceWorker"in navigator&&location.protocol==="https:")navigator.serviceWorker.register("/sw.js").catch(()=>{});
""".replace("%CHATGPT%", CHATGPT).replace("%FLOW%", FLOW)


def build_page(k, p, img_url):
    label, typ = cat_of(p.get("category"))
    title = (p.get("title") or "AI Prompt").strip()
    desc = (p.get("description") or "").strip()
    steps = (p.get("process") or "").strip()
    prompts = prompts_of(p)
    labels = p.get("promptLabels") if isinstance(p.get("promptLabels"), list) else []
    yid = yt_id(p.get("videoUrl"))
    kind = {"photo": "AI Photo Prompt", "video": "AI Video Prompt", "tutorial": "Tutorial"}[typ]
    url = f"{SITE}/p/{safe_id(k)}/"
    meta_desc = clip(desc, 160) or (
        f"{title}. Free {kind.lower()} by RajRebel Creations - copy with one tap and create with your own photo."
        if typ != "tutorial" else f"{title}. Free tutorial by RajRebel Creations.")
    if not steps:
        if typ == "video":
            steps = '1. Tap "Copy" on the prompt below.\n2. Tap "Open Google Flow" and upload your photo.\n3. Paste the prompt and generate.'
        elif typ == "photo":
            steps = '1. Tap "Copy" on the prompt below.\n2. Tap "Open ChatGPT" and upload your photo.\n3. Paste the prompt and send.'
        else:
            steps = "Watch the video and follow along."

    if typ == "tutorial" and yid:
        media = (f'<a class="media yt" href="https://www.youtube.com/watch?v={yid}" target="_blank" rel="noopener">'
                 f'<img src="{esc(img_url or "")}" alt="{esc(title)}" loading="eager"><span><i></i></span></a>')
    elif img_url:
        media = f'<div class="media"><img src="{esc(img_url)}" alt="{esc(title)}" loading="eager"></div>'
    else:
        media = ""

    pr_html = ""
    for i, t in enumerate(prompts):
        lab = labels[i] if i < len(labels) and labels[i] else (f"Prompt {i + 1}" if len(prompts) > 1 else "Prompt")
        pr_html += (f'<div class="pr"><div class="h"><b>{esc(lab).upper()}</b>'
                    f'<button class="btn copy" data-copy="p{i}">Copy</button></div><pre id="p{i}">{esc(t)}</pre></div>')

    app_url = f"{SITE}/?post={esc(k)}"
    if typ == "tutorial":
        cta = (f'<a class="btn big" href="https://www.youtube.com/watch?v={yid}" target="_blank" rel="noopener">▶ Watch Video</a>' if yid
               else (f'<a class="btn big" href="{esc(p.get("videoUrl"))}" target="_blank" rel="noopener">▶ Watch Video</a>' if p.get("videoUrl") else ""))
    elif typ == "video":
        cta = '<a class="btn big" id="openFlow" href="' + FLOW + '">Copy &amp; Open Google Flow</a>'
    else:
        cta = '<a class="btn big" id="openGpt" href="' + CHATGPT + '">Copy &amp; Open ChatGPT</a>'
    bar = f'<div class="bar"><div class="wrap">{cta}</div></div>' if cta else ""
    cta = f'<a class="btn alt" href="{app_url}">Open in RRC AI Prompts</a><a class="btn alt" href="{SITE}/">More free prompts</a>'

    t = post_time(k, p)
    ld = {
        "@context": "https://schema.org", "@type": "CreativeWork", "name": title, "headline": title,
        "description": meta_desc, "url": url, "inLanguage": "en", "genre": label,
        "author": {"@type": "Organization", "name": "RajRebel Creations", "url": SITE + "/"},
        "publisher": {"@type": "Organization", "name": "RajRebel Creations", "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png"}},
    }
    if img_url:
        ld["image"] = img_url
    if t:
        ld["datePublished"] = t.strftime("%Y-%m-%d")
    og_img = (f'<meta property="og:image" content="{esc(img_url)}">\n<meta property="og:image:alt" content="{esc(title)}">\n'
              f'<meta name="twitter:image" content="{esc(img_url)}">') if img_url else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)} | RajRebel Creations</title>
<meta name="description" content="{esc(meta_desc)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#07090e">
<meta property="og:type" content="article">
<meta property="og:site_name" content="RajRebel Creations">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(meta_desc)}">
<meta property="og:url" content="{url}">
{og_img}
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">
<meta name="google-adsense-account" content="{ADSENSE}">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>{PAGE_CSS}</style>
</head>
<body>
<header><div class="wrap"><a href="/" style="display:flex;align-items:center;gap:10px;text-decoration:none"><img src="/logo-96.png" alt=""><b>RajRebel Creations</b></a></div></header>
<main class="wrap">
<div class="appbar" id="appBar" hidden><img src="/icon-192.png" alt=""><div class="t"><b>Get the RRC AI Prompts app</b><span>Free · opens in one tap from your home screen</span></div><button class="go" id="appBarGo">Install</button><button class="x" id="appBarX" aria-label="Close">✕</button></div><p class="apptip" id="appTip" hidden></p>
{media}
<div class="tags"><span class="tag {'v' if typ == 'tutorial' else 'y'}">{kind.upper()}</span><span class="tag">{esc(label)}</span>{f'<span class="tag">{esc(p.get("topic"))}</span>' if p.get("topic") else ''}</div>
<h1>{esc(title)}</h1>
{f'<p class="desc">{esc(desc)}</p>' if desc else ''}
<h2>{'Steps' if typ == 'tutorial' else 'How to use'}</h2>
<div class="box">{esc(steps)}</div>
{('<h2>' + ('Prompts' if len(prompts) > 1 else 'Prompt') + '</h2>' + pr_html) if prompts else ''}
<div class="cta">{cta}</div>
</main>
<footer class="wrap"><a href="/">Home</a><a href="/?page=about">About</a><a href="/?page=contact">Contact</a><a href="/?page=privacy">Privacy Policy</a><a href="/?page=terms">Terms</a><br><br>© RajRebel Creations</footer>
{bar}
<div class="toast" id="toast"></div>
<script>{PAGE_JS}</script>
</body>
</html>
"""


def main():
    posts = load_posts()
    if not posts:
        print("No posts found - nothing changed.")
        return 0
    pdir = os.path.join(OUT, "p")
    img_dir = os.path.join(pdir, "img")
    os.makedirs(img_dir, exist_ok=True)
    keep = set()
    entries = []
    for k, p in sorted(posts.items()):
        sid = safe_id(k)
        keep.add(sid)
        img_url = save_image(k, p, img_dir)
        page = build_page(k, p, img_url)
        d = os.path.join(pdir, sid)
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, "index.html")
        old = open(f, encoding="utf-8").read() if os.path.exists(f) else None
        if old != page:
            open(f, "w", encoding="utf-8").write(page)
        t = post_time(k, p)
        entries.append((f"{SITE}/p/{sid}/", t.strftime("%Y-%m-%d") if t else None))
    # remove pages of deleted posts
    for name in os.listdir(pdir):
        if name == "img":
            continue
        if name not in keep and os.path.isdir(os.path.join(pdir, name)):
            shutil.rmtree(os.path.join(pdir, name))
    for name in os.listdir(img_dir):
        if name.endswith(".jpg") and name[:-4] not in keep:
            os.remove(os.path.join(img_dir, name))
    # sitemap
    urls = [f"  <url><loc>{SITE}/</loc></url>"]
    for loc, lm in sorted(entries, key=lambda e: e[1] or "", reverse=True):
        urls.append(f"  <url><loc>{loc}</loc>{f'<lastmod>{lm}</lastmod>' if lm else ''}</url>")
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    smf = os.path.join(OUT, "sitemap.xml")
    if not os.path.exists(smf) or open(smf, encoding="utf-8").read() != sm:
        open(smf, "w", encoding="utf-8").write(sm)
    print(f"Built {len(entries)} prompt pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
