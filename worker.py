from flask import Flask, request, jsonify
import subprocess, json, tempfile, requests, os, shutil, re

app = Flask(__name__)

def map_res(width, height):
    w,h = int(width or 0), int(height or 0)
    if w>=7680 and h>=4320: return "8K"
    if w>=3840 and h>=2160: return "4K"
    if w>=2560 and h>=1440: return "Ultra HD"
    if w>=1920 and h>=1080: return "Full HD"
    return f"{w}x{h}" if w and h else ""

def hhmmss(seconds):
    s = int(round(float(seconds or 0)))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

@app.post("/probe")
def probe():
    data = request.get_json(silent=True) or {}
    url = data.get("url"); filename = data.get("filename") or "file"
    if not url: return jsonify(error="Missing url"), 400

    tmpdir = tempfile.mkdtemp()
    local = os.path.join(tmpdir, filename)
    try:
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(local, "wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk: f.write(chunk)

        width = height = fps = None; duration = None
        try:
            cmd = [
                "ffprobe","-v","error",
                "-select_streams","v:0",
                "-show_entries","stream=width,height,avg_frame_rate",
                "-show_entries","format=duration",
                "-of","json", local
            ]
            meta = json.loads(subprocess.check_output(cmd).decode())
            if meta.get("format", {}).get("duration"):
                duration = hhmmss(meta["format"]["duration"])
            if meta.get("streams"):
                v = meta["streams"][0]
                width, height = v.get("width"), v.get("height")
                afr = v.get("avg_frame_rate","0/1")
                n,d = afr.split("/")
                fps = round(float(n)/float(d),2) if float(d)!=0 else None
        except Exception:
            pass

        exif = {}
        try:
            out = subprocess.check_output(["exiftool","-json",local]).decode()
            arr = json.loads(out)
            if isinstance(arr, list) and arr: exif = arr[0]
        except Exception:
            pass

        named = map_res(width, height) if (width and height) else ""
        date = None
        for k in ("CreateDate","DateTimeOriginal","ModifyDate","MediaCreateDate"):
            if k in exif:
                m = re.search(r"(\d{4})[:\-](\d{2})[:\-](\d{2})", str(exif[k]))
                if m: date = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"; break

        return jsonify({
            "duration": duration,
            "width": width, "height": height,
            "fps": fps,
            "resolution_named": named,
            "date": date,
            "gps": {
                "lat": exif.get("GPSLatitude"),
                "lon": exif.get("GPSLongitude")
            }
        })
    finally:
        try: shutil.rmtree(tmpdir)
        except Exception: pass

@app.get("/healthz")
def health(): return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

