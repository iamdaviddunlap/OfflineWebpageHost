import argparse
import collections
import logging
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- JavaScript for Bookmarking Feature ---
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

# --- HTML for Bookmarks Page ---
BOOKMARKS_HTML = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
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
    <ul id=\"bookmarks-list\"></ul>
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


INVALID_CHARS = re.compile(r'[<>:"\\|?*]')


def sanitize_path(path):
    """Replace characters that are invalid on Windows file systems."""
    return '/'.join(INVALID_CHARS.sub('_', part) for part in path.split('/'))

def save_file(content, directory, filename):
    """Save binary content to a file."""
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        logging.info(f"Skipping existing file: {path}")
        return True
    try:
        with open(path, 'wb') as f:
            f.write(content)
        logging.info(f"Saved file: {path}")
        return True
    except IOError as e:
        logging.error(f"Could not save file {path}: {e}")
        return False

def download_and_rewrite(url, session, output_dir, visited_urls, domain):
    """Download a single page, its assets, and rewrite links."""
    if url in visited_urls:
        return None, None
    visited_urls.add(url)
    logging.info(f"Crawling: {url}")

    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Failed to download {url}: {e}")
        return None, None

    soup = BeautifulSoup(response.content, 'html.parser')

    tags = {
        'img': 'src', 'link': 'href', 'script': 'src',
        'video': 'src', 'audio': 'src', 'source': 'src',
    }

    current_page_dir = os.path.dirname(os.path.join(output_dir, sanitize_path(urlparse(url).path.lstrip('/'))))

    for tag_name, attr in tags.items():
        for element in soup.find_all(tag_name, **{attr: True}):
            asset_url_raw = element[attr]
            asset_url = urljoin(url, asset_url_raw)

            if urlparse(asset_url).netloc != domain:
                continue

            parsed_asset_url = urlparse(asset_url)
            asset_path = sanitize_path(parsed_asset_url.path.lstrip('/'))
            if not asset_path:
                continue
            local_path = os.path.join(output_dir, asset_path)

            if not os.path.exists(local_path):
                try:
                    asset_response = session.get(asset_url, timeout=10)
                    asset_response.raise_for_status()
                    save_file(asset_response.content, os.path.dirname(local_path), os.path.basename(local_path))
                except requests.RequestException as e:
                    logging.warning(f"Failed to download asset {asset_url}: {e}")

            relative_path = os.path.relpath(local_path, start=current_page_dir)
            element[attr] = relative_path
            logging.info(f"Rewrote asset {asset_url_raw} to {relative_path}")

    page_path_part = sanitize_path(urlparse(url).path.lstrip('/'))
    if (not page_path_part or page_path_part.endswith('/') or
            not os.path.splitext(page_path_part)[1]):
        page_path_part = os.path.join(page_path_part.rstrip('/'), 'index.html')

    if soup.body:
        script_tag = soup.new_tag("script")
        script_tag.string = BOOKMARK_JS
        soup.body.append(script_tag)
        logging.info(f"Injected bookmarking script into {url}")

    new_links = []
    for link in soup.find_all('a', href=True):
        absolute_link = urljoin(url, link['href'])
        parsed_link = urlparse(absolute_link)
        if parsed_link.netloc == domain:
            if absolute_link not in visited_urls:
                new_links.append(absolute_link)
            link_path_part = sanitize_path(parsed_link.path.lstrip('/'))
            if (not link_path_part or link_path_part.endswith('/') or
                    not os.path.splitext(link_path_part)[1]):
                link_path_part = os.path.join(link_path_part.rstrip('/'), 'index.html')
            final_link_path = os.path.join(output_dir, link_path_part)
            relative_link = os.path.relpath(final_link_path, start=current_page_dir)
            link['href'] = relative_link

    save_file(
        soup.prettify('utf-8'),
        os.path.join(output_dir, os.path.dirname(page_path_part)),
        os.path.basename(page_path_part),
    )
    return new_links, page_path_part

def main():
    parser = argparse.ArgumentParser(description="Crawl and download a website for offline viewing.")
    parser.add_argument('--url', required=True, help="The starting URL of the website to crawl.")
    parser.add_argument('--path', required=True, help="The local directory to save the website content.")
    args = parser.parse_args()

    start_url = args.url
    output_dir = args.path
    domain = urlparse(start_url).netloc
    if not domain:
        logging.error("Invalid URL provided. Could not determine domain.")
        return

    session = requests.Session()
    session.headers.update({'User-Agent': 'Offline-Site-Archiver/1.0'})

    visited_urls = set()
    queue = collections.deque([start_url])

    while queue:
        current_url = queue.popleft()
        new_links, _ = download_and_rewrite(current_url, session, output_dir, visited_urls, domain)
        if new_links:
            queue.extend(new_links)

    save_file(BOOKMARKS_HTML.encode('utf-8'), output_dir, '_bookmarks.html')
    logging.info("Created _bookmarks.html page.")
    logging.info("Crawling finished.")

if __name__ == '__main__':
    main()
