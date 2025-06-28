

# **A System Architecture for On-Demand Offline Website Archiving and Browsing in a Constrained Mobile Environment**

## **I. Executive Summary and Architectural Overview**

### **1.1. Project Synopsis**

This report details the system architecture and implementation plan for a software solution designed to archive and browse websites offline within the a-Shell application environment on iOS. The primary objective is to create a robust, user-friendly system that allows for the comprehensive crawling of a target website, the downloading of all its constituent pages and assets, and subsequent offline browsing in a standard web browser like Safari. The proposed solution is engineered with a core focus on what the user has termed "silently reliable" operation, acknowledging the unique constraints of the mobile operating system and the user's need for a seamless, app-like experience facilitated by Apple Shortcuts.

### **1.2. The Core Architectural Challenge: The Illusion of Persistence on iOS**

The most critical constraint governing this project's design is the process lifecycle management enforced by Apple's iOS. To preserve battery life, system resources, and user privacy, iOS imposes strict limitations on background execution for third-party applications.1 When an app like a-Shell moves to the background, it is typically suspended, meaning it receives no CPU time. The system can, and frequently does, terminate suspended apps with little to no warning to reclaim memory or other resources for the foreground application.3  
This fundamental principle of iOS process management is in direct conflict with the conventional model of a persistent, always-on web server. The user's desire for a server that is "silently reliable" and does not need to be "restarted at random times" cannot be met by any architecture that attempts to run a process indefinitely in the background. Official APIs for long-running background tasks are tailored for specific use cases like audio playback or location updates and are not applicable here; there is no sanctioned method for a standard application to maintain an arbitrary, persistent server process.3 Any attempt to circumvent these limitations with "keep-alive" workarounds would be fragile, unreliable, and would lead to excessive battery drain—the exact opposite of the desired outcome.  
Therefore, true reliability on this platform can only be achieved by embracing the ephemeral nature of its processes, not by fighting it. The system must be designed to function perfectly under the assumption that its server component is not, and should not be, running at all times. This leads to a necessary architectural shift away from a persistent server model and towards an **on-demand server model**. The server should only be launched when the user actively initiates a browsing session and should be designed to be gracefully terminated by the system when the session is over. This principle is the cornerstone of the proposed reliable architecture.

### **1.3. The Three-Component Architecture**

Based on the on-demand principle, a three-component architecture is proposed to meet the project's goals:

1. **The Crawler Engine:** A Python script responsible for the one-time, heavyweight task of downloading and processing a target website. This component is invoked via a dedicated Apple Shortcut, runs to completion in the foreground of the a-Shell process, and then terminates.  
2. **The On-Demand Local Server:** A lightweight Python web server. This component is explicitly designed *not* to be always running. It is launched by a separate "Browse" Shortcut immediately before opening Safari. It runs as a background job within the shell *only for the duration of the active browsing session*. Its standard output and error streams are redirected to /dev/null to prevent them from cluttering the interactive terminal.6  
3. **The Shortcut Orchestrator:** A set of user-facing Apple Shortcuts that act as the control plane for the entire system. These Shortcuts manage the execution of the Crawler and Server scripts, passing necessary parameters such as target URLs and local file paths, thereby providing the desired "app-like" user experience.

## **II. The Crawler Engine: A Deep Dive into Implementation Strategies**

### **2.1. Defining the Ideal Crawler**

The crawler is the heart of the archiving process. Its primary responsibilities are to recursively discover all internal hyperlinks within a specified domain, download the corresponding HTML pages, identify and download all associated assets (CSS, JavaScript, images, fonts, etc.), and, most critically, rewrite all links within the saved HTML files to use relative paths, ensuring they function correctly in an offline context. This entire process must be executable within the specific environment provided by a-Shell on iOS.

### **2.2. Strategy A: The Turnkey Solution (pywebcopy)**

A preliminary analysis might suggest using a high-level, specialized library like pywebcopy. This library is purpose-built to "clone/archive pages or sites" and offers a simple API, save\_website, that promises to handle the entire process of scanning, downloading, and remapping links automatically.7 This approach appears to offer maximum convenience with minimal coding effort.  
However, a deeper investigation reveals two critical limitations that make this strategy unsuitable for the target environment. First, the library's documentation explicitly states: "PyWebCopy does not include a virtual DOM or any form of JavaScript parsing".7 This is a severe deficiency in the modern web, where a significant number of websites rely on JavaScript to dynamically generate content and links, which  
pywebcopy would be unable to discover.9  
Second, and more decisively, is the library's dependency profile. pywebcopy relies on several other packages, including lxml.7 The  
lxml library is not pure Python; it is a C-based extension that provides bindings to the libxml2 and libxslt libraries. Installing lxml from source using pip requires a C compiler toolchain and the corresponding system-level development header files (e.g., libxml2-dev, libxslt-dev).13 While a-Shell commendably includes the  
clang compiler 16, the sandboxed nature of an iOS application makes the installation of system-level development headers highly problematic, if not impossible. An attempt to  
pip install lxml is therefore very likely to fail.  
This reveals the hidden cost of convenience. While a library like pywebcopy simplifies development in a standard desktop environment, its reliance on complex, non-Python dependencies transforms that convenience into a significant liability in a constrained environment like a-Shell. The high probability of a failed installation makes this strategy architecturally unsound and unreliable.

