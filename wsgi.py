"""
wsgi.py

Entry point aplikasi. Digunakan oleh:
- `flask run` (development)
- WSGI server seperti gunicorn: `gunicorn wsgi:app` (production)
"""

from backend import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
