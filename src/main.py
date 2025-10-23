"""
This file is going to house our Flask app to run the website. It will hold all of the API endpoints as well as the logic to render the HTML templates.
"""

# import flask
from flask import Flask, request, jsonify, render_template, session 

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)