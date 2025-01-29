from main import app  # Импорт приложения из main.py

server = app.server  # Gunicorn запускает Flask-сервер

if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8050)