from enum import Enum
import vertexai
import os
from vertexai.generative_models import GenerativeModel
from langchain.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.vectorstores import FAISS
from vertexai.generative_models import (
    FunctionDeclaration,
    GenerationConfig,
    GenerativeModel,
    SafetySetting,
    HarmCategory,
    HarmBlockThreshold,
    Part,
    Tool,
)


class DuringChainStatus(Enum):
    TERMINATED = 0
    AGENT_TRANSFERRED = 1
    IN_PROGRESS_USER_QUERY = 2
    IN_PROGRESS_RETRIEVAL = 3
    IN_PROGRESS_GENERAL = 4


SYSTEM_INSTRUCTION = """
    Your name is Radhika from Amazon Customer Support Agent Team.

    You are on a call. 
    
    You can use any of the tools for help 
    get_data_of_user,
    get_answers_to_general_help,
    terminate_if_satisfied,
    send_to_agent_for_manual_intervention

    Do not verify anything about user because he is already verified.

    You can ask user if you need any details.
    
    If you are unable to find the answer, forward the call to agent by calling 'send_to_agent_for_manual_intervention'

    You can only tell the user about things, you cannot help if any thing needs to be executed. 
    For example, you cannot execute an return but you can only tell info about it.

    DO NOT MAKE UP ANSWERS/DETAILS OF YOUR OWN.
"""

class DuringChain():
    def __init__(self, user_data, user_query, system_instruction = SYSTEM_INSTRUCTION) -> None:
        vertexai.init(location=os.environ['LOCATION'], project=os.environ['PROJECT_ID'])
        self.user_data = user_data
        self.user_query = user_query
        self.safety_config = [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_UNSPECIFIED,
                threshold=HarmBlockThreshold.BLOCK_NONE
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_NONE
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_NONE
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.BLOCK_NONE
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.BLOCK_NONE
            )
        ]

    def get_tools(self):
        get_data_of_user = FunctionDeclaration(
            name = "get_data_of_user",
            description = 
            """
                Do not mock up any info, ask here if you need any info.
                Get data of User, his orders, product, transactions, items info and any other profile details.
            """,
            parameters = {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            }
        )

        get_info_about_query = FunctionDeclaration(
            name = "get_info_about_query",
            description = """
            This searches through help docs of the Amazon Pages and finds relevant information about refund policy, cancellation policy and from other help related pages. 
            You can take data from here to understand better about the solutions if not known to you already.
            """,
            parameters = {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            }
        )

        terminate_if_satisfied = FunctionDeclaration(
            name = "terminate_if_satisfied",
            description = "Checks if the user seems satisfied with the answer and terminates the chat accordingly.",
            parameters = {
                "type": "object",
                "properties": {"feedback_user": {"type": "string"}},
            }
        )

        send_to_agent_for_manual_intervention = FunctionDeclaration(
            name = "send_to_agent_for_manual_intervention",
            description = "Sends the query to a human agent for manual intervention when the LLM is unable to process it.",
            parameters = {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            }
        )

        tools = Tool(
            function_declarations=[
                get_data_of_user,
                get_info_about_query,
                terminate_if_satisfied,
                send_to_agent_for_manual_intervention
            ],
        )

        return tools
        

    def initialize_model(self):
        model = GenerativeModel(
            "gemini-1.5-pro-001",
            generation_config=GenerationConfig(temperature=0.5),
            tools=[self.get_tools()],
            system_instruction=SYSTEM_INSTRUCTION,
            safety_settings=self.safety_config
        )

        chat = model.start_chat(response_validation=False)
        self.chat = chat

        return chat

    def format_text(self, text):
        return "".join(text.split("\n"))

    def start_chat(self):
        response = self.chat.send_message(self.user_query)

        return self.validate_response(response)

    def validate_response(self, response):
        final_response = ""

        function_call = response.candidates[0].content.parts[0].function_call

        print(function_call)

        if(not function_call):
            ai_reply = self.format_text(response.candidates[0].content.parts[0].text)
            return (DuringChainStatus.IN_PROGRESS_GENERAL, self.format_text(ai_reply))
        else:
            function_name = response.candidates[0].content.parts[0].function_call.name

            if(function_name == "send_to_agent_for_manual_intervention"):
                final_response = """You will soon receive a call from an agent. Thank you for contacting Amazon! This call can now be terminated."""
                return (DuringChainStatus.AGENT_TRANSFERRED, final_response)
            
            elif(function_name == "terminate_if_satisfied"):
                feedback = function_call.args['feedback']

                # TODO LOG IT SOMEWHERE IN ANALYTICS

                final_response = """Thank you for calling Amazon. Have an amazing day!"""
                return (DuringChainStatus.TERMINATED, final_response)
            
            elif(function_name == "get_data_of_user"):
                question = function_call.args['query']

                response = self.send_message(
                    Part.from_function_response(
                        name=function_name,
                        response={
                            "content": self.get_data_of_user_chain(question),
                        },
                    ),
                )

                return (DuringChainStatus.IN_PROGRESS_USER_QUERY, self.format_text(response.candidates[0].content.parts[0].text))

            elif(function_name == "get_answers_to_general_help"):
                response = self.send_message(
                    Part.from_function_response(
                        name = function_name,
                        response = {
                            "content": self.get_info_about_query(question)
                        }
                    )
                )

                return (DuringChainStatus.IN_PROGRESS_RETRIEVAL, self.format_text(response.candidates[0].content.parts[0].text))

            else:
                return (DuringChainStatus.AGENT_TRANSFERRED,"""You will soon receive a call from an agent. Thank you for contacting Amazon! This call can now be terminated.""")

    def send_message(self, input):
        response = self.chat.send_message(input)
        return self.validate_response(response)

    def get_data_of_user_chain(self, question):
        try: 
            template = """
                Use the following pieces of context (JSON) which is everything of user data to answer the question at the end.
                If you don't know the answer, just say that you don't know, don't try to make up an answer.

                {context}

                Question: Find {question}

                Helpful Answer:"""
            
            prompt = PromptTemplate(
                input_variables=["context", "question"],
                template=template
            )

            sol = prompt.format(context = self.user_data, question = question)

            print(sol)

            model = GenerativeModel(
                "gemini-1.5-pro-001",
                generation_config=GenerationConfig(temperature=0.5),
                safety_settings=None
            )

            chat = model.start_chat(response_validation = False)
            response = chat.send_message(sol)

            if(not response):
                return "There is no data available. Please transfer the call to agent."

            print(response)

            return self.format_text(response.candidates[0].content.parts[0].text)
        except Exception as e:
            print("get_data_of_user_chain", e)

    def get_info_about_query(self, user_question):
        model = ChatGoogleGenerativeAI(
            model="gemini-pro",
            client=genai,
            temperature=0.5,
            safety_settings=None
        )

        embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001")

        new_db = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)

        def filter_contexts(term):
            contexts = new_db.similarity_search_with_score(term, k=3)

            ans_contexts = []

            for i in contexts:
                print(i[1])
                if(i[1] > 0.5):
                    ans_contexts.append(i[0].page_content)

            return ans_contexts

        data = filter_contexts(user_question)
        return "".join(data)