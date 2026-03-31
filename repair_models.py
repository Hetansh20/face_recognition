import os, requests, zipfile, time

URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
TARGET_DIR = r"C:\Users\USER\.insightface\models\buffalo_l"
ZIP_PATH = r"C:\Users\USER\.insightface\models\buffalo_l.zip"

os.makedirs(r"C:\Users\USER\.insightface\models", exist_ok=True)

print("Cleaning up incorrect files...")
for f in ["det_10g.onnx", "webface_r50.onnx"]:
    p = os.path.join(TARGET_DIR, f)
    if os.path.exists(p): 
        try:
            os.remove(p)
            print(f"Removed faulty {f}")
        except:
            pass

while True:
    try:
        downloaded = os.path.getsize(ZIP_PATH) if os.path.exists(ZIP_PATH) else 0
        # If it's already exactly 281857000 we can just break
        if downloaded >= 281857000:
            print("\nDownload already complete!")
            break

        headers = {"Range": f"bytes={downloaded}-"} if downloaded > 0 else {}
        print(f"\nResuming download from {(downloaded / 1024 / 1024):.1f} MB...")
        
        with requests.get(URL, headers=headers, stream=True, timeout=15) as r:
            if r.status_code == 416: 
                print("\nDownload complete!")
                break
            r.raise_for_status()
            
            with open(ZIP_PATH, "ab" if downloaded > 0 else "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        print(f"\rProgress: {(downloaded / 1024 / 1024):.1f} MB", end="")
            
        print("\nFinished download stream.")
        break # Successfully finished iter_content
    except Exception as e:
        print(f"\nConnection dropped ({e}). Retrying in 2 seconds...")
        time.sleep(2)

print("\nExtracting...")
os.makedirs(TARGET_DIR, exist_ok=True)
with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
    zf.extractall(TARGET_DIR)
print("Successfully extracted to", TARGET_DIR)
