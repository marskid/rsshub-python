from waitress import serve
from main import app

if __name__ == '__main__':
    print("Starting RSSHub with Waitress on http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000, threads=16)