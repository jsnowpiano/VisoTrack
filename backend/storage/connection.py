from pymongo import MongoClient
from dataclasses import dataclass

uri  = "mongodb+srv://d00419226:DBMikuBot2122Magic@cluster0.h6fp6.mongodb.net/?appName=Cluster0"

client = MongoClient(uri)

dataBase = client["ResearchStudyDatabase"]

collection = dataBase["ResearchStudyCollection"] 

class StudyDatabaseConnection:
    def __init__(self):
        self.client = client
        self.database = dataBase
        self.collection = collection
    
    def add_study(self, study_data):
        result = self.collection.insert_one(study_data)
        return result.inserted_id
    
    def get_study(self, study_name, company_name):
        query = {"study_name": study_name, "company_name": company_name}
        study = self.collection.find_one(query)
        return study

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
    
    def add_user(self, user_data):
        result = self.collection.insert_one(user_data)
        return result.inserted_id
    
    def get_user(self, user_id):
        query = {"user_id": user_id}
        user = self.collection.find_one(query)
        return user

    def update_user(self, user_id, update_data):
        query = {"user_id": user_id}
        update = {"$set": update_data}
        result = self.collection.update_one(query, update)
        return result.modified_count
    
    def delete_user(self, user_id):
        query = {"user_id": user_id}
        result = self.collection.delete_one(query)
        return result.deleted_count