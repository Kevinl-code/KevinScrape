import io
import os
import re
import urllib.parse
import zipfile
from typing import List, Dict, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration & Page Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title=" Image Scraper MVP",
    page_icon="🖼️️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size:2.2rem;
        font-weight:700;
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size:1.0rem;
        color: #555555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Headers
st.markdown('<div class="main-header">🖼️ Web Image Scraper & Extractor</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Scrape, analyze, filter, and bulk-download images from any web page.</div>',
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Utility / Helper Functions
# -----------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def normalize_url(url: str) -> str:
    """Ensure URL has an explicit scheme (http:// or https://)."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_image_urls(target_url: str, headers: dict) -> List[str]:
    """Extract all image URLs from <img> tags and CSS background-images."""
    response = requests.get(target_url, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    image_urls = set()

    # 1. Extract standard <img> tags (src, data-src, srcset)
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-original", "srcset"]:
            src = img.get(attr)
            if src:
                # Handle srcset if present
                if " " in src and "," in src:
                    parts = src.split(",")
                    for part in parts:
                        part_url = part.strip().split(" ")[0]
                        if part_url:
                            image_urls.add(urllib.parse.urljoin(target_url, part_url))
                else:
                    image_urls.add(urllib.parse.urljoin(target_url, src.strip()))

    # 2. Extract CSS inline background-images
    style_tags = soup.find_all(style=True)
    for tag in style_tags:
        style = tag["style"]
        urls = re.findall(r"url\((['\"]?)(.*?)\1\)", style)
        for _, bg_url in urls:
            if not bg_url.startswith("data:"):
                image_urls.add(urllib.parse.urljoin(target_url, bg_url.strip()))

    return list(image_urls)


def fetch_image_metadata(img_url: str, headers: dict) -> Optional[Dict]:
    """Fetch an image and return its PIL Image object and metadata."""
    try:
        res = requests.get(img_url, headers=headers, timeout=8, stream=True)
        if res.status_code == 200:
            content_type = res.headers.get("Content-Type", "")
            if "image" not in content_type and not any(
                img_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"]
            ):
                return None

            raw_bytes = res.content
            size_kb = len(raw_bytes) / 1024

            # Attempt to parse with PIL
            try:
                img = Image.open(io.BytesIO(raw_bytes))
                width, height = img.size
                format_ext = (img.format or "UNKNOWN").upper()
            except Exception:
                # SVG or unparseable dynamic image
                width, height = 0, 0
                format_ext = img_url.split(".")[-1].split("?")[0].upper()

            filename = os.path.basename(urllib.parse.urlparse(img_url).path) or f"image_{hash(img_url)}.png"

            return {
                "url": img_url,
                "filename": filename,
                "bytes": raw_bytes,
                "width": width,
                "height": height,
                "size_kb": round(size_kb, 2),
                "format": format_ext,
            }
    except Exception:
        pass
    return None


def create_zip_file(images: List[Dict]) -> bytes:
    """Package filtered image dictionaries into a downloadable ZIP buffer."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        seen_filenames = set()
        for idx, img in enumerate(images):
            name = img["filename"]
            # Handle duplicate filenames safely
            if name in seen_filenames or not name:
                base, ext = os.path.splitext(name)
                ext = ext if ext else f".{img['format'].lower()}"
                name = f"{base or 'image'}_{idx}{ext}"
            seen_filenames.add(name)

            zip_file.writestr(name, img["bytes"])

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Scraper Controls")

url_input = st.sidebar.text_input(
    "Target Website URL",
    value="https://unsplash.com",
    placeholder="https://example.com",
)

custom_user_agent = st.sidebar.text_input(
    "Custom User-Agent (Optional)",
    value="",
    placeholder="Default Browser User-Agent",
)

scrape_button = st.sidebar.button("🚀 Start Scraping", use_container_width=True, type="primary")

st.sidebar.markdown("---")
st.sidebar.caption("💡 **Tip**: Some websites actively block automated scrapers. Use a realistic User-Agent if requests fail.")

# -----------------------------------------------------------------------------
# App State & Main Logic
# -----------------------------------------------------------------------------
if "scraped_images" not in st.session_state:
    st.session_state.scraped_images = None

if scrape_button and url_input:
    target_url = normalize_url(url_input)
    headers = DEFAULT_HEADERS.copy()
    if custom_user_agent.strip():
        headers["User-Agent"] = custom_user_agent.strip()

    with st.spinner(f"Fetching page source from {target_url}..."):
        try:
            raw_urls = extract_image_urls(target_url, headers)
            st.toast(f"Found {len(raw_urls)} potential image link(s)!", icon="🔍")
        except Exception as e:
            st.error(f"Failed to scrape webpage: {str(e)}")
            raw_urls = []

    if raw_urls:
        progress_bar = st.progress(0)
        status_text = st.empty()
        parsed_images = []

        for idx, img_url in enumerate(raw_urls):
            status_text.text(f"Downloading & Analyzing ({idx + 1}/{len(raw_urls)}): {img_url[:60]}...")
            meta = fetch_image_metadata(img_url, headers)
            if meta:
                parsed_images.append(meta)
            progress_bar.progress((idx + 1) / len(raw_urls))

        status_text.empty()
        progress_bar.empty()
        st.session_state.scraped_images = parsed_images
        st.success(f"Successfully processed {len(parsed_images)} active image assets!")


# -----------------------------------------------------------------------------
# Gallery & Filtering Interface
# -----------------------------------------------------------------------------
images = st.session_state.scraped_images

if images:
    st.subheader("📊 Filters & Analytics")

    # Metrics Summary
    m1, m2, m3, m4 = st.columns(4)
    total_imgs = len(images)
    total_size_mb = sum(img["size_kb"] for img in images) / 1024
    formats = list(set(img["format"] for img in images))

    m1.metric("Total Images", total_imgs)
    m2.metric("Total Data Size", f"{total_size_mb:.2f} MB")
    m3.metric("Formats Found", ", ".join(formats[:4]) if formats else "N/A")
    m4.metric("Avg File Size", f"{(total_size_mb * 1024 / (total_imgs or 1)):.1f} KB")

    st.markdown("---")

    # Filters Section
    f_col1, f_col2, f_col3 = st.columns([2, 2, 2])

    with f_col1:
        selected_formats = st.multiselect(
            "Filter by Format",
            options=formats,
            default=formats,
        )

    with f_col2:
        max_size = max([img["size_kb"] for img in images], default=100.0)
        min_kb, max_kb = st.slider(
            "Filter by File Size (KB)",
            min_value=0.0,
            max_value=float(max_size),
            value=(0.0, float(max_size)),
        )

    with f_col3:
        min_dim = st.number_input("Min Width (pixels)", min_value=0, value=0, step=50)

    # Apply Filters
    filtered_images = [
        img
        for img in images
        if img["format"] in selected_formats
        and min_kb <= img["size_kb"] <= max_kb
        and img["width"] >= min_dim
    ]

    # Bulk Download Section
    st.subheader(f"🖼️ Gallery ({len(filtered_images)} of {total_imgs} Images Shown)")

    if filtered_images:
        zip_data = create_zip_file(filtered_images)
        st.download_button(
            label=f"📦 Download Selected ({len(filtered_images)}) as .ZIP Archive",
            data=zip_data,
            file_name="scraped_images.zip",
            mime="application/zip",
            type="primary",
        )

        st.write("")

        # Image Grid View
        cols_per_row = 4
        cols = st.columns(cols_per_row)

        for idx, img in enumerate(filtered_images):
            col = cols[idx % cols_per_row]
            with col:
                st.image(img["bytes"], use_container_width=True)
                st.caption(f"**{img['filename'][:20]}**")
                st.text(f"Dim: {img['width']}x{img['height']} px\nFormat: {img['format']}\nSize: {img['size_kb']} KB")

                # Individual Download Button
                st.download_button(
                    label="⬇️ Download",
                    data=img["bytes"],
                    file_name=img["filename"],
                    mime=f"image/{img['format'].lower()}",
                    key=f"dl_{idx}",
                )
    else:
        st.info("No images match the currently applied filters.")

elif st.session_state.scraped_images is not None:
    st.warning("No downloadable images were discovered on the target page.")
else:
    st.info("👈 Enter a URL in the sidebar and click **Start Scraping** to begin.")
