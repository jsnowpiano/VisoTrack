from flask import Blueprint, jsonify, request
import bcrypt
from storage.connection import (
    StudyDatabaseConnection,
    UserDatabaseConnection,
    CompanyDatabaseConnection,
)

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/companies/register", methods=["POST"])
def register_company():
    payload = request.get_json(silent=True) or {}
    name     = (payload.get("name") or "").strip()
    password = (payload.get("password") or "").strip()

    if not name or not password:
        return jsonify({"error": "name and password are required"}), 400

    db = CompanyDatabaseConnection()

    if db.get_company_by_name(name):
        return jsonify({"error": "A company with that name already exists"}), 409

    try:
        access_code = db.generate_unique_code()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    company_doc = {
        "name":          name,
        "password_hash": password_hash,
        "access_code":   access_code,
    }

    try:
        db.create_company(company_doc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"access_code": access_code}), 201


@api_bp.route("/api/companies/login", methods=["POST"])
def login_company():

    payload  = request.get_json(silent=True) or {}
    name     = (payload.get("name") or "").strip()
    password = (payload.get("password") or "").strip()

    if not name or not password:
        return jsonify({"error": "name and password are required"}), 400

    db      = CompanyDatabaseConnection()
    company = db.get_company_by_name(name)

    if not company:
        return jsonify({"error": "Invalid credentials"}), 401

    stored_hash = company.get("password_hash", "")
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode()

    if not bcrypt.checkpw(password.encode(), stored_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "access_code": company["access_code"],
        "name":        company["name"],
    }), 200

def _require_company_code():
    code = request.args.get("company_code") or ""
    if not code:
        body = request.get_json(silent=True) or {}
        code = body.get("company_code") or ""
    return code.strip()


@api_bp.route("/api/studies", methods=["GET"])
def get_studies():
    company_code = request.args.get("company_code", "").strip()
    if not company_code:
        return jsonify({"error": "company_code is required"}), 400

    # Validate that the code actually exists
    cdb = CompanyDatabaseConnection()
    if not cdb.get_company_by_code(company_code):
        return jsonify({"error": "Invalid company code"}), 403

    try:
        db      = StudyDatabaseConnection()
        studies = db.get_all_studies(company_code=company_code)
        return jsonify(studies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies/<study_name>", methods=["GET"])
def get_study(study_name):
    company      = request.args.get("company", "")
    company_code = request.args.get("company_code", "").strip()

    try:
        db    = StudyDatabaseConnection()
        study = db.get_study(study_name, company, company_code or None)
        if not study:
            return jsonify({"error": "Not found"}), 404
        return jsonify(study)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies", methods=["POST"])
def create_study():
    payload      = request.get_json(silent=True) or {}
    company_code = (payload.get("company_code") or "").strip()

    if not company_code:
        return jsonify({"error": "company_code is required"}), 400

    cdb = CompanyDatabaseConnection()
    if not cdb.get_company_by_code(company_code):
        return jsonify({"error": "Invalid company code"}), 403

    payload["company_code"] = company_code  # ensure it's stored
    try:
        db  = StudyDatabaseConnection()
        _id = db.add_study(payload)
        return jsonify({"status": "ok", "id": _id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies/session", methods=["POST"])
def add_session():
    payload      = request.get_json(silent=True) or {}
    study_name   = payload.get("study_name")
    company_name = payload.get("company_name", "")
    gaze_points  = payload.get("gaze_points", [])
    company_code = payload.get("company_code", "")

    if not study_name:
        return jsonify({"error": "Missing study_name"}), 400

    try:
        db = StudyDatabaseConnection()
        db.add_gaze_session(study_name, company_name, gaze_points,
                            company_code=company_code or None)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/studies/<study_name>", methods=["DELETE"])
def delete_study(study_name):
    payload      = request.get_json(silent=True) or {}
    company_name = payload.get("company_name", "")
    company_code = (payload.get("company_code") or "").strip()

    if not company_code:
        return jsonify({"error": "company_code is required"}), 400

    try:
        db    = StudyDatabaseConnection()
        count = db.delete_study(study_name, company_name, company_code)
        if count == 0:
            return jsonify({"error": "Study not found or code mismatch"}), 404
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/api/users/register", methods=["POST"])
def register_user():
    payload      = request.get_json(silent=True) or {}
    user_id      = (payload.get("user_id") or "").strip()
    password     = (payload.get("password") or "").strip()
    company_code = (payload.get("company_code") or "").strip()

    if not user_id or not password or not company_code:
        return jsonify({"error": "user_id, password, and company_code are required"}), 400

    cdb = CompanyDatabaseConnection()
    company = cdb.get_company_by_code(company_code)
    if not company:
        return jsonify({"error": "Invalid company access code"}), 403

    udb = UserDatabaseConnection()
    if udb.get_user(user_id):
        return jsonify({"error": "user_id already taken"}), 409

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user_doc = {
        "user_id":       user_id,
        "password_hash": password_hash,
        "company_code":  company_code,
        "company_name":  company.get("name", ""),
    }

    try:
        udb.add_user(user_doc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status":       "ok",
        "company_code": company_code,
        "company_name": company.get("name", ""),
    }), 201


@api_bp.route("/api/auth/login", methods=["POST"])
def login_user():
    payload  = request.get_json(silent=True) or {}
    user_id  = payload.get("user_id")
    password = payload.get("password")

    if not user_id or not password:
        return jsonify({"error": "Missing credentials"}), 400

    try:
        db   = UserDatabaseConnection()
        user = db.get_user(user_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    stored_hash = user.get("password_hash")
    if not stored_hash:
        return jsonify({"error": "Invalid credentials"}), 401
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode()

    if not bcrypt.checkpw(password.encode(), stored_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "status":       "ok",
        "company_code": user.get("company_code", ""),
        "company_name": user.get("company_name", ""),
    }), 200


@api_bp.route("/api/users", methods=["GET"])
def get_users():
    try:
        db    = UserDatabaseConnection()
        users = db.get_all_users()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500