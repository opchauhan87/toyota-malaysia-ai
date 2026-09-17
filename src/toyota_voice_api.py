#!/usr/bin/env python3

from flask import Flask, request, jsonify
from toyota_customer_query import answer_question

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Toyota Malaysia Voice AI",
        "language": "English",
        "knowledge_base": "Toyota Malaysia Official",
        "no_guessing": True
    })


@app.route("/ask", methods=["POST"])
def ask():

    data = request.get_json(silent=True) or {}

    question = data.get("question", "").strip()

    if not question:
        return jsonify({
            "success": False,
            "answer": "Please tell me your question."
        }), 400

    answer = answer_question(question)

    return jsonify({
        "success": True,
        "question": question,
        "answer": answer,
        "language": "English"
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8090,
        debug=False
    )
