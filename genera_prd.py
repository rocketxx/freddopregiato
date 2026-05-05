import json
import os
import shutil

IMAGE_SRC = "image"
IMAGE_DST = "image-prd"
CATALOGO_SRC = "catalogo.json"
CATALOGO_DST = "catalogo-prd.json"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/rocketxx/freddopregiato/main/image-prd/"

os.makedirs(IMAGE_DST, exist_ok=True)

with open(CATALOGO_SRC, encoding="utf-8") as f:
    catalogo = json.load(f)

# Indice catalogo: filename → entry (normalizzato: trattini → underscore per il match)
catalogo_index = {}
for entry in catalogo:
    key = entry["immagine"].replace("-", "_")
    catalogo_index[key] = entry

images = sorted(os.listdir(IMAGE_SRC))[:50]

risultato = []
non_trovati = []

for img_file in images:
    src = os.path.join(IMAGE_SRC, img_file)
    dst = os.path.join(IMAGE_DST, img_file)
    shutil.copy2(src, dst)

    key = img_file
    entry = catalogo_index.get(key)

    if entry:
        risultato.append({
            "nome": entry["nome"],
            "descrizione": entry["descrizione"],
            "immagine": GITHUB_RAW_BASE + img_file,
        })
    else:
        non_trovati.append(img_file)
        risultato.append({
            "nome": img_file.replace("_", " ").replace(".png", "").upper(),
            "descrizione": "",
            "immagine": GITHUB_RAW_BASE + img_file,
        })

with open(CATALOGO_DST, "w", encoding="utf-8") as f:
    json.dump(risultato, f, ensure_ascii=False, indent=2)

print(f"Copiate {len(images)} immagini in '{IMAGE_DST}'")
print(f"Creato '{CATALOGO_DST}' con {len(risultato)} voci")
if non_trovati:
    print(f"\nNon trovati in catalogo.json ({len(non_trovati)}):")
    for n in non_trovati:
        print(f"  - {n}")
