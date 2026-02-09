from flask import Blueprint, jsonify, request
import bcrypt
from backend.storage.connection import StudyDatabaseConnection, UserDatabaseConnection

api_bp = Blueprint("api", __name__)

@api_bp.route("/api/studies", methods=["GET"])
def get_studies():
    db = StudyDatabaseConnection()
    studies = db.get_all_studies()
    return jsonify(studies)

@api_bp.route("/api/users", methods=["GET"])
def get_users():
    db = UserDatabaseConnection()
    users = db.get_all_users()
    return jsonify(users)

@api_bp.route("/api/auth/login", methods=["POST"])
def login_user():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    password = payload.get("password")

    if not user_id or not password:
        return jsonify({"error": "Missing credentials"}), 400

    db = UserDatabaseConnection()
    user = db.get_user(user_id)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    stored_hash = user.get("password_hash")
    if not stored_hash:
        return jsonify({"error": "Invalid credentials"}), 401

    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode("utf-8")

    is_valid = bcrypt.checkpw(password.encode("utf-8"), stored_hash)
    if not is_valid:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"status": "ok"}), 200
