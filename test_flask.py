from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return '<h1>TEST DZIAŁA! ✅</h1>'

if __name__ == '__main__':
    print("🚀 Startuje na http://127.0.0.1:5000")
    app.run(debug=True, port=5000)