### **2.3. Strategy B: The Custom-Built Crawler (Requests \+ BeautifulSoup)**

A more robust and reliable strategy involves constructing a custom crawler using two well-established and minimally-dependent Python libraries: requests for handling HTTP operations and BeautifulSoup for HTML parsing.17  
This approach provides complete control over the crawling and processing logic:

* **Crawling:** The process begins with a queue seeded with the user-provided root URL. The script fetches a URL from the queue, parses its HTML content to discover all \<a\> tags, and adds any new, same-domain URLs back into the queue for subsequent processing.  
* **Asset Discovery and Downloading:** For each downloaded page, BeautifulSoup is used to find all tags that reference external resources, such as \<link\> for CSS, \<script\> for JavaScript, and \<img\>, \<video\>, and \<source\> for media.19 The  
  requests library is then used to download each of these assets into a structured local directory (e.g., css/, js/, images/).  
* **Link Rewriting:** This is the most crucial step for enabling offline functionality. As each page and asset is processed, its corresponding tag in the BeautifulSoup object is programmatically modified. The href or src attribute is replaced with a new, relative path that points to the locally saved copy of the resource.20 The  
  urllib.parse.urljoin function is invaluable here for correctly resolving relative links (e.g., ../styles/main.css) into absolute URLs for downloading.19 After all modifications are complete, the modified  
  BeautifulSoup object is saved as the final HTML file.

The primary advantage of this strategy lies in its dependency profile. BeautifulSoup is highly flexible and can operate with Python's built-in html.parser, thereby completely obviating the need for the problematic lxml library.22 This choice eliminates the single greatest installation risk and ensures the crawler component is predictable and resilient within the a-Shell environment.

### **2.4. Recommendation and Implementation Plan**

**Recommendation:** Strategy B, the custom-built crawler using Requests and BeautifulSoup, is unequivocally recommended. While it requires more explicit coding than a turnkey solution, it provides superior control, adaptability, and crucially, mitigates the critical dependency risks associated with C-based extensions in the a-Shell environment. Its resilience and predictability make it the only viable choice for a "silently reliable" system.  
**Table 2.1: Comparative Analysis of Crawler Strategies**

| Feature | pywebcopy | Requests \+ BeautifulSoup |
| :---- | :---- | :---- |
| **Core Function** | High-level, automated website cloning | Granular control over HTTP requests and HTML parsing |
| **Key Dependencies** | requests, beautifulsoup4, lxml | requests, beautifulsoup4 |
| **JavaScript Rendering** | No support 8 | No native support, but extensible |
| **Implementation** | Low complexity; single function call | Medium complexity; requires custom logic |
| **Reliability in a-Shell** | **Low.** High risk of installation failure due to lxml C-extension dependency.14 | **High.** Relies on pure-Python dependencies and the built-in html.parser, ensuring predictable installation. |

**Implementation Details:** The following Python script, crawl.py, implements the recommended crawler. It uses the argparse library to handle command-line arguments 24, a  
set to keep track of visited URLs to avoid redundant downloads, and a collections.deque for an efficient URL queue.

Python

\# crawl.py  
import argparse  
import collections  
import logging  
import os  
import requests  
from bs4 import BeautifulSoup  
from urllib.parse import urljoin, urlparse

\# Configure logging  
logging.basicConfig(level=logging.INFO, format='%(asctime)s \- %(levelname)s \- %(message)s')

def save\_file(content, directory, filename):  
    """Saves binary content to a file."""  
    path \= os.path.join(directory, filename)  
    os.makedirs(os.path.dirname(path), exist\_ok=True)  
    try:  
        with open(path, 'wb') as f:  
            f.write(content)  
        logging.info(f"Saved file: {path}")  
        return True  
    except IOError as e:  
        logging.error(f"Could not save file {path}: {e}")  
        return False

