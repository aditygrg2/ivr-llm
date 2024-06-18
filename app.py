from enum import Enum
from mongoengine import connect
from dotenv import load_dotenv
import os
import models.address as Address, models.orders as Order, models.product as Product, models.transactionDetail as Transaction, models.user as User
from VerificationChain import VerificationChain, VerificationChainStatus
from DuringChain import DuringChain, DuringChainStatus
from bson.json_util import dumps
from flask import Flask
from flask_socketio import SocketIO, emit
from io import BytesIO
from uuid import uuid4
import speech_recognition as sr
from gtts import gTTS
from pydub.utils import which
from pydub import AudioSegment
from flask_cors import CORS
from pydub.playback import play
import base64
import subprocess

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app,cors_allowed_origins="*")

recognizer = sr.Recognizer()
AudioSegment.converter = which("ffmpeg")

client = connect(host=os.environ['MONGO_URL'])

all_users = client.list_database_names()
print(all_users)

user_dict = {

}

class CallStatus(Enum):
    VerificationChainNotStarted = 0
    VerificationChainStarted = 1
    DuringChainStarted = 2

@socketio.on('send_audio')
def handle_audio(data):
    try:
        phone_number = data['phone_number']
        data = data['data']

        if(phone_number not in user_dict.keys()):
            phone_dict = {
                'call_status':  CallStatus.VerificationChainNotStarted,
                "verification_chain": None,
                "during_chain": None,
                "user_query": "",
            }

            user_dict[phone_number] = phone_dict
        
        audio_data = base64.b64decode(data)
        u = uuid4()

        if(not os.path.exists(f"audios/{phone_number}")):
            os.mkdir(f"audios/{phone_number}")
        
        with open(f'audios/{phone_number}/{u}.mp3', 'wb') as audio_file:
            audio_file.write(audio_data)

        subprocess.call(['ffmpeg', '-i', f'audios/{phone_number}/{u}.mp3', f'audios/{phone_number}/{u}.wav'])
        
        with sr.AudioFile(f'audios/{phone_number}/{u}.wav') as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio)

            user_data = """
                    [{
                "name": "Raj Patel",
                "address": {
                "phone_number": 932489237
                "apartment_no": "223, Suryasthali Appartment",
                "area_street": "Manavta Nagar",
                "landmark": "Hanuman Mandir",
                "town_city": "Bengaluru",
                "state": "Karnataka",
                "pincode": 530068
                },
                "email": "raja23@gmail.com",
                "subscriptionStatus": false,
                "previousOrders": [
                    {
                "order_id": “20234435843-1107”,
                "status": "Delivered",
                "transaction": {
                "transaction_id": "txn123dsafasd",
                "status": "Successful",
                "payment_method": "Amazon Pay",
                "total_amount": 3000,
                "timestamp": {
                    "$date": "2024-06-14T18:55:34.443Z"
                }
                },
                "items": [
                "product_id": 3247387,
                "name": "HRX Oversized T-Shirt",
                "description": "Cotton-Comfy fit Oversized T-Shirt",
                "category": "Clothing-Men-TShirt",
                "average_rating": 3,
                "price": 399,
                "reviews": [
                    "Very Comfortable and Affordable",
                    "Cheap and affordable",
                    "Don't BUY AT ALLLL"
                ]
                ],
            """

            print(user_dict)

            if(user_dict[phone_number]['call_status'] == CallStatus.VerificationChainNotStarted):
                user_dict[phone_number]['user_query'] = text
                user_dict[phone_number]['verification_chain'] = VerificationChain(user_data=user_data, user_query=text)
                chat = user_dict[phone_number]['verification_chain'].start_chat()
                print("124", chat)
                user_dict[phone_number]['call_status'] = CallStatus.VerificationChainStarted
                print("End Not Started")
                convert_to_audio_and_send(chat[1])
                
            elif(user_dict[phone_number]['call_status'] == CallStatus.VerificationChainStarted):
                response = user_dict[phone_number]['verification_chain'].send_message(text)
                print("130", response)

                chain_status = response[0]

                if(chain_status == VerificationChainStatus.NOT_VERIFIED):
                    convert_to_audio_and_send(response[1])
                    user_dict[phone_number]['call_status'] = CallStatus.VerificationChainNotStarted
                    
                elif(chain_status == VerificationChainStatus.IN_PROGRESS):
                    convert_to_audio_and_send(response[1])
                
                else:
                    print("During chain started")
                    user_dict[phone_number]['during_chain'] = DuringChain(user_data=user_data, user_query=user_dict[phone_number]['user_query'])
                    chat_instance = user_dict[phone_number]['during_chain'].initialize_model()
                    response = user_dict[phone_number]['during_chain'].start_chat()
                    user_dict[phone_number]['call_status'] = CallStatus.DuringChainStarted
                    handle_during_chain_conditions(response)

            else:
                response = user_dict[phone_number]['during_chain'].send_message(text)
                handle_during_chain_conditions(response, phone_number)

    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
    finally:
        user_dict[phone_number]['first_time'] = False

def convert_to_audio_and_send(text):
    print("AI Text", text)
    tts = gTTS(text)
    audio_output_buffer = BytesIO()
    tts.write_to_fp(audio_output_buffer)
    audio_output_buffer.seek(0)

    emit('receive_audio', audio_output_buffer.getvalue(), binary=True)
    return "something"

def handle_during_chain_conditions(response, phone_number):
    status = response[0]
    reply = response[1]

    if(status == DuringChainStatus.AGENT_TRANSFERRED or status == DuringChainStatus.TERMINATED):
        del user_dict[phone_number]

    print(reply, status)
    convert_to_audio_and_send(reply)

socketio.run(app, debug=True, host='0.0.0.0', port=8000)