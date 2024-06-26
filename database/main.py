from pymongo import MongoClient
import os

from dotenv import load_dotenv
load_dotenv()

client = MongoClient(os.environ['MONGO_URL'])
db = client['amazon_data']
userCollection = db['User']
analysis = db['analysis']
trackers = db['trackers']

class Database():
    def __init__(self) -> None:
        self.userCollection = userCollection
        self.analysisCollection = analysis
        self.trackerCollection = trackers

    def get_user(self, phone_number):
        projection = {
            '_id': 0
        }
        return self.userCollection.find_one({"phone_number": phone_number}, projection)
    
    def get_user_data_for_verification(self, phone_number):
        print(phone_number, "queried")
        fields = ['phone_number', 'name', 'town_city', 'state', 'pincode']
        projection = {field: 1 for field in fields}
        projection['_id'] = 0
        data = self.userCollection.find_one({"phone_number": phone_number}, projection)
        print(data)
        return data

    def insert_audio_analysis(self, phone_number, data):
        # {
        #     "phoneNumber":"9878500123",
        #     "call_st":[
        #         {
        #             "type":"AI",
        #             "sent":'pos',
        #             "file":"filepath"
        #         },
        #         {
        #             "type":"human",
        #             "sent":'pos',
        #             "file":"fielpath"
        #         },
        #         ...
        #     ],
        #     "trackers":[
        #         {
        #             "title":"Amazon great indian sale",
        #             "trackerCount":{
        #                 "winter":2,
        #                 "great":3
        #             }
        #         },
        #         ...
        #     ],
        #     "aegnt_feedback": {
        #         "score": 7,
        #         "text":"It's nice"
        #     }
        # }
        try:
            analysis.update_one({"phone_number":phone_number},{"$push": {"call_sent": data}},upsert=True)
        except Exception as e:
            print(e)

    def get_trackers(self):
        return self.trackerCollection.find()
    
    def insert_tracker_analysis(self, phoneNumber, data, chat_history):
        try:
            self.analysisCollection.update_one({"phone_number": phoneNumber},{'$set':{"trackers": data,"transcribe": chat_history}},upsert=True)
        except Exception as e:
            print(e)

    def insert_merged_audio_link(self, phone_number, merged_audio_link):
        try:
            self.analysisCollection.update_one({"phone_number": phone_number},{'$set':{"merged_audio_link": merged_audio_link}},upsert=True)
        except Exception as e:
            print(e)
    
    def insert_feedback_analysis(self,phoneNumber, data):
        try:
            feedback = {
                "score":data['score'],
                "text": data['text']
            }
            self.analysisCollection.update_one({"phone_number":phoneNumber},{"$set":{"contact_feedback":feedback}},upsert=True)
        except Exception as e:
            print(e)

    def insert_feedback_analysis_ai(self,phoneNumber, data):
        try:
            feedback = {
                "score":data['score'],
                "text": data['text']
            }
            self.analysisCollection.update_one({"phone_number":phoneNumber},{"$set":{"agent_feedback": feedback}},upsert=True)
        except Exception as e:
            print(e)
    
    def get_analyzed_data(self):
        try:
            return self.analysisCollection.find()
        except Exception as e:
            print(e)