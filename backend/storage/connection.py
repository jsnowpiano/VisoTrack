from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import secrets
import string

uri = "mongodb+srv://d00419226:DBMikuBot2122Magic@cluster0.h6fp6.mongodb.net/?appName=Cluster0"

client = MongoClient(uri)
dataBase = client["ResearchStudyDatabase"]
collection = dataBase["ResearchStudyCollection"]


def _clean(doc):
    """Strip _id and any other non-JSON-safe BSON types recursively."""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = _clean(v)
        elif isinstance(v, list):
            out[k] = [_clean(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _generate_access_code(length=6):
    """Generate a random uppercase alphanumeric access code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ─────────────────────────────────────────────────────────────
#  Company (Researcher) DB
# ─────────────────────────────────────────────────────────────
class CompanyDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = dataBase["CompanyCollection"]

    def create_company(self, company_data: dict) -> str:
        """Insert a new company doc; returns the inserted _id as string."""
        result = self.collection.insert_one(company_data)
        return str(result.inserted_id)

    def get_company_by_name(self, name: str):
        doc = self.collection.find_one({"name": name}, {"_id": 0})
        return _clean(doc)

    def get_company_by_code(self, access_code: str):
        doc = self.collection.find_one({"access_code": access_code}, {"_id": 0})
        return _clean(doc)

    def get_all_companies(self):
        docs = list(self.collection.find({}, {"_id": 0, "password_hash": 0}))
        return [_clean(d) for d in docs]

    def generate_unique_code(self) -> str:
        """Keep generating until we find a code not already in use."""
        for _ in range(20):
            code = _generate_access_code()
            if not self.collection.find_one({"access_code": code}):
                return code
        raise RuntimeError("Could not generate a unique access code")


# ─────────────────────────────────────────────────────────────
#  Study DB  (now access-code aware)
# ─────────────────────────────────────────────────────────────
class StudyDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = collection

    def get_all_studies(self, company_code: str = None):
        """
        Return studies without image data.
        If company_code is provided, filter to only that company's studies.
        """
        query = {}
        if company_code:
            query["company_code"] = company_code
        studies = list(self.collection.find(query, {"_id": 0, "image_b64": 0}))
        return [_clean(s) for s in studies]

    def get_all_studies_full(self, company_code: str = None):
        """Return all studies including image data (use sparingly)."""
        query = {}
        if company_code:
            query["company_code"] = company_code
        studies = list(self.collection.find(query, {"_id": 0}))
        return [_clean(s) for s in studies]

    def get_study(self, study_name: str, company_name: str, company_code: str = None):
        query = {"study_name": study_name, "company_name": company_name}
        if company_code:
            query["company_code"] = company_code
        study = self.collection.find_one(query, {"_id": 0})
        return _clean(study)

    def add_study(self, study_data: dict) -> str:
        result = self.collection.insert_one(study_data)
        return str(result.inserted_id)

    def add_gaze_session(self, study_name: str, company_name: str,
                         gaze_points: list, company_code: str = None):
        """Append a new gaze session to an existing study's gaze_sessions array."""
        session = {
            "recorded_at": datetime.utcnow().isoformat(),
            "gaze_points": gaze_points,
        }
        query = {"study_name": study_name, "company_name": company_name}
        if company_code:
            query["company_code"] = company_code
        self.collection.update_one(query, {"$push": {"gaze_sessions": session}})

    def update_study(self, study_name: str, company_name: str,
                     update_data: dict, company_code: str = None):
        query = {"study_name": study_name, "company_name": company_name}
        if company_code:
            query["company_code"] = company_code
        result = self.collection.update_one(query, {"$set": update_data})
        return result.modified_count

    def delete_study(self, study_name: str, company_name: str,
                     company_code: str = None):
        query = {"study_name": study_name, "company_name": company_name}
        if company_code:
            query["company_code"] = company_code
        result = self.collection.delete_one(query)
        return result.deleted_count


# ─────────────────────────────────────────────────────────────
#  User (Participant) DB
# ─────────────────────────────────────────────────────────────
class UserDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = dataBase["UserCollection"]

    def get_all_users(self):
        users = list(self.collection.find({}, {"_id": 0, "password_hash": 0}))
        return [_clean(u) for u in users]

    def add_user(self, user_data: dict) -> str:
        result = self.collection.insert_one(user_data)
        return str(result.inserted_id)

    def get_user(self, user_id: str):
        query = {"user_id": user_id}
        user = self.collection.find_one(query, {"_id": 0})
        return _clean(user)

    def update_user(self, user_id: str, update_data: dict):
        query = {"user_id": user_id}
        result = self.collection.update_one(query, {"$set": update_data})
        return result.modified_count

    def delete_user(self, user_id: str):
        query = {"user_id": user_id}
        result = self.collection.delete_one(query)
        return result.deleted_count