def download\_and\_rewrite(url, session, output\_dir, visited\_urls, domain):  
    """Downloads a single page, its assets, and rewrites links."""  
    if url in visited\_urls:  
        return None  
    visited\_urls.add(url)  
    logging.info(f"Crawling: {url}")

    try:  
        response \= session.get(url, timeout=10)  
        response.raise\_for\_status()  
    except requests.RequestException as e:  
        logging.error(f"Failed to download {url}: {e}")  
        return None

    soup \= BeautifulSoup(response.content, 'html.parser')  
      
    \# Define tags and their attributes to check for resources  
    tags \= {  
        'img': 'src',  
        'link': 'href',  
        'script': 'src',  
        'video': 'src',  
        'audio': 'src',  
        'source': 'src'  
    }

    for tag, attr in tags.items():  
        for element in soup.find\_all(tag, \*\*{attr: True}):  
            asset\_url\_raw \= element\[attr\]  
            asset\_url \= urljoin(url, asset\_url\_raw)

            if urlparse(asset\_url).netloc\!= domain:  
                continue \# Skip external assets

            try:  
                asset\_response \= session.get(asset\_url, timeout=10)  
                asset\_response.raise\_for\_status()  
                  
                \# Create a local path for the asset  
                parsed\_asset\_url \= urlparse(asset\_url)  
                \# Sanitize path to avoid issues with query strings  
                asset\_path \= parsed\_asset\_url.path.lstrip('/')  
                if not asset\_path:  
                    continue \# Skip if path is empty  
                  
                local\_path \= os.path.join(output\_dir, asset\_path)  
                  
                \# Save the asset  
                save\_file(asset\_response.content, os.path.dirname(local\_path), os.path.basename(local\_path))  
                  
                \# Rewrite the link in the HTML  
                relative\_path \= os.path.relpath(local\_path, start=os.path.dirname(os.path.join(output\_dir, urlparse(url).path.lstrip('/'))))  
                element\[attr\] \= relative\_path  
                logging.info(f"Rewrote {asset\_url\_raw} to {relative\_path}")

            except requests.RequestException as e:  
                logging.warning(f"Failed to download asset {asset\_url}: {e}")

    \# Save the modified HTML  
    page\_path \= urlparse(url).path.lstrip('/')  
    if not page\_path or page\_path.endswith('/'):  
        page\_path \= os.path.join(page\_path, 'index.html')  
      
    save\_file(soup.prettify('utf-8'), os.path.join(output\_dir, os.path.dirname(page\_path)), os.path.basename(page\_path))

    \# Find new internal links to crawl  
    new\_links \=  
    for link in soup.find\_all('a', href=True):  
        absolute\_link \= urljoin(url, link\['href'\])  
        if urlparse(absolute\_link).netloc \== domain:  
            if absolute\_link not in visited\_urls:  
                 new\_links.append(absolute\_link)  
            \# Rewrite internal page links  
            parsed\_link \= urlparse(absolute\_link)  
            link\_path \= parsed\_link.path.lstrip('/')  
            if not link\_path or link\_path.endswith('/'):  
                link\_path \= os.path.join(link\_path, 'index.html')  
              
            current\_page\_dir \= os.path.dirname(os.path.join(output\_dir, urlparse(url).path.lstrip('/')))  
            relative\_link \= os.path.relpath(os.path.join(output\_dir, link\_path), start=current\_page\_dir)  
            link\['href'\] \= relative\_link

    \# Save the final HTML with rewritten internal links  
    save\_file(soup.prettify('utf-8'), os.path.join(output\_dir, os.path.dirname(page\_path)), os.path.basename(page\_path))

    return new\_links

def main():  
    parser \= argparse.ArgumentParser(description="Crawl and download a website for offline viewing.")  
    parser.add\_argument('--url', required=True, help="The starting URL of the website to crawl.")  
    parser.add\_argument('--path', required=True, help="The local directory to save the website content.")  
    args \= parser.parse\_args()

    start\_url \= args.url  
    output\_dir \= args.path  
      
    domain \= urlparse(start\_url).netloc  
    if not domain:  
        logging.error("Invalid URL provided. Could not determine domain.")  
        return

    session \= requests.Session()  
    session.headers.update({'User-Agent': 'Offline-Site-Archiver/1.0'})  
      
    visited\_urls \= set()  
    queue \= collections.deque(\[start\_url\])

    while queue:  
        current\_url \= queue.popleft()  
        new\_links \= download\_and\_rewrite(current\_url, session, output\_dir, visited\_urls, domain)  
        if new\_links:  
            queue.extend(new\_links)  
      
    logging.info("Crawling finished.")

if \_\_name\_\_ \== "\_\_main\_\_":  
    main()

## **III. The On-Demand Local Server: Architecture and Implementation**

### **3.1. Server Requirements**

The local web server is a critical component for browsing the archived content. Its requirements are dictated by the constrained mobile environment and the need for future extensibility (i.e., the bookmarking feature). The ideal server must be:

* **Lightweight:** It must have a minimal memory and CPU footprint.  
* **Dependency-Free:** To ensure maximum reliability and ease of setup in a-Shell, it should have minimal or, ideally, zero external dependencies.  
* **Launchable:** It must be easily launchable from a single command line invocation via an Apple Shortcut.  
* **Extensible:** It must provide a clean mechanism for adding custom routes and application logic to support features like bookmarking.

### **3.2. Option A: The Standard Library (http.server)**

Python's standard library includes the http.server module, which provides a basic static file server that can be launched with a single command: python3 \-m http.server 8000\.25 This approach is attractive for its absolute simplicity, as it requires no installation. However, its functionality is limited and rigid. While it is possible to subclass its request handlers to add custom logic, this requires significant boilerplate code and is not idiomatic for building web applications.27 Furthermore, the module is explicitly "not recommended for production" due to its lack of robust security features, although this is a lesser concern for a locally-bound server.28 Its primary drawback is its inflexibility for adding the desired bookmarking API.

### **3.3. Option B: The Bottle Micro-framework**

