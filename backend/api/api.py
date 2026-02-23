from flask import Blueprint, jsonify, request
import bcrypt
from storage.connection import StudyDatabaseConnection, UserDatabaseConnection

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/studies", methods=["GET"])
def get_studies():
    """
    Returns studies WITHOUT image_b64 to keep the response small and fast.
    The participant client only needs name/company/viewing_time/status for the list.
    """
    try:
        db = StudyDatabaseConnection()
        studies = db.get_all_studies()
        return jsonify(studies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies/<study_name>", methods=["GET"])
def get_study(study_name):
    """Return a single study including image_b64, looked up by name."""
    company = request.args.get("company", "")
    try:
        db = StudyDatabaseConnection()
        study = db.get_study(study_name, company)
        if not study:
            return jsonify({"error": "Not found"}), 404
        return jsonify(study)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies/session", methods=["POST"])
def add_session():
    """Append a gaze session to an existing study."""
    payload = request.get_json(silent=True) or {}
    study_name = payload.get("study_name")
    company_name = payload.get("company_name", "")
    gaze_points = payload.get("gaze_points", [])

    if not study_name:
        return jsonify({"error": "Missing study_name"}), 400

    try:
        db = StudyDatabaseConnection()
        db.add_gaze_session(study_name, company_name, gaze_points)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/users", methods=["GET"])
def get_users():
    try:
        db = UserDatabaseConnection()
        users = db.get_all_users()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/auth/login", methods=["POST"])
def login_user():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    password = payload.get("password")

    if not user_id or not password:
        return jsonify({"error": "Missing credentials"}), 400

    try:
        db = UserDatabaseConnection()
        user = db.get_user(user_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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