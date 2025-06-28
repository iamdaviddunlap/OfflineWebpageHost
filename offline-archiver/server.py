import argparse
import os
import json
from bottle import Bottle, run, static_file, request, response

BOOKMARKS_FILE = 'bookmarks.json'


def get_bookmarks_path(root_path):
    """Construct the absolute path to the bookmarks file."""
    return os.path.join(root_path, BOOKMARKS_FILE)


def load_bookmarks(root_path):
    """Load bookmarks from the JSON file."""
    bookmarks_path = get_bookmarks_path(root_path)
    if not os.path.exists(bookmarks_path):
        return []
    try:
        with open(bookmarks_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return []


def save_bookmarks(bookmarks, root_path):
    """Save bookmarks to the JSON file."""
    bookmarks_path = get_bookmarks_path(root_path)
    try:
        with open(bookmarks_path, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, indent=4)
        return True
    except IOError:
        return False


app = Bottle()


@app.route('/api/bookmarks', method='GET')
def get_bookmarks_api(root_path):
    """Return all bookmarks."""
    response.content_type = 'application/json'
    bookmarks = load_bookmarks(root_path)
    return json.dumps(bookmarks)


@app.route('/api/add_bookmark', method='POST')
def add_bookmark_api(root_path):
    """Add a new bookmark."""
    try:
        data = request.json
        if not data or 'title' not in data or 'url' not in data:
            response.status = 400
            return {'error': 'Invalid payload'}

        bookmarks = load_bookmarks(root_path)
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


@app.route('/<filepath:path>')
def server_static(filepath, root_path):
    """Serve static files from the archive."""
    if filepath.endswith('/'):
        filepath += 'index.html'
    elif not os.path.splitext(filepath)[1]:
        if os.path.isfile(os.path.join(root_path, filepath)):
            return static_file(filepath, root=root_path)
        filepath = os.path.join(filepath, 'index.html')
    return static_file(filepath, root=root_path)


@app.route('/')
def server_root(root_path):
    """Serve the root index.html."""
    return static_file('index.html', root=root_path)


def main():
    parser = argparse.ArgumentParser(description="Lightweight web server for browsing offline sites.")
    parser.add_argument('--path', required=True, help="The root directory of the archived website to serve.")
    parser.add_argument('--port', type=int, default=8080, help="The port to run the server on.")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"Error: Directory not found at {args.path}")
        return

    app.config['root_path'] = args.path

    app.route('/<filepath:path>')(lambda filepath: server_static(filepath, root_path=app.config['root_path']))
    app.route('/')(lambda: server_root(root_path=app.config['root_path']))
    app.get('/api/bookmarks')(lambda: get_bookmarks_api(root_path=app.config['root_path']))
    app.post('/api/add_bookmark')(lambda: add_bookmark_api(root_path=app.config['root_path']))

    print(f"Starting server for {args.path} on http://localhost:{args.port}")
    run(app, host='localhost', port=args.port, quiet=True)


if __name__ == '__main__':
    main()
