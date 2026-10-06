import io
import re
import os
import zipfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="VisualGrab - Image Scraper",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for UI styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        color: #64748B;
        margin-bottom: 2rem;
    }
    .stCard {
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 10px;
        background-color: #FFFFFF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .metric-container {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #E2E8F0;
    }
</style>
""", unsafe_allow_html=True)

# Helper Functions
def is_valid_url(url):
    """Check if the provided URL has a valid schema and network location."""
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

def extract_image_urls(target_url, headers):
    """Fetch target web page and parse image sources from <img> tags and styles."""
    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Failed to fetch page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    image_urls = set()

    # 1. Standard <img> src tags
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if src:
            image_urls.add(urljoin(target_url, src))

        # Check srcset
        srcset = img.get('srcset')
        if srcset:
            parts = srcset.split(',')
            for part in parts:
                url_part = part.strip().split(' ')[0]
                if url_part:
                    image_urls.add(urljoin(target_url, url_part))

    # 2. Extract CSS inline background images
    style_tags = soup.find_all(style=True)
    for tag in style_tags:
        style = tag['style']
        urls = re.findall(r'url\(([\'"]?.*?[\'"]?)\)', style)
        for u in urls:
            u = u.strip('\'"')
            if u and not u.startswith('data:'):
                image_urls.add(urljoin(target_url, u))

    return list(image_urls)

def process_and_filter_image(img_url, headers, min_width, min_height, keyword_filter):
    """Download, inspect, and filter individual image."""
    if keyword_filter and keyword_filter.lower() not in img_url.lower():
        return None

    try:
        res = requests.get(img_url, headers=headers, timeout=5, stream=True)
        if res.status_code == 200:
            content_type = res.headers.get('content-type', '')
            if 'image' in content_type or any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg']):
                img_data = res.content
                img = Image.open(io.BytesIO(img_data))
                width, height = img.size

                if width >= min_width and height >= min_height:
                    return {
                        'url': img_url,
                        'bytes': img_data,
                        'width': width,
                        'height': height,
                        'format': img.format or 'PNG',
                        'size_kb': round(len(img_data) / 1024, 1)
                    }
    except Exception:
        pass
    return None

# App Sidebar Setup
st.sidebar.title("⚙️ Scraper Settings")

# User Agent Header configuration
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

# Target URL Input
target_url = st.sidebar.text_input("Target Website URL", placeholder="https://example.com")

st.sidebar.subheader("Filter Rules")
min_width = st.sidebar.number_input("Minimum Width (px)", min_value=0, value=100, step=50)
min_height = st.sidebar.number_input("Minimum Height (px)", min_value=0, value=100, step=50)
keyword_filter = st.sidebar.text_input("URL Keyword Filter", placeholder="e.g., product, hero, thumb")

max_images = st.sidebar.slider("Maximum Images to Scrape", min_value=5, max_value=100, value=30)

start_scrape = st.sidebar.button("🚀 Start Scraping", use_container_width=True, type="primary")

# Main Interface Layout
st.markdown("<div class='main-title'>🖼️ VisualGrab - Live Web Image Scraper</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Extract, inspect, filter, and batch download images from any website URL.</div>", unsafe_allow_html=True)

# Main Application Logic
if start_scrape:
    if not target_url or not is_valid_url(target_url):
        st.warning("Please enter a valid URL (e.g., starting with https:// or http://).")
    else:
        with st.spinner("Analyzing web page and gathering image links..."):
            raw_urls = extract_image_urls(target_url, headers)

        if not raw_urls:
            st.info("No images were found on the provided page. The site might block automated scripts or rely on JavaScript rendering.")
        else:
            st.write(f"Found **{len(raw_urls)}** prospective image sources. Downloading and applying filters...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            processed_images = []
            
            for idx, url in enumerate(raw_urls[:max_images]):
                status_text.text(f"Processing image {idx + 1} of {min(len(raw_urls), max_images)}...")
                result = process_and_filter_image(url, headers, min_width, min_height, keyword_filter)
                if result:
                    processed_images.append(result)
                progress_bar.progress((idx + 1) / min(len(raw_urls), max_images))

            status_text.empty()
            progress_bar.empty()

            st.session_state['scraped_images'] = processed_images
            st.session_state['target_url'] = target_url

# Results Display Section
if 'scraped_images' in st.session_state and st.session_state['scraped_images']:
    images = st.session_state['scraped_images']
    
    # Key Dashboard Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Scraped Images Passed Filters", value=len(images))
    with col2:
        total_size = sum(img['size_kb'] for img in images) / 1024
        st.metric(label="Total Size", value=f"{total_size:.2f} MB")
    with col3:
        avg_res = int(sum(img['width'] for img in images) / len(images)) if images else 0
        st.metric(label="Avg Image Width", value=f"{avg_res} px")

    st.markdown("---")

    # ZIP File Generation for Batch Download
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for idx, img in enumerate(images):
            ext = img['format'].lower() if img['format'] else 'png'
            filename = f"image_{idx + 1}.{ext}"
            zip_file.writestr(filename, img['bytes'])
    
    zip_buffer.seek(0)

    # Download All Action
    st.download_button(
        label="📦 Download All Images as ZIP",
        data=zip_buffer,
        file_name="scraped_images.zip",
        mime="application/zip",
        type="primary"
    )

    st.subheader("Image Gallery")
    
    # Display Gallery in 3 Columns
    grid_cols = st.columns(3)
    for idx, img in enumerate(images):
        col = grid_cols[idx % 3]
        with col:
            st.image(img['bytes'], use_column_width=True)
            st.caption(f"**Resolution:** {img['width']}x{img['height']} px | **Size:** {img['size_kb']} KB")
            
            # Single Image Download Button
            ext = img['format'].lower() if img['format'] else 'png'
            st.download_button(
                label=f"⬇️ Download #{idx + 1}",
                data=img['bytes'],
                file_name=f"scraped_img_{idx + 1}.{ext}",
                mime=f"image/{ext}",
                key=f"dl_{idx}"
            )
            st.markdown("<br>", unsafe_allow_html=True)

elif 'scraped_images' in st.session_state and not st.session_state['scraped_images']:
    st.info("No images matched your current width, height, or keyword filter criteria.")
