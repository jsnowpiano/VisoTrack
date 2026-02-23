from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

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


class StudyDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = collection

    def get_all_studies(self):
        """Return all studies without image data (for list views)."""
        studies = list(self.collection.find({}, {"_id": 0, "image_b64": 0}))
        return [_clean(s) for s in studies]

    def get_all_studies_full(self):
        """Return all studies including image data (use sparingly)."""
        studies = list(self.collection.find({}, {"_id": 0}))
        return [_clean(s) for s in studies]

    def get_study(self, study_name, company_name):
        query = {"study_name": study_name, "company_name": company_name}
        study = self.collection.find_one(query, {"_id": 0})
        return _clean(study)

    def add_study(self, study_data):
        result = self.collection.insert_one(study_data)
        return str(result.inserted_id)

    def add_gaze_session(self, study_name: str, company_name: str, gaze_points: list):
        """Append a new gaze session to an existing study's gaze_sessions array."""
        session = {
            "recorded_at": datetime.utcnow().isoformat(),
            "gaze_points": gaze_points,
        }
        self.collection.update_one(
            {"study_name": study_name, "company_name": company_name},
            {"$push": {"gaze_sessions": session}}
        )

    def update_study(self, study_name, company_name, update_data):
        query = {"study_name": study_name, "company_name": company_name}
        update = {"$set": update_data}
        result = self.collection.update_one(query, update)
        return result.modified_count

    def delete_study(self, study_name, company_name):
        query = {"study_name": study_name, "company_name": company_name}
        result = self.collection.delete_one(query)
        return result.deleted_count


class UserDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = dataBase["UserCollection"]

    def get_all_users(self):
        users = list(self.collection.find({}, {"_id": 0, "password_hash": 0}))
        return [_clean(u) for u in users]

    def add_user(self, user_data):
        result = self.collection.insert_one(user_data)
        return str(result.inserted_id)

    def get_user(self, user_id):
        query = {"user_id": user_id}
        user = self.collection.find_one(query, {"_id": 0})
        return _clean(user)

    def update_user(self, user_id, update_data):
        query = {"user_id": user_id}
        update = {"$set": update_data}
        result = self.collection.update_one(query, update)
        return result.modified_count

    def delete_user(self, user_id):
        query = {"user_id": user_id}
        result = self.collection.delete_one(query)
        return result.deleted_count