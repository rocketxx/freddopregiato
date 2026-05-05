#!/usr/bin/env python3
"""
Extract product images and names from catalog PDF - V2
Uses word-level positioning to build labels per image column.
"""

import fitz  # PyMuPDF
import pdfplumber
import json
import os
import re
from pathlib import Path
from collections import defaultdict

PDF_PATH = "./catalogo.pdf"
OUTPUT_DIR = "./image"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name):
    name = name.strip().lower()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name[:80]

def extract_images_with_positions(doc, page_num):
    """Extract product images (skip tiny/huge ones) with bounding boxes."""
    page = doc[page_num]
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    images = []
    
    for img in page.get_images(full=True):
        xref = img[0]
        rects = page.get_image_rects(img)
        if not rects:
            continue
        rect = rects[0]
        
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            
            # Skip tiny images (icons, decorations, masks) and huge backgrounds
            if pix.width < 100 or pix.height < 100:
                continue
            img_area = rect.width * rect.height
            if img_area > page_area * 0.4:
                continue
            # Skip smask / alpha-only images
            if pix.alpha and pix.n == 2:  # gray + alpha only
                continue
                
            images.append({
                'xref': xref,
                'rect': rect,
                'x0': rect.x0, 'y0': rect.y0,
                'x1': rect.x1, 'y1': rect.y1,
                'cx': (rect.x0 + rect.x1) / 2,
                'cy': (rect.y0 + rect.y1) / 2,
                'width': pix.width, 'height': pix.height,
                'pix': pix
            })
        except:
            continue
    
    return images

def get_words_pdfplumber(pdf_plumber, page_num):
    """Get individual words with positions."""
    page = pdf_plumber.pages[page_num]
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    return words

# Common header/category patterns to skip
SKIP_PATTERNS = [
    r'^PESCE\s*SURGELATO$', r'^PESCI\s*INTERI', r'^E/O$', r'^LAVORATI$',
    r'^CROSTACEI$', r'^MOLLUSCHI$', r'^CEFALOPODI$', r'^SPECIALITÀ$',
    r'^FRITTURE$', r'^PANATI$', r'^PASTELLATI$', r'^ELABORATI$',
    r'^CATALOGO$', r'^www\.', r'^VEGETALI$', r'^CONTORNI$',
    r'^PIZZE$', r'^SNACK$', r'^DOLCI$', r'^PANE$', r'^INDICE$',
    r'^INDEX$', r'^SURGELATO$', r'^NC$', r'^PESCE$', r'^LINEA\s',
    r'^DESSERT$', r'^COLAZIONE$', r'^GELATI$', r'^POLLO$',
    r'^GHIACCIO$', r'^SENZA\s*GLUTINE$', r'^FUNGHI$', r'^FRUTTA$',
    r'^\d+$', r'^PRIMI\s*PIATTI', r'^PIATTI\s*PRONTI',
    r'^CUORE\s*DI\s*MAMMA$', r'^LINEA\s', r'^JOLLY$',
    r'^ARTIGIANALE$', r'^MANTECATO$', r'^BARCHETTE$',
    r'^VASCHETTE\s*1KG$', r'^LATTOSIO$', r'^MULTIPACK$',
    r'^ROYAL$', r'^PRONTOFORNO$',
]

def is_header_word(text):
    """Check if text is a header/category (not a product name)."""
    t = text.strip().upper()
    for pat in SKIP_PATTERNS:
        if re.match(pat, t):
            return True
    return False