The Bottle micro-framework presents a compelling alternative. Bottle is renowned for being fast, simple, and exceptionally lightweight.29 Its single most important feature for this project is that it is distributed as a single file module and  
**has no dependencies other than the Python Standard Library**.30 This means it can be included directly within the project directory, completely eliminating any need for  
pip install and its associated risks.  
Despite its minimalism, Bottle provides a powerful and elegant decorator-based routing system (e.g., @app.route('/path')) that makes defining static file servers and custom API endpoints trivial.32 It includes a built-in helper function,  
static\_file, designed specifically for securely serving files from a directory, which is precisely what is needed.34  
Bottle strikes the perfect balance between the simplicity of http.server and the flexibility required for the bookmarking feature.

### **3.4. Option C: The Flask Micro-framework**

Flask is another widely used and respected micro-framework. It is more feature-rich than Bottle but this comes at the cost of external dependencies, such as Werkzeug for WSGI handling and Jinja2 for templating.35 While powerful, these dependencies make  
Flask a heavier choice and introduce additional packages that must be managed. For the specific, focused requirements of this project, the added complexity of Flask is unnecessary. Bottle's zero-dependency nature makes it a more fitting and robust choice that adheres to the principle of using the simplest effective tool for the job.37

### **3.5. Recommendation and Implementation Plan**

**Recommendation:** Bottle is the ideal choice for the on-demand local server. Its zero-dependency, single-file distribution model guarantees reliability and ease of deployment in the a-Shell environment, while its clean API provides the necessary flexibility to implement both the static file serving and the advanced bookmarking functionality without unnecessary complexity.  
**Table 3.1: Comparative Analysis of Lightweight Server Frameworks**

| Framework | Type | Dependencies | Ease of Extension | Suitability for Project |
| :---- | :---- | :---- | :---- | :---- |
| http.server | Standard Library | None | Low (requires subclassing) | **Adequate** for basic serving, **Poor** for custom features. |
| Bottle | Micro-framework | None (single file) | High (decorator-based routing) | **Excellent.** Balances simplicity with necessary flexibility. |
| Flask | Micro-framework | External (Werkzeug, etc.) | High (decorator-based routing) | **Good, but Overkill.** Dependencies add unnecessary complexity. |

**Implementation Details:** The following Python script, server.py, implements the Bottle-based on-demand server. It requires the bottle.py file to be present in the same directory. The script uses argparse to receive the path to the archived website directory and serves all content from that location.

Python

\# server.py  
import argparse  
import os  
from bottle import Bottle, run, static\_file, request, response  
import json

\# \--- BOOKMARKING FEATURE \---  
BOOKMARKS\_FILE \= 'bookmarks.json'

def get\_bookmarks\_path(root\_path):  
    """Constructs the absolute path to the bookmarks file."""  
    return os.path.join(root\_path, BOOKMARKS\_FILE)

def load\_bookmarks(root\_path):  
    """Loads bookmarks from the JSON file."""  
    bookmarks\_path \= get\_bookmarks\_path(root\_path)  
    if not os.path.exists(bookmarks\_path):  
        return  
    try:  
        with open(bookmarks\_path, 'r', encoding='utf-8') as f:  
            return json.load(f)  
    except (IOError, json.JSONDecodeError):  
        return

def save\_bookmarks(bookmarks, root\_path):  
    """Saves bookmarks to the JSON file."""  
    bookmarks\_path \= get\_bookmarks\_path(root\_path)  
    try:  
        with open(bookmarks\_path, 'w', encoding='utf-8') as f:  
            json.dump(bookmarks, f, indent=4)  
        return True  
    except IOError:  
        return False

\# \--- BOTTLE APPLICATION \---  
app \= Bottle()

@app.route('/\<filepath:path\>')  
def server\_static(filepath, root\_path):  
    """Serves all static files from the archived site directory."""  
    \# Ensure the requested path is within the root directory for security  
    requested\_path \= os.path.abspath(os.path.join(root\_path, filepath))  
    if not requested\_path.startswith(os.path.abspath(root\_path)):  
        return "403 Forbidden"  
      
    return static\_file(filepath, root=root\_path)

\# \--- API Endpoints for Bookmarking \---  
@app.get('/api/bookmarks')  
def get\_bookmarks\_api(root\_path):  
    """API endpoint to retrieve all bookmarks."""  
    response.content\_type \= 'application/json'  
    return json.dumps(load\_bookmarks(root\_path))

@app.post('/api/add\_bookmark')  
def add\_bookmark\_api(root\_path):  
    """API endpoint to add a new bookmark."""  
    try:  
        data \= request.json  
        if not data or 'title' not in data or 'url' not in data:  
            response.status \= 400  
            return {'error': 'Invalid payload'}  
          
        bookmarks \= load\_bookmarks(root\_path)  
        \# Avoid duplicate bookmarks  
        if not any(b\['url'\] \== data\['url'\] for b in bookmarks):  
            bookmarks.append({'title': data\['title'\], 'url': data\['url'\]})  
            if save\_bookmarks(bookmarks, root\_path):  
                response.status \= 201  
                return {'status': 'success'}  
            else:  
                response.status \= 500  
                return {'error': 'Failed to save bookmarks'}  
        else:  
            return {'status': 'success', 'message': 'Bookmark already exists'}

    except Exception as e:  
        response.status \= 500  
        return {'error': str(e)}

def main():  
    parser \= argparse.ArgumentParser(description="Lightweight web server for browsing offline sites.")  
    parser.add\_argument('--path', required=True, help="The root directory of the archived website to serve.")  
    parser.add\_argument('--port', type=int, default=8080, help="The port to run the server on.")  
    args \= parser.parse\_args()

    if not os.path.isdir(args.path):  
        print(f"Error: Directory not found at {args.path}")  
        return

    \# Make the root path available to the route handlers  
    \# This is a simple way to pass the path without using global variables  
    \# A more complex app might use a plugin or a different structure.  
    app.route('/\<filepath:path\>')(lambda filepath: server\_static(filepath, root\_path=args.path))  
    app.get('/api/bookmarks')(lambda: get\_bookmarks\_api(root\_path=args.path))  
    app.post('/api/add\_bookmark')(lambda: add\_bookmark\_api(root\_path=args.path))

    print(f"Starting server for {args.path} on http://localhost:{args.port}")  
    run(app, host='localhost', port=args.port, quiet=True)

if \_\_name\_\_ \== "\_\_main\_\_":  
    main()

## **IV. System Orchestration via Apple Shortcuts and a-Shell**

Apple Shortcuts serves as the essential user-facing control plane, abstracting the command-line interactions into simple, tappable icons. This orchestration layer is what transforms the collection of Python scripts into a cohesive, app-like system.

### **4.1. Shortcut 1: "Archive New Website"**

This Shortcut manages the one-time process of downloading a website.

* **Workflow:**  
  1. **Ask for Input:** A prompt appears asking the user, "Enter the full URL of the website to archive."  
  2. **Ask for Input:** A second prompt appears asking, "Enter a project name for this archive." This name will be used for the directory, so it should be filesystem-friendly (e.g., "python-docs").  
  3. **Run Shell Script:** This is the core action, configured to execute in a-Shell. It takes the outputs from the previous two steps and uses them as arguments for the crawl.py script.38  
     * **Shell:** a-Shell  
     * **Command:** python3 crawl.py \--url "Shortcut Input 1" \--path "\~/Documents/archives/Shortcut Input 2"  
     * This command runs in the foreground of the a-Shell action. The user can see the logging output from the crawler, providing valuable progress feedback. The Shortcut will wait until the crawl.py script finishes execution before completing.

### **4.2. Shortcut 2: "Browse Offline Site"**

This Shortcut launches the on-demand server and opens Safari for browsing.

* **Workflow:**  
  1. **Get File:** This action opens the iOS file picker, allowing the user to navigate to and select the specific archived website directory they wish to browse (e.g., the "python-docs" folder inside \~/Documents/archives/).  
  2. **Run Shell Script:** This action launches the server.py script. The key is to run it as a background job so that the Shortcut can immediately proceed to the next step. This is achieved using the standard Unix ampersand (&) operator for job control, which is fully supported in a-Shell.40  
     * **Shell:** a-Shell  
     * **Command:** python3 server.py \--path "Shortcut Input" \>/dev/null 2\>&1 &  
     * The \> /dev/null 2\>&1 part is crucial; it redirects both standard output and standard error to /dev/null, preventing any server logs from appearing in the terminal and interfering with other tasks.6 The trailing  
       & immediately returns control to the Shortcut without waiting for the server to terminate.  
  3. **Open URL:** Immediately following the shell script action, this action opens Safari to the URL http://localhost:8080. By the time Safari opens, the lightweight Bottle server will have started and be ready to serve the index.html of the selected archive.

### **4.3. Managing the Process Lifecycle**

The elegance of the on-demand architecture lies in its self-managing lifecycle. There is no need for a dedicated "stop server" script or shortcut. The server.py process is a child of the a-Shell application instance.41 When the user is finished browsing and either manually closes a-Shell from the app switcher or iOS decides to terminate the backgrounded a-Shell app to reclaim resources, the server process is automatically and cleanly terminated by the operating system.42  
This behavior is the very definition of "silently reliable." The system consumes zero resources when not in active use and cleans up after itself without any required user interaction. The next time the "Browse Offline Site" shortcut is tapped, a new, clean server instance is started, ensuring a consistent and robust experience.

## **V. Advanced Feature Implementation: A Stateless Bookmarking System**

The choice of the Bottle framework for the local server makes implementing a sophisticated feature like bookmarking straightforward. To maintain the system's core principle of reliability, the bookmarking system must be stateless, meaning it cannot rely on any in-memory data that would be lost when the server process is inevitably terminated. All state must be persisted to the filesystem immediately upon modification.

### **5.1. Implementation Plan**

The bookmarking system will consist of three parts: a persistence layer, server-side API endpoints, and client-side JavaScript injected into the archived pages.

