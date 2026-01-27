from pymongo import MongoClient

uri  = "mongodb+srv://d00419226:DBMikuBot2122Magic@cluster0.h6fp6.mongodb.net/?appName=Cluster0"

client = MongoClient(uri)

dataBase = client["ResearchStudyDatabase"]

collection = dataBase["ResearchStudyCollection"]