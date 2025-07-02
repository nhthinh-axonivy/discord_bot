from pymongo import MongoClient
import os

class Database:
    def __init__(self):
        self.client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.client["prison_bot"]

    def get_user(self, user_id):
        return self.db["users"].find_one({"user_id": user_id})

    def update_user(self, user_id, data):
        self.db["users"].update_one({"user_id": user_id}, {"$set": data}, upsert=True)

db = Database()
