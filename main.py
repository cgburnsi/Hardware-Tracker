from app import create_app

app = create_app()

if __name__ == '__main__':
    # Use reloader=True for development so you don't have to restart on every change
    app.run(debug=True, use_reloader=True)