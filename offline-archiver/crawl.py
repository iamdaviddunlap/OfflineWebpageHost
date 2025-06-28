import argparse
import collections
import json
import logging
import os
import re
import requests
import sqlite3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Constants for bookmarking feature ---
BOOKMARK_JS = """
document.addEventListener('DOMContentLoaded', () => {
    const bookmarkBtn = document.createElement('button');
    bookmarkBtn.textContent = 'Bookmark this Page';
    bookmarkBtn.style.position = 'fixed';
    bookmarkBtn.style.bottom = '10px';
    bookmarkBtn.style.right = '10px';
    bookmarkBtn.style.zIndex = '9999';
    bookmarkBtn.style.padding = '10px';
    bookmarkBtn.style.backgroundColor = '#007bff';
    bookmarkBtn.style.color = 'white';
    bookmarkBtn.style.border = 'none';
    bookmarkBtn.style.borderRadius = '5px';
    bookmarkBtn.style.cursor = 'pointer';
    document.body.appendChild(bookmarkBtn);

    bookmarkBtn.addEventListener('click', () => {
        const pageTitle = document.title;
        const pageUrl = window.location.pathname;
        fetch('/api/add_bookmark', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: pageTitle, url: pageUrl }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Bookmark added!');
            } else {
                alert('Error: ' + (data.error || 'Could not add bookmark.'));
            }
        })
        .catch(error => {
            console.error('Error adding bookmark:', error);
            alert('Failed to add bookmark.');
        });
    });
});
"""
BOOKMARKS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookmarks</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 2em; color: #333; }
        h1 { color: #000; }
        ul { list-style-type: none; padding: 0; }
        li { margin-bottom: 1em; background-color: #f0f0f0; padding: 10px; border-radius: 5px;}
        a { text-decoration: none; color: #007bff; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>My Bookmarks</h1>
    <ul id="bookmarks-list"></ul>
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const listElement = document.getElementById('bookmarks-list');
            fetch('/api/bookmarks')
                .then(response => response.json())
                .then(bookmarks => {
                    if (bookmarks && bookmarks.length > 0) {
                        bookmarks.forEach(bookmark => {
                            const listItem = document.createElement('li');
                            const link = document.createElement('a');
                            link.href = bookmark.url;
                            link.textContent = bookmark.title;
                            listItem.appendChild(link);
                            listElement.appendChild(listItem);
                        });
                    } else {
                        listElement.innerHTML = '<li>No bookmarks yet.</li>';
                    }
                })
                .catch(error => {
                    console.error('Error fetching bookmarks:', error);
                    listElement.innerHTML = '<li>Error loading bookmarks.</li>';
                });
        });
    </script>
</body>
</html>
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Regex patterns ---
STYLE_URL_REGEX = re.compile(r'url\s*\(([^)]+)\)')
IMPORT_URL_REGEX = re.compile(r'@import\s+(?:url\(([^)]+)\)|"([^"]+)"|\'([^\']+)\');')
INVALID_CHARS = re.compile(r'[<>:"\\|?*]')
STATE_FILE = 'crawl_state.json'
BOOKMARKS_DB = 'bookmarks.db'
MAX_PATH_LENGTH = 240


def sanitize_path(path):
    """Sanitize a path component for file system saving."""
    sanitized = INVALID_CHARS.sub('_', path)
    if len(sanitized) > MAX_PATH_LENGTH:
        logging.warning(f"Sanitized path part is very long: {sanitized[:60]}...")
    return sanitized


def normalize_url(url, args):
    """Normalizes a URL by stripping fragment and optionally the query string."""
    if args.ignore_query:
        url = url.split('?')[0]
    return url.split('#')[0]


def load_state(output_dir, start_url):
    """Load crawl state if it exists, otherwise return empty state."""
    state_path = os.path.join(output_dir, STATE_FILE)
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('start_url') == start_url:
                visited = set(data.get('visited', []))
                queue = collections.deque(data.get('queue', []))
                logging.info('Resuming previous crawl session.')
                return visited, queue
        except (IOError, json.JSONDecodeError) as e:
            logging.warning(f'Could not load state file: {e}')
    return set(), collections.deque([start_url])


def save_state(output_dir, start_url, visited_urls, queue):
    """Persist crawl state to disk."""
    state_path = os.path.join(output_dir, STATE_FILE)
    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({
                'start_url': start_url,
                'visited': list(visited_urls),
                'queue': list(queue)
            }, f, indent=4)
        logging.info("Crawl state saved.")
    except IOError as e:
        logging.warning(f'Failed to write state file: {e}')


def save_file(content, directory, filename):
    """Save binary content to a file."""
    path = os.path.join(directory, filename)
    if len(path) > MAX_PATH_LENGTH:
        logging.warning(f"Full path is long and may not work on Windows: {path}")

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(content)
        return True
    except IOError as e:
        logging.error(f"Could not save file {path}: {e}")
        return False


def get_page_path_from_url(url, output_dir):
    """
    Generates a local file path for a navigable page URL.
    Correctly appends 'index.html' for directory-like URLs.
    """
    parsed_url = urlparse(url)

    # Sanitize all parts of the path from the start.
    path_parts = [sanitize_path(part) for part in parsed_url.path.strip('/').split('/') if part]

    if not path_parts:
        return os.path.join(output_dir, 'index.html')

    # Determine if the URL path's last component is a directory or a file.
    last_part = parsed_url.path.strip('/').split('/')[-1]
    if parsed_url.path.endswith('/') or '.' not in last_part:
        # If it's a directory (ends in /) or has no extension, append index.html.
        path_parts.append('index.html')

    # If it has an extension, the sanitized path_parts list is already correct.
    return os.path.join(output_dir, *path_parts)


def get_asset_path_from_url(url, output_dir):
    """
    FIX: Generates a local file path for an asset URL.
    Does NOT append 'index.html', preserving the original filename.
    """
    parsed_url = urlparse(url)
    path_components = [sanitize_path(part) for part in parsed_url.path.strip('/').split('/') if part]
    if not path_components:
        # Edge case for a URL like "http://example.com" used as an asset source.
        # We'll use the domain name as the filename.
        sanitized_domain = sanitize_path(parsed_url.netloc)
        return os.path.join(output_dir, sanitized_domain)

    return os.path.join(output_dir, *path_components)


def process_css_content(css_content, css_url, session, output_dir, domain, args):
    """Parses CSS content, downloads referenced assets, and rewrites paths."""
    # FIX: Use get_asset_path_from_url for assets.
    css_local_path = get_asset_path_from_url(css_url, output_dir)
    css_dir = os.path.dirname(css_local_path)

    def process_match(match, base_url):
        url_part = next((g for g in match.groups() if g is not None), None)
        if not url_part or not url_part.strip() or url_part.startswith(('data:', '#')):
            return match.group(0)

        asset_url_raw = url_part.strip('\'"')
        asset_url = urljoin(base_url, asset_url_raw)

        if urlparse(asset_url).netloc == domain:
            # FIX: Use get_asset_path_from_url for assets.
            asset_local_path = get_asset_path_from_url(asset_url, output_dir)
            download_asset(asset_url, session, asset_local_path, args)
            relative_path = os.path.relpath(asset_local_path, start=css_dir).replace('\\', '/')

            if match.re == IMPORT_URL_REGEX:
                return f"@import url('{relative_path}');"
            else:
                return f"url('{relative_path}')"

        return match.group(0)

    processed_imports = IMPORT_URL_REGEX.sub(lambda m: process_match(m, css_url), css_content)
    final_css = STYLE_URL_REGEX.sub(lambda m: process_match(m, css_url), processed_imports)

    return final_css


def download_asset(asset_url, session, local_path, args):
    """Download a single asset."""
    if os.path.exists(local_path):
        return "exists"
    try:
        asset_response = session.get(asset_url, timeout=args.timeout, stream=True)

        # FIX: Gracefully handle 404 errors for assets, as many sites have broken links.
        if asset_response.status_code == 404:
            logging.info(f"Asset not found (404), skipping: {asset_url}")
            return None  # Silently skip this asset

        # For any other error (500, 403, etc.), raise an exception to see the warning.
        asset_response.raise_for_status()

        save_file(asset_response.content, os.path.dirname(local_path), os.path.basename(local_path))
        logging.info(f"Downloaded asset: {asset_url}")
        return asset_response
    except requests.RequestException as e:
        logging.warning(f"Failed to download asset {asset_url}: {e}")
        return None


def rewrite_asset_path(element, attr, url, domain, session, output_dir, current_page_dir, args):
    """Helper to download and rewrite a single asset path."""
    asset_url_raw = element.get(attr)
    if not asset_url_raw or not asset_url_raw.strip() or asset_url_raw.startswith(('data:', 'mailto:', 'tel:')):
        return

    asset_url = urljoin(url, asset_url_raw)
    if urlparse(asset_url).netloc != domain:
        return

    # FIX: Use get_asset_path_from_url for assets.
    local_path = get_asset_path_from_url(asset_url, output_dir)
    asset_response = download_asset(asset_url, session, local_path, args)

    is_stylesheet = element.name == 'link' and 'stylesheet' in element.get('rel', [])
    if asset_response and asset_response != "exists" and is_stylesheet:
        logging.info(f"Processing CSS file: {asset_url}")
        try:
            encoding = asset_response.encoding or 'utf-8'
            content = asset_response.content.decode(encoding, errors='ignore')
            modified_css = process_css_content(content, asset_url, session, output_dir, domain, args)
            save_file(modified_css.encode('utf-8'), os.path.dirname(local_path), os.path.basename(local_path))
        except Exception as e:
            logging.error(f"Failed to process CSS content for {asset_url}: {e}")

    relative_path = os.path.relpath(local_path, start=current_page_dir).replace('\\', '/')
    element[attr] = relative_path


def download_and_rewrite(url, session, output_dir, visited_urls, queue, domain, args):
    """Download a single page, its assets, and rewrite links."""
    norm_url = normalize_url(url, args)
    if norm_url in visited_urls:
        return None
    logging.info(f"Crawling: {url}")

    try:
        response = session.get(url, timeout=args.timeout)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower().strip()

        if not content_type.startswith('text/html'):
            logging.info(f"Saving non-HTML content at {url} ({content_type})")
            # FIX: Use get_asset_path_from_url for non-HTML content.
            local_path = get_asset_path_from_url(url, output_dir)
            download_asset(url, session, local_path, args)
            visited_urls.add(norm_url)
            return None

        final_url = normalize_url(response.url, args)
        visited_urls.add(norm_url)
        if final_url != norm_url:
            visited_urls.add(final_url)

        html_content = response.content
    except requests.RequestException as e:
        logging.error(f"Failed to download {url}: {e}")
        visited_urls.add(norm_url)
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    # FIX: Use get_page_path_from_url for the main page.
    local_page_path = get_page_path_from_url(url, output_dir)
    current_page_dir = os.path.dirname(local_page_path)

    tags = {'img': 'src', 'link': 'href', 'script': 'src', 'video': 'src', 'audio': 'src', 'source': 'src',
            'iframe': 'src'}
    for tag_name, attr in tags.items():
        for element in soup.find_all(tag_name, **{attr: True}):
            rewrite_asset_path(element, attr, url, domain, session, output_dir, current_page_dir, args)

    for element in soup.find_all(['img', 'source'], srcset=True):
        best_candidate = {'url': None, 'value': -1}
        for src_candidate in element['srcset'].split(','):
            parts = src_candidate.strip().split()
            if not parts: continue
            asset_url_part = parts[0]
            if not asset_url_part: continue
            descriptor = parts[1] if len(parts) > 1 else '1x'
            value = 0
            if descriptor.endswith('w'):
                try:
                    value = int(descriptor[:-1])
                except ValueError:
                    continue
            elif descriptor.endswith('x'):
                try:
                    value = int(float(descriptor[:-1])) * 1000
                except ValueError:
                    continue
            if value > best_candidate['value']:
                best_candidate = {'url': asset_url_part, 'value': value}

        if best_candidate['url']:
            asset_url = urljoin(url, best_candidate['url'])
            if urlparse(asset_url).netloc == domain:
                # FIX: Use get_asset_path_from_url for assets.
                local_path = get_asset_path_from_url(asset_url, output_dir)
                download_asset(asset_url, session, local_path, args)
                relative_path = os.path.relpath(local_path, start=current_page_dir).replace('\\', '/')
                element['srcset'] = relative_path
                if element.name == 'img':
                    element['src'] = relative_path

    for element in soup.find_all(style=True):
        original_style = element['style']
        rewritten_style = process_css_content(original_style, url, session, output_dir, domain, args)
        if original_style != rewritten_style:
            element['style'] = rewritten_style

    if soup.body:
        script_tag = soup.new_tag("script")
        script_tag.string = BOOKMARK_JS
        soup.body.append(script_tag)

    new_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if not href.strip() or href.startswith(('#', 'data:', 'mailto:', 'tel:')):
            continue

        absolute_link = urljoin(url, href)
        if urlparse(absolute_link).netloc == domain:
            normalized_link = normalize_url(absolute_link, args)
            if normalized_link not in visited_urls and normalized_link not in queue:
                new_links.append(absolute_link)

            # FIX: Use get_page_path_from_url for navigation links.
            final_link_path = get_page_path_from_url(absolute_link, output_dir)
            relative_link = os.path.relpath(final_link_path, start=current_page_dir).replace('\\', '/')
            link['href'] = relative_link

    save_file(soup.prettify('utf-8'), os.path.dirname(local_page_path), os.path.basename(local_page_path))
    return new_links


def init_db(root_path):
    """Initialize the SQLite database for bookmarks."""
    db_path = os.path.join(root_path, BOOKMARKS_DB)
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
        con.close()
        logging.info(f"Bookmark database initialized at {db_path}")
    except sqlite3.Error as e:
        logging.error(f"Database error during initialization: {e}")


def main():
    parser = argparse.ArgumentParser(description="Crawl and download a website for offline viewing.")
    parser.add_argument('url', help="The starting URL of the website to crawl.")
    parser.add_argument('path', help="The local directory to save the website content.")
    parser.add_argument('--ignore-query', action='store_true',
                        help="Ignore URL query strings to avoid duplicate page downloads.")
    parser.add_argument('--timeout', type=int, default=15,
                        help="Timeout in seconds for network requests.")
    args = parser.parse_args()

    start_url = args.url
    output_dir = args.path
    os.makedirs(output_dir, exist_ok=True)

    domain = urlparse(start_url).netloc
    if not domain:
        logging.error("Invalid URL provided. Could not determine domain.")
        return

    init_db(output_dir)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    visited_urls, queue = load_state(output_dir, start_url)
    crawl_count = 0
    crawl_interrupted = True

    try:
        while queue:
            current_url = queue.popleft()
            new_links = download_and_rewrite(current_url, session, output_dir, visited_urls, queue, domain, args)

            if new_links:
                for link in new_links:
                    if normalize_url(link, args) not in visited_urls and link not in queue:
                        queue.append(link)

            crawl_count += 1
            if crawl_count % 20 == 0:
                save_state(output_dir, start_url, visited_urls, queue)
        crawl_interrupted = False
    finally:
        if crawl_interrupted:
            logging.info("Crawl interrupted. Saving final state.")
            save_state(output_dir, start_url, visited_urls, queue)
        else:
            logging.info("Crawl finished successfully.")
            state_path = os.path.join(output_dir, STATE_FILE)
            if os.path.exists(state_path):
                try:
                    os.remove(state_path)
                    logging.info(f"Removed state file: {state_path}")
                except OSError as e:
                    logging.error(f"Could not remove state file {state_path}: {e}")

        save_file(BOOKMARKS_HTML.encode('utf-8'), output_dir, '_bookmarks.html')
        logging.info("Created/Updated _bookmarks.html page.")


if __name__ == '__main__':
    main()
