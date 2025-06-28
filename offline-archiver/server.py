import argparse
import os
import json
import sqlite3
import logging
from bottle import Bottle, run, static_file, request, response

BOOKMARKS_DB = 'bookmarks.db'

def init_db(root_path):
    """Initialize the SQLite database and create the bookmarks table if it doesn't exist."""
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
        logging.info(f"Database initialized at {db_path}")
    except sqlite3.Error as e:
        logging.error(f"Database error during initialization: {e}")
        raise

class ArchiveServer:
    def __init__(self, root_path):
        """Initializes the server with the specified root path for the archive."""
        if not os.path.isdir(root_path):
            raise FileNotFoundError(f"Error: Root directory not found at {root_path}")
        self.root_path = os.path.abspath(root_path)
        self.db_path = os.path.join(self.root_path, BOOKMARKS_DB)
        self.app = Bottle()
        self._setup_routes()

    def _setup_routes(self):
        """Sets up all the URL routes for the Bottle application."""
        self.app.route('/', method='GET')(self.serve_root)
        self.app.route('/api/bookmarks', method='GET')(self.get_bookmarks_api)
        self.app.route('/api/add_bookmark', method='POST')(self.add_bookmark_api)
        self.app.route('/<filepath:path>', method='GET')(self.serve_static)

    def get_bookmarks_api(self):
        """API endpoint to return all bookmarks from the database."""
        response.content_type = 'application/json'
        bookmarks = []
        try:
            con = sqlite3.connect(self.db_path)
            cur = con.cursor()
            for row in cur.execute("SELECT title, url FROM bookmarks ORDER BY created_at DESC"):
                bookmarks.append({'title': row[0], 'url': row[1]})
            con.close()
        except sqlite3.Error as e:
            logging.error(f"API Error getting bookmarks: {e}")
            response.status = 500
            return json.dumps({'status': 'error', 'error': str(e)})
        return json.dumps(bookmarks)

    def add_bookmark_api(self):
        """API endpoint to add a new bookmark to the database."""
        # IMPROVEMENT: Set content type at the start for all response paths.
        response.content_type = 'application/json'
        try:
            data = request.json
            if not data or 'title' not in data or 'url' not in data:
                response.status = 400
                return {'status': 'error', 'error': 'Invalid payload'}

            con = sqlite3.connect(self.db_path)
            cur = con.cursor()
            cur.execute("INSERT OR IGNORE INTO bookmarks (title, url) VALUES (?, ?)", (data['title'], data['url']))
            con.commit()

            if con.changes() > 0:
                response.status = 201  # Created
                result = {'status': 'success', 'message': 'Bookmark added.'}
            else:
                response.status = 200  # OK
                result = {'status': 'success', 'message': 'Bookmark already exists.'}
            con.close()
            return result
        except json.JSONDecodeError:
            response.status = 400
            return {'status': 'error', 'error': 'Invalid JSON'}
        except sqlite3.Error as e:
            logging.error(f"API Error adding bookmark: {e}")
            response.status = 500
            return {'status': 'error', 'error': f'Database error: {e}'}

    def serve_static(self, filepath):
        """
        Serve static files from the archive.
        FIX: Removed .lower() on the filepath. This is the critical fix that allows
        the server to find files with uppercase characters on case-sensitive or
        case-preserving filesystems (like macOS/iOS and Linux).
        """
        # The filepath is used as-is to respect the original casing.
        safe_filepath = filepath

        full_path = os.path.join(self.root_path, safe_filepath)
        if safe_filepath.endswith('/') or (os.path.exists(full_path) and os.path.isdir(full_path)):
             safe_filepath = os.path.join(safe_filepath, 'index.html')

        return static_file(safe_filepath, root=self.root_path)

    def serve_root(self):
        """Serve the root index.html."""
        return self.serve_static('index.html')

    def start(self, host='localhost', port=8080):
        """Starts the web server."""
        init_db(self.root_path)
        print(f"Starting server for {self.root_path} on http://{host}:{port}")
        run(self.app, host=host, port=port, quiet=False)

def main():
    parser = argparse.ArgumentParser(description="Lightweight web server for browsing offline sites.")
    parser.add_argument('--path', required=True, help="The root directory of the archived website to serve.")
    parser.add_argument('--port', type=int, default=8080, help="The port to run the server on.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        server = ArchiveServer(root_path=args.path)
        server.start(port=args.port)
    except FileNotFoundError as e:
        logging.error(f"Error: {e}. Please provide a valid path to an archived site.")
    except Exception as e:
        logging.error(f"Failed to start server: {e}")

if __name__ == '__main__':
    main()