* **Persistence Layer:** For each archived site, a single JSON file named bookmarks.json will be stored in the root of its directory. This file will contain a simple array of bookmark objects, for example: \[{ "title": "...", "url": "..." },...\].  
* **Server-Side Logic (server.py):** The Bottle server will be enhanced with two new API endpoints, as shown in the code provided in Section 3.5:  
  * GET /api/bookmarks: This route reads the bookmarks.json file from the currently served archive's directory and returns its contents as a JSON response.  
  * POST /api/add\_bookmark: This route accepts a JSON payload containing the title and url of a page to be bookmarked. It performs an atomic read-append-write operation: it reads the current bookmarks.json, appends the new entry, and immediately writes the updated array back to the file, ensuring no data is lost even if the server is terminated moments later.  
* **Client-Side Logic (JavaScript Injection):** The crawl.py script will be modified to inject a small, non-intrusive JavaScript snippet into the \<head\> of every HTML page it saves. This script will:  
  1. Dynamically create and append a "Bookmark this page" button to the document's \<body\>.  
  2. Attach an event listener to this button. When clicked, the listener will capture the page's title from the \<title\> tag and its relative path from window.location.pathname.  
  3. Make an asynchronous fetch POST request to the local server's /api/add\_bookmark endpoint, sending the captured title and path as a JSON payload.  
* **Bookmark Display:** The crawler will also generate a special file, \_bookmarks.html, in the root of the archive. This page will contain JavaScript that, on load, makes a fetch GET request to /api/bookmarks. It will then dynamically parse the JSON response and render the list of bookmarks as a series of clickable links, providing a central hub for the user's saved pages. The "Browse Offline Site" shortcut can be easily modified to give the user the option to open this bookmarks page directly.

## **VI. Conclusion and Future Trajectories**

### **6.1. Synthesis of the Proposed Architecture**

The recommended architecture provides a complete and robust solution for offline website archiving and browsing on iOS, specifically tailored to the capabilities and constraints of the a-Shell environment. By combining a custom-built crawler using Requests and BeautifulSoup for maximum dependency reliability, an on-demand local server powered by the zero-dependency Bottle framework for lightweight flexibility, and an elegant orchestration layer using Apple Shortcuts, the system achieves the user's primary goal of being "silently reliable." This design deliberately embraces the ephemeral nature of iOS processes, resulting in a system that is resilient, resource-efficient, and requires no manual cleanup from the user.

### **6.2. Future Work and Potential Enhancements**

While the proposed system is comprehensive, several avenues for future enhancement exist:

* **Handling JavaScript-Heavy Websites:** The primary limitation of the current crawler is its inability to execute JavaScript. To archive modern Single-Page Applications (SPAs), integration with a headless browser engine would be necessary. This is a significant undertaking in the a-Shell environment but could potentially be explored by running a browser driver like Selenium or Playwright on a separate, networked machine that the a-Shell script could communicate with.10  
* **Incremental Updates:** The current crawler performs a full download on each run. A more advanced version could implement incremental updates by storing HTTP ETag or Last-Modified headers for each downloaded resource and using conditional GET requests on subsequent runs to only download content that has changed.  
* **Archive Management UI:** The Bottle server could be expanded to include a simple management interface. A "Manage Archives" shortcut could launch the server to a special page that lists all downloaded site archives, allowing the user to view their size, see their bookmarks, or trigger a deletion.  
* **Enhanced Error Reporting:** The Apple Shortcuts could be made more intelligent. For instance, the Run Shell Script action can capture the exit code of the script. The Shortcut could then use an If action to check if the exit code is non-zero and display a meaningful error notification to the user if the crawling or server launch fails.45

#### **Works cited**

1. Finish tasks in the background \- WWDC25 \- Videos \- Apple Developer, accessed June 27, 2025, [https://developer.apple.com/videos/play/wwdc2025/227/](https://developer.apple.com/videos/play/wwdc2025/227/)  
2. Extending your app's background execution time | Apple Developer Documentation, accessed June 27, 2025, [https://developer.apple.com/documentation/uikit/extending-your-app-s-background-execution-time](https://developer.apple.com/documentation/uikit/extending-your-app-s-background-execution-time)  
3. iOS Background service limitations \- Stack Overflow, accessed June 27, 2025, [https://stackoverflow.com/questions/61750991/ios-background-service-limitations](https://stackoverflow.com/questions/61750991/ios-background-service-limitations)  
4. Be able to customize cursor shape · Issue \#210 · holzschu/a-shell ..., accessed June 27, 2025, [https://github.com/holzschu/a-shell/issues/210](https://github.com/holzschu/a-shell/issues/210)  
5. accessed December 31, 1969, [https://github.com/holzschu/a-shell/issues/1090](https://github.com/holzschu/a-shell/issues/1090)  
6. How to deal with output from a background linux task \- Stack Overflow, accessed June 27, 2025, [https://stackoverflow.com/questions/14630104/how-to-deal-with-output-from-a-background-linux-task](https://stackoverflow.com/questions/14630104/how-to-deal-with-output-from-a-background-linux-task)  
7. pywebcopy \- PyPI, accessed June 27, 2025, [https://pypi.org/project/pywebcopy/](https://pypi.org/project/pywebcopy/)  
8. pywebcopy API documentation \- GitHub Pages, accessed June 27, 2025, [https://rajatomar788.github.io/pywebcopy/](https://rajatomar788.github.io/pywebcopy/)  
9. Best Web Scraping Methods for JavaScript-Heavy Websites \- PromptCloud, accessed June 27, 2025, [https://www.promptcloud.com/blog/best-javascript-web-scraping-methods/](https://www.promptcloud.com/blog/best-javascript-web-scraping-methods/)  
10. JavaScript Rendering in Web Scraping: Why It Matters \- InstantAPI.ai, accessed June 27, 2025, [https://web.instantapi.ai/blog/javascript-rendering-in-web-scraping-why-it-matters/](https://web.instantapi.ai/blog/javascript-rendering-in-web-scraping-why-it-matters/)  
11. pywebcopy·PyPI, accessed June 27, 2025, [https://pypi.org/project/pywebcopy/6.1.1/](https://pypi.org/project/pywebcopy/6.1.1/)  
12. Home · rajatomar788/pywebcopy Wiki \- GitHub, accessed June 27, 2025, [https://github.com/rajatomar788/pywebcopy/wiki](https://github.com/rajatomar788/pywebcopy/wiki)  
13. How do I install lxml on my system? \- WebScraping.AI, accessed June 27, 2025, [https://webscraping.ai/faq/lxml/how-do-i-install-lxml-on-my-system](https://webscraping.ai/faq/lxml/how-do-i-install-lxml-on-my-system)  
14. Installing lxml, accessed June 27, 2025, [https://lxml.de/installation.html](https://lxml.de/installation.html)  
15. How to Install lxml on Ubuntu? \- GeeksforGeeks, accessed June 27, 2025, [https://www.geeksforgeeks.org/techtips/how-to-install-lxml-on-ubuntu/](https://www.geeksforgeeks.org/techtips/how-to-install-lxml-on-ubuntu/)  
16. a-Shell, accessed June 27, 2025, [https://holzschu.github.io/a-Shell\_iOS/](https://holzschu.github.io/a-Shell_iOS/)  
17. Web Crawler with Python Using BeautifulSoup \- Medium, accessed June 27, 2025, [https://medium.com/@spaw.co/web-crawler-with-python-using-beautifulsoup-a5110f46e767](https://medium.com/@spaw.co/web-crawler-with-python-using-beautifulsoup-a5110f46e767)  
18. How To Work with Web Data Using Requests and Beautiful Soup with Python 3, accessed June 27, 2025, [https://www.digitalocean.com/community/tutorials/how-to-work-with-web-data-using-requests-and-beautiful-soup-with-python-3](https://www.digitalocean.com/community/tutorials/how-to-work-with-web-data-using-requests-and-beautiful-soup-with-python-3)  
19. How to Download HTML and Assets from a URL with Python \- ByteScrum Technologies, accessed June 27, 2025, [https://blog.bytescrum.com/how-to-download-html-and-assets-from-a-url-with-python?source=more\_series\_bottom\_blogs](https://blog.bytescrum.com/how-to-download-html-and-assets-from-a-url-with-python?source=more_series_bottom_blogs)  
20. \[Python\] How to change urls in BeautifulSoup? : r/learnprogramming \- Reddit, accessed June 27, 2025, [https://www.reddit.com/r/learnprogramming/comments/46p8w7/python\_how\_to\_change\_urls\_in\_beautifulsoup/](https://www.reddit.com/r/learnprogramming/comments/46p8w7/python_how_to_change_urls_in_beautifulsoup/)  
21. python \- BeautifulSoup \- modifying all links in a piece of HTML? \- Stack Overflow, accessed June 27, 2025, [https://stackoverflow.com/questions/459981/beautifulsoup-modifying-all-links-in-a-piece-of-html](https://stackoverflow.com/questions/459981/beautifulsoup-modifying-all-links-in-a-piece-of-html)  
22. Best Python Web Scraping Libraries in 2024 \- GeeksforGeeks, accessed June 27, 2025, [https://www.geeksforgeeks.org/best-python-web-scraping-libraries-in-2024/](https://www.geeksforgeeks.org/best-python-web-scraping-libraries-in-2024/)  
23. Implementing Web Scraping in Python with BeautifulSoup \- GeeksforGeeks, accessed June 27, 2025, [https://www.geeksforgeeks.org/python/implementing-web-scraping-python-beautiful-soup/](https://www.geeksforgeeks.org/python/implementing-web-scraping-python-beautiful-soup/)  
24. Command Line Arguments for Your Python Script \- MachineLearningMastery.com, accessed June 27, 2025, [https://machinelearningmastery.com/command-line-arguments-for-your-python-script/](https://machinelearningmastery.com/command-line-arguments-for-your-python-script/)  
25. How to Create a Simple HTTP Server in Python \- DigitalOcean, accessed June 27, 2025, [https://www.digitalocean.com/community/tutorials/python-simplehttpserver-http-server](https://www.digitalocean.com/community/tutorials/python-simplehttpserver-http-server)  
26. Create a HTTP server with one command thanks to Python | by Ryan Blunden | Medium, accessed June 27, 2025, [https://ryanblunden.com/create-a-http-server-with-one-command-thanks-to-python-29fcfdcd240e](https://ryanblunden.com/create-a-http-server-with-one-command-thanks-to-python-29fcfdcd240e)  
27. Serve directory in Python 3 \- Stack Overflow, accessed June 27, 2025, [https://stackoverflow.com/questions/55052811/serve-directory-in-python-3](https://stackoverflow.com/questions/55052811/serve-directory-in-python-3)  
28. http.server — HTTP servers — Python 3.13.5 documentation, accessed June 27, 2025, [https://docs.python.org/3/library/http.server.html](https://docs.python.org/3/library/http.server.html)  
29. bottle.py is a fast and simple micro-framework for python web-applications. \- GitHub, accessed June 27, 2025, [https://github.com/bottlepy/bottle](https://github.com/bottlepy/bottle)  
30. Bottle: Python Web Framework — Bottle 0.14-dev documentation, accessed June 27, 2025, [https://bottlepy.org/](https://bottlepy.org/)  
31. Top Python Frameworks for Web Development in 2025 \- DRC Systems, accessed June 27, 2025, [https://www.drcsystems.com/blogs/python-frameworks-for-web-development/](https://www.drcsystems.com/blogs/python-frameworks-for-web-development/)  
32. Writing Web Applications in Python with Bottle, accessed June 27, 2025, [https://pwp.stevecassidy.net/bottle/python-webapps/](https://pwp.stevecassidy.net/bottle/python-webapps/)  
33. Introduction to Bottle Web Framework \- Python \- GeeksforGeeks, accessed June 27, 2025, [https://www.geeksforgeeks.org/python/introduction-to-bottle-web-framework-python/](https://www.geeksforgeeks.org/python/introduction-to-bottle-web-framework-python/)  
34. User's Guide — Bottle 0.14-dev documentation \- Bottle.py, accessed June 27, 2025, [https://bottlepy.org/docs/dev/tutorial.html\#static-files](https://bottlepy.org/docs/dev/tutorial.html#static-files)  
35. Choosing the Right Python Web Framework: Django, Flask, FastAPI, Tornado, and Bottle | by Kanak Sengar | Medium, accessed June 27, 2025, [https://medium.com/@KanakSengar/choosing-the-right-python-web-framework-django-flask-fastapi-tornado-and-bottle-19bb6f6c5d3d](https://medium.com/@KanakSengar/choosing-the-right-python-web-framework-django-flask-fastapi-tornado-and-bottle-19bb6f6c5d3d)  
36. Flask vs Bottle Web Framework \- DEV Community, accessed June 27, 2025, [https://dev.to/amigosmaker/flask-vs-bottle-web-framework-li6](https://dev.to/amigosmaker/flask-vs-bottle-web-framework-li6)  
37. Flask vs. Bottle, what are their advantages and disadvantages? \- Quora, accessed June 27, 2025, [https://www.quora.com/Flask-vs-Bottle-what-are-their-advantages-and-disadvantages](https://www.quora.com/Flask-vs-Bottle-what-are-their-advantages-and-disadvantages)  
38. How to pass multiple inputs to a Python script in macOS Shortcuts? \- Stack Overflow, accessed June 27, 2025, [https://stackoverflow.com/questions/79463058/how-to-pass-multiple-inputs-to-a-python-script-in-macos-shortcuts](https://stackoverflow.com/questions/79463058/how-to-pass-multiple-inputs-to-a-python-script-in-macos-shortcuts)  
39. Run a python script as a quick action in finder on selected folder \- Apple Developer, accessed June 27, 2025, [https://developer.apple.com/forums/thread/742419](https://developer.apple.com/forums/thread/742419)  
40. How to Run Commands in Background in Shell Scripting \- LabEx, accessed June 27, 2025, [https://labex.io/questions/how-to-run-a-command-in-the-background-in-a-shell-script-388819](https://labex.io/questions/how-to-run-a-command-in-the-background-in-a-shell-script-388819)  
41. Processes — Linux shell tutorial documentation, accessed June 27, 2025, [https://aaltoscicomp.github.io/linux-shell/processes/](https://aaltoscicomp.github.io/linux-shell/processes/)  
42. How To Use Bash's Job Control to Manage Foreground and Background Processes, accessed June 27, 2025, [https://www.digitalocean.com/community/tutorials/how-to-use-bash-s-job-control-to-manage-foreground-and-background-processes](https://www.digitalocean.com/community/tutorials/how-to-use-bash-s-job-control-to-manage-foreground-and-background-processes)  
43. 7 Best Python Web Scraping Libraries in 2025 \- ZenRows, accessed June 27, 2025, [https://www.zenrows.com/blog/python-web-scraping-library](https://www.zenrows.com/blog/python-web-scraping-library)  
44. Latest Techniques in Crawling JavaScript-Heavy Websites \- PromptCloud, accessed June 27, 2025, [https://www.promptcloud.com/blog/crawling-techniques-for-javascript-heavy-websites/](https://www.promptcloud.com/blog/crawling-techniques-for-javascript-heavy-websites/)  
45. How to compare output of Run Shell Script action to a value \- Apple Support Community, accessed June 27, 2025, [https://discussions.apple.com/thread/255216039](https://discussions.apple.com/thread/255216039)