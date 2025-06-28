Based on the detailed system architecture guide you provided, here is the complete implementation of the project for on-demand offline website archiving and Browse on iOS.

### **Project Overview**

This system allows you to archive a complete website and browse it offline on an iOS device using the a-Shell application. It is built on a "silently reliable" philosophy, embracing the temporary nature of iOS background processes to create a resource-efficient and robust solution.

The implementation consists of three core components as detailed in the guide:

1.  **A Crawler Engine (`crawl.py`):** A Python script that downloads a target website, including all assets like CSS, JavaScript, and images, and rewrites links for offline use.
2.  **An On-Demand Server (`server.py`):** A lightweight Bottle web server that serves the archived files. It runs only when you are actively Browse the site.
3.  **An Orchestrator (Apple Shortcuts):** Two Apple Shortcuts provide a user-friendly interface to run the crawler and the server without needing to manually type commands.

-----

## **I. Project Files**

Here are the complete Python scripts required for the project.

### **1. `bottle.py` Micro-framework**

This project requires the Bottle micro-framework. A key advantage of Bottle is that it's a single file with no dependencies beyond the Python Standard Library, which makes it ideal for the a-Shell environment.

**Action Required:**

1.  Download the `bottle.py` file from the [official Bottle website](https://bottlepy.org/bottle.py).
2.  Save this file in the same directory where you will place the `server.py` script.

### **2. `crawl.py` (Crawler Engine)**

This script recursively downloads a website and all its assets. It has been built using `requests` and `BeautifulSoup` for maximum reliability in the a-Shell environment, avoiding libraries with complex C-dependencies like `lxml`.

As specified in the implementation plan for advanced features, this version of the script has been enhanced to:

  * Inject a "Bookmark this page" button into every downloaded HTML page.
  * Generate a `_bookmarks.html` file to display saved bookmarks.

<!-- end list -->

```python
# crawl.py
import argparse
import collections
import logging
import os
import requests
from bs4 import BeautifulSoup, Comment
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def save_file(content, directory, filename):
    """Saves binary content to a file."""
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'wb') as f:
            f.write(content)
        logging.info(f"Saved file: {path}")
        return True
    except IOError as e:
        logging.error(f"Could not save file {path}: {e}")
        return False

def download_and_rewrite(url, session, output_dir, visited_urls, domain):
    """Downloads a single page, its assets, and rewrites links."""
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

    # Use built-in html.parser for reliability
    soup = BeautifulSoup(response.content, 'html.parser')

    # Define tags and their attributes to check for resources
    tags = {
        'img': 'src', 'link': 'href', 'script': 'src',
        'video': 'src', 'audio': 'src', 'source': 'src',
    }
    
    current_page_dir = os.path.dirname(os.path.join(output_dir, urlparse(url).path.lstrip('/')))

    for tag_name, attr in tags.items():
        for element in soup.find_all(tag_name, **{attr: True}):
            asset_url_raw = element[attr]
            asset_url = urljoin(url, asset_url_raw)

            if urlparse(asset_url).netloc != domain:
                continue # Skip external assets

            try:
                asset_response = session.get(asset_url, timeout=10)
                asset_response.raise_for_status()

                parsed_asset_url = urlparse(asset_url)
                asset_path = parsed_asset_url.path.lstrip('/')
                if not asset_path: continue

                local_path = os.path.join(output_dir, asset_path)
                
                if save_file(asset_response.content, os.path.dirname(local_path), os.path.basename(local_path)):
                    relative_path = os.path.relpath(local_path, start=current_page_dir)
                    element[attr] = relative_path # Rewrite the link in the HTML
                    logging.info(f"Rewrote asset {asset_url_raw} to {relative_path}")

            except requests.RequestException as e:
                logging.warning(f"Failed to download asset {asset_url}: {e}")

    page_path_part = urlparse(url).path.lstrip('/')
    if not page_path_part or page_path_part.endswith('/'):
        page_path_part = os.path.join(page_path_part, 'index.html')

    # Inject bookmarking script
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
            # Add to crawl queue if not visited
            if absolute_link not in visited_urls:
                new_links.append(absolute_link)

            # Rewrite internal page links
            link_path_part = parsed_link.path.lstrip('/')
            if not link_path_part or link_path_part.endswith('/'):
                link_path_part = os.path.join(link_path_part, 'index.html')
            
            final_link_path = os.path.join(output_dir, link_path_part)
            relative_link = os.path.relpath(final_link_path, start=current_page_dir)
            link['href'] = relative_link
    
    save_file(soup.prettify('utf-8'), os.path.join(output_dir, os.path.dirname(page_path_part)), os.path.basename(page_path_part))

    return new_links, page_path_part


def main():
    parser = argparse.ArgumentParser(description="Crawl and download a website for offline viewing.")
    parser.add_argument('--url', required=True, help="The starting URL of the website to crawl.") #
    parser.add_argument('--path', required=True, help="The local directory to save the website content.") #
    args = parser.parse_args()

    start_url = args.url
    output_dir = args.path
      
    domain = urlparse(start_url).netloc
    if not domain:
        logging.error("Invalid URL provided. Could not determine domain.")
        return

    session = requests.Session()
    session.headers.update({'User-Agent': 'Offline-Site-Archiver/1.0'})
      
    visited_urls = set() #
    queue = collections.deque([start_url]) #

    while queue:
        current_url = queue.popleft()
        new_links, _ = download_and_rewrite(current_url, session, output_dir, visited_urls, domain)
        if new_links:
            queue.extend(new_links)
    
    # Create the bookmarks page
    save_file(BOOKMARKS_HTML.encode('utf-8'), output_dir, '_bookmarks.html')
    logging.info("Created _bookmarks.html page.")
      
    logging.info("Crawling finished.")

if __name__ == "__main__":
    main()
```

### **3. `server.py` (On-Demand Server)**

This script runs a lightweight web server using the Bottle framework. It serves the static files of the archived website and provides API endpoints for the bookmarking feature. Its zero-dependency nature makes it exceptionally reliable.

```python
# server.py
import argparse
import os
import json
from bottle import Bottle, run, static_file, request, response

# --- BOOKMARKING FEATURE LOGIC ---
BOOKMARKS_FILE = 'bookmarks.json'

def get_bookmarks_path(root_path):
    """Constructs the absolute path to the bookmarks file."""
    return os.path.join(root_path, BOOKMARKS_FILE)

def load_bookmarks(root_path):
    """Loads bookmarks from the JSON file."""
    bookmarks_path = get_bookmarks_path(root_path)
    if not os.path.exists(bookmarks_path):
        return []
    try:
        with open(bookmarks_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return []

def save_bookmarks(bookmarks, root_path):
    """Saves bookmarks to the JSON file."""
    bookmarks_path = get_bookmarks_path(root_path)
    try:
        with open(bookmarks_path, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, indent=4)
        return True
    except IOError:
        return False

# --- BOTTLE APPLICATION ---
app = Bottle()

# --- API Endpoints for Bookmarking ---
@app.route('/api/bookmarks', method='GET')
def get_bookmarks_api(root_path):
    """API endpoint to retrieve all bookmarks."""
    response.content_type = 'application/json'
    bookmarks = load_bookmarks(root_path)
    return json.dumps(bookmarks)

@app.route('/api/add_bookmark', method='POST')
def add_bookmark_api(root_path):
    """API endpoint to add a new bookmark."""
    try:
        data = request.json
        if not data or 'title' not in data or 'url' not in data:
            response.status = 400
            return {'error': 'Invalid payload'}
        
        bookmarks = load_bookmarks(root_path)
        # Avoid duplicate bookmarks
        if not any(b['url'] == data['url'] for b in bookmarks):
            bookmarks.append({'title': data['title'], 'url': data['url']})
            if save_bookmarks(bookmarks, root_path):
                response.status = 201
                return {'status': 'success'}
            else:
                response.status = 500
                return {'error': 'Failed to save bookmarks'}
        else:
            return {'status': 'success', 'message': 'Bookmark already exists'}

    except Exception as e:
        response.status = 500
        return {'error': str(e)}

# --- Static File Server ---
@app.route('/<filepath:path>')
def server_static(filepath, root_path):
    """Serves all static files from the archived site directory."""
    # Default to index.html for directories
    if filepath.endswith('/'):
        filepath += 'index.html'
    if not os.path.splitext(filepath)[1]:
        filepath = os.path.join(filepath, 'index.html')
    
    return static_file(filepath, root=root_path)

@app.route('/')
def server_root(root_path):
    """Serves the root index.html file."""
    return static_file('index.html', root=root_path)


def main():
    parser = argparse.ArgumentParser(description="Lightweight web server for Browse offline sites.")
    parser.add_argument('--path', required=True, help="The root directory of the archived website to serve.")
    parser.add_argument('--port', type=int, default=8080, help="The port to run the server on.")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"Error: Directory not found at {args.path}")
        return

    # Pass the root path to the request handlers
    app.config['root_path'] = args.path
    
    # Update routes to pass root_path from config
    app.route('/<filepath:path>')(lambda filepath: server_static(filepath, root_path=app.config['root_path']))
    app.route('/')(lambda: server_root(root_path=app.config['root_path']))
    app.get('/api/bookmarks')(lambda: get_bookmarks_api(root_path=app.config['root_path']))
    app.post('/api/add_bookmark')(lambda: add_bookmark_api(root_path=app.config['root_path']))

    print(f"Starting server for {args.path} on http://localhost:{args.port}")
    # 'quiet=True' prevents server logs from cluttering the terminal
    run(app, host='localhost', port=args.port, quiet=True)

if __name__ == "__main__":
    main()
```

-----

## **II. Setup and Orchestration**

Follow these steps to set up the scripts and configure Apple Shortcuts for easy use.

### **1. Directory Structure**

Inside the a-Shell app's file system, create the following directory structure within `~/Documents`:

```
~/Documents/
|-- offline-archiver/
|   |-- crawl.py
|   |-- server.py
|   |-- bottle.py
|
|-- archives/
    |-- (Archived websites will be saved here)
```

1.  Create a folder named `offline-archiver`. Place the `crawl.py`, `server.py`, and the downloaded `bottle.py` files inside it.
2.  Create an empty folder named `archives`. This is where the crawler will store the downloaded websites.

### **2. Apple Shortcuts Configuration**

These shortcuts act as the control panel for the system.

#### **Shortcut 1: "Archive New Website"**

This shortcut prompts you for a URL and a name, then runs the `crawl.py` script.

1.  Open the **Shortcuts** app and create a new shortcut.
2.  Add an **Ask for Input** action. Set the prompt to "Enter the full URL of the website to archive."
3.  Add a second **Ask for Input** action. Set the prompt to "Enter a project name for this archive (e.g., python-docs)."
4.  Add a **Run Shell Script** action.
      * Ensure it's configured to run in **a-Shell**.
      * In the script body, enter the following command precisely. It uses the variables from the previous steps.
        ```bash
        cd offline-archiver
        python3 crawl.py --url "Shortcut Input 1" --path "~/Documents/archives/Shortcut Input 2"
        ```
5.  Name the shortcut **Archive New Website** and save it.

#### **Shortcut 2: "Browse Offline Site"**

This shortcut lets you pick an archived site, starts the local server in the background, and opens Safari.

1.  Create a new shortcut in the **Shortcuts** app.
2.  Add a **Get File** action.
      * Toggle on "Show Document Picker".
      * Set the "Default Path" to `archives`.
      * Toggle on "Select a Directory".
3.  Add a **Run Shell Script** action.
      * Configure it to run in **a-Shell**.
      * Enter the following command. The `&` runs the server as a background job, and `>/dev/null 2>&1` silences its output.
        ```bash
        cd offline-archiver
        python3 server.py --path "Shortcut Input" &> /dev/null &
        ```
4.  Add an **Open URL** action. Set the URL to `http://localhost:8080`.
5.  Name the shortcut **Browse Offline Site** and save it.

-----

## **III. How to Use the System**

1.  **To Archive a Site:**

      * Run the **"Archive New Website"** shortcut.
      * Enter the full URL when prompted (e.g., `https://docs.python.org/3/`).
      * Provide a simple name for the local directory (e.g., `python-docs`).
      * a-Shell will open and you will see the crawler's progress logs. Wait for it to complete.

2.  **To Browse a Site:**

      * Run the **"Browse Offline Site"** shortcut.
      * The file picker will appear. Navigate into the `archives` folder and select the directory of the site you want to view.
      * Safari will open automatically to the homepage of your offline archive.
      * You can now browse the site, add bookmarks using the button at the bottom-right, or view all your bookmarks by navigating to `http://localhost:8080/_bookmarks.html`.

The server process starts on-demand and is automatically terminated by iOS when a-Shell is closed or suspended for a long period, ensuring zero resource usage when inactive.