# OfflineWebpageHost

A simple toolkit for archiving websites and browsing them offline on iOS.
It was designed around the constraints of the [a-Shell](https://github.com/holzschu/a-shell) environment and can be controlled entirely through Apple Shortcuts.

## Repository Contents

- `offline-archiver/`
  - `crawl.py` – crawler that downloads a website, rewrites links and injects a small bookmarking script
  - `server.py` – lightweight Bottle web server used to browse the archive on demand
  - `bottle.py` – the Bottle micro‑framework included as a single file
- `Research_and_Plan.md` – architecture discussion
- `V0_Implementation.md` – detailed implementation notes

## Setting Up on iPhone

1. **Install a‑Shell** from the App Store.
2. Clone this repository in a‑Shell:
   ```bash
   git clone <repo-url>
   ```
3. Move into the project directory and install the required Python packages if they are not already available:
   ```bash
   pip install requests beautifulsoup4
   ```
4. Inside your `~/Documents` directory create two folders:
   - `offline-archiver` – copy the contents of this repository's `offline-archiver` folder here
   - `archives` – destination for downloaded websites

The final layout should look like:
```
~/Documents/
|-- offline-archiver/
|   |-- crawl.py
|   |-- server.py
|   |-- bottle.py
|
|-- archives/
    |-- (site archives go here)
```

## Apple Shortcuts

Two shortcuts provide an app-like experience. Detailed steps for creating them can be found in `V0_Implementation.md`.

### 1. Archive New Website
Prompts for a URL and a project name then runs:
```bash
cd offline-archiver
python3 crawl.py --url "<entered URL>" --path "~/Documents/archives/<project name>"
```

### 2. Browse Offline Site
Lets you pick an archived site directory, starts the server in the background, and opens Safari:
```bash
cd offline-archiver
python3 server.py --path "<chosen directory>" &> /dev/null &
open http://localhost:8080
```
The server stops automatically when a‑Shell is closed or suspended.

## Manual Usage

You may run the scripts directly in a‑Shell:
```bash
# Download a site
python3 offline-archiver/crawl.py --url https://example.com --path ~/Documents/archives/example

# Start the server
python3 offline-archiver/server.py --path ~/Documents/archives/example
```
Then open `http://localhost:8080` in Safari.

## About
This project implements the architecture described in the accompanying documents and serves as a reference implementation for reliable offline browsing on iOS.