def match_images_to_text(images, words, scale_x, scale_y):
    """
    For each image, find words that are directly below it (within the image's
    horizontal span) and close vertically. These words form the product name.
    """
    results = []
    
    for img in images:
        img_x0 = img['x0']
        img_x1 = img['x1']
        img_y1 = img['y1']  # bottom of image
        img_cx = img['cx']
        img_width = img_x1 - img_x0
        
        # Expand horizontal search zone a bit
        margin_x = img_width * 0.15
        search_x0 = img_x0 - margin_x
        search_x1 = img_x1 + margin_x
        
        # Look for words below the image, within a reasonable distance
        candidate_words = []
        for w in words:
            wx0 = w['x0'] * scale_x
            wx1 = w['x1'] * scale_x
            wy0 = w['top'] * scale_y
            wy1 = w['bottom'] * scale_y
            wcx = (wx0 + wx1) / 2
            
            # Word must be below image
            if wy0 < img_y1 - 5:
                continue
            # Word must not be too far below
            if wy0 > img_y1 + 60:
                continue
            # Word center must be within image horizontal span
            if wcx < search_x0 or wcx > search_x1:
                continue
            
            candidate_words.append({
                'text': w['text'],
                'x0': wx0, 'x1': wx1,
                'top': wy0, 'bottom': wy1,
                'cy': (wy0 + wy1) / 2
            })
        
        # Sort candidate words by vertical then horizontal position
        candidate_words.sort(key=lambda w: (round(w['top'] / 8) * 8, w['x0']))
        
        # Build the label from words, grouping lines
        if candidate_words:
            lines = []
            current_line = [candidate_words[0]]
            for i in range(1, len(candidate_words)):
                cw = candidate_words[i]
                prev = current_line[-1]
                if abs(cw['top'] - prev['top']) < 10:
                    current_line.append(cw)
                else:
                    lines.append(current_line)
                    current_line = [cw]
            lines.append(current_line)
            
            label_parts = []
            for line in lines:
                line_text = ' '.join(w['text'] for w in line)
                label_parts.append(line_text)
            
            label = ' '.join(label_parts).strip()
            
            # Clean up: remove header-like fragments
            # But keep the full label if it seems like a real product name
            if label and not is_header_word(label):
                results.append({'image': img, 'label': label})
            else:
                results.append({'image': img, 'label': None})
        else:
            results.append({'image': img, 'label': None})
    
    return results


# Main
print("Opening PDF...")
doc = fitz.open(PDF_PATH)
pdf_plumber = pdfplumber.open(PDF_PATH)

all_products = []
counter = 0

for page_num in range(len(doc)):
    images = extract_images_with_positions(doc, page_num)
    if not images:
        continue
    
    words = get_words_pdfplumber(pdf_plumber, page_num)
    
    fitz_page = doc[page_num]
    plumber_page = pdf_plumber.pages[page_num]
    scale_x = fitz_page.rect.width / plumber_page.width
    scale_y = fitz_page.rect.height / plumber_page.height
    
    matches = match_images_to_text(images, words, scale_x, scale_y)
    
    named_count = sum(1 for m in matches if m['label'])
    print(f"Page {page_num+1}: {len(images)} images, {named_count} named")
    
    for match in matches:
        counter += 1
        label = match['label']
        img = match['image']
        
        if label:
            filename = f"{sanitize_filename(label)}.png"
        else:
            filename = f"unknown_{counter:03d}.png"
        
        filepath = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(filepath):
            base, ext = os.path.splitext(filepath)
            filepath = f"{base}_{counter}{ext}"
            filename = os.path.basename(filepath)
        
        img['pix'].save(filepath)
        
        all_products.append({
            'name': label or f"Unknown #{counter}",
            'filename': filename,
            'page': page_num + 1
        })
        if label:
            print(f"  [{counter}] {label}")

# Save index
index_path = os.path.join(OUTPUT_DIR, "products_index.json")
with open(index_path, 'w', encoding='utf-8') as f:
    json.dump(all_products, f, ensure_ascii=False, indent=2)

named = sum(1 for p in all_products if not p['name'].startswith('Unknown'))
print(f"\n=== Done! {len(all_products)} total, {named} named, {len(all_products)-named} unknown ===")

doc.close()
pdf_plumber.close()