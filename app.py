"""
App based on code from Ed Donner's 'Agents' course and repository:
https://github.com/ed-donner/agents

Original code (c) 2025 Ed Donner
Modifications and extensions (c) 2025 Amanda Hernández
Licensed under the MIT License (see LICENSE file).
"""

from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr
from datetime import datetime
import psycopg2
import uuid  # to generate unique session IDs


load_dotenv(override=True)
# Conection to the database
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)


def save_chat(session_id, question, answer):
    """Guarda un intercambio en Supabase"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO chat_logs (session_id, ts, question, answer)
        VALUES (%s, %s, %s, %s)
    """, (session_id, datetime.utcnow(), question, answer))
    conn.commit()
    cur.close()
    conn.close()

def push(text):
    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": os.getenv("PUSHOVER_TOKEN"),
            "user": os.getenv("PUSHOVER_USER"),
            "message": text,
        }
    )


def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Recording {question}")
    return {"recorded": "ok"}

record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address of this user"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            }
            ,
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

record_new_conversation_json = {
    "name": "new_conversation",
    "description": "Always use this tool to record that a user has started a new conversation and provided to you his or her name",
    "parameters": {
        "type": "object",
        "properties": {

            "name": {
                "type": "string",
                "description": "The user's name"
            }
            ,
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["name"],
        "additionalProperties": False
    }
}

tools = [{"type": "function", "function": record_user_details_json},
        {"type": "function", "function": record_unknown_question_json},
        {"type": "function", "function": record_new_conversation_json}]


class Me:

    def __init__(self):
        self.openai = OpenAI()
        self.name = "Amanda Hernández"
        reader = PdfReader("me/CV_Amanda_Hernandez.pdf")
        self.linkedin = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.linkedin += text
        with open("me/summary.txt", "r", encoding="utf-8") as f:
            self.summary = f.read()


    def handle_tool_call(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
        return results
    
    def system_prompt(self):
#         system_prompt = f"You are acting as {self.name}. You are answering questions on {self.name}'s website, \
# particularly questions related to {self.name}'s career, background, skills and experience. \
# Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. \
# You are given a summary of {self.name}'s background and LinkedIn profile which you can use to answer questions. \
# Be professional and engaging, as if talking to a potential client or future employer who came across the website. \
# If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
# If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "

        system_prompt = f" You are acting as {self. name}, an accomplished professional with a strong mix of technical expertise,\
strategic thinking, and interpersonal skills. You represent {self.name} on their personal website and \
respond to visitors' questions about {self.name}'s background, experience, and professional journey. \
Your goal is to convey {self.name}'s capabilities authentically and engagingly — highlighting not only \
technical depth and achievements but also soft skills such as leadership, collaboration, creativity, \
and adaptability. Speak with confidence and warmth, as if having a friendly yet insightful conversation \
with a potential employer, recruiter, or collaborator. You are given a summary of {self.name}'s background and LinkedIn profile to draw accurate, \
well-informed responses. Avoid sounding like a résumé; instead, tell concise and impactful stories \
that illustrate problem-solving ability, initiative, and measurable results. \
    The first thing you must do is kindly and politely ask the name of the user, to know whom you are talking to.\
    You can ask if the user wants to give you its email address, to know how to get in touch with them. \
        If you don't know the answer to a question, use your record_unknown_question tool to log it, \
even if the question seems minor or unrelated to the career topic. \
If the user seems interested in connecting or learning more, naturally guide the conversation toward \
getting in touch — ask for their email politely and record it using your record_user_details tool. \
Maintain a professional, engaging, and authentic tone at all times — representing {self.name} \
as both technically strong and personally inspiring."   
        system_prompt += f"\n\n## Summary:\n{self.summary}\n\n## LinkedIn Profile:\n{self.linkedin}\n\n"
        system_prompt += f"With this context, please chat with the user, always staying in character as {self.name}."
        return system_prompt
    
    def chat(self, message, history):
        messages = [{"role": "system", "content": self.system_prompt()}] + history + [{"role": "user", "content": message}]
        done = False
        while not done:
            response = self.openai.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
            if response.choices[0].finish_reason=="tool_calls":
                message = response.choices[0].message
                tool_calls = message.tool_calls
                results = self.handle_tool_call(tool_calls)
                messages.append(message)
                messages.extend(results)
            else:
                done = True
        return response.choices[0].message.content
    

# if __name__ == "__main__":
#     me = Me()
#     # gr.ChatInterface(fn=me.chat, type="messages",  title="🤖 Agente de Amanda Hernández",
#     #     description=("Soy un asistente conversacional que responde preguntas sobre el perfil, "\
#     #         "proyectos y experiencia profesional de Amanda. "\
#     #         "Pregúntame sobre habilidades técnicas, trayectoria o logros destacados.")).launch()
#     with gr.Blocks(title="Amanda's AI Assistant") as demo:
#         gr.Markdown("""
#         # 🤖 Amanda's AI Assistant 
#         Hey! I'm AImanda, the digital version of Amanda Hernández.
# Ask me anything about her career path, skills, and the projects she's most passionate about. 💬✨
#         """)

#         gr.ChatInterface(
#             fn=me.chat,
#             type="messages",
#             title="AImanda",
#         )

#     demo.launch()
# if __name__ == "__main__":
#     me = Me()

#     with gr.Blocks(title="AImanda") as demo:
#         chatbot = gr.Chatbot(
#             value=[(
#                 None,
#                 "👋 Hi! I'm **AImanda**, the digital version of Amanda Hernández.\n\n"
#                 "Ask me anything about her career path, skills, or the projects she's most passionate about. ✨"
#             )],
#             label="Chat with AImanda"
#         )

#         msg = gr.Textbox(placeholder="Type a message...")
#         send = gr.Button("Send")

#         def user_input(user_message, chat_history):
#             bot_reply = me.chat(user_message, chat_history)
#             chat_history.append((user_message, bot_reply))
#             return "", chat_history

#         send.click(user_input, [msg, chatbot], [msg, chatbot])

#     demo.launch()


if __name__ == "__main__":
    me = Me()
    session_id = str(uuid.uuid4())

    with gr.Blocks(title="AImanda") as demo:
        # Chat en formato OpenAI (role/content)
        chatbot = gr.Chatbot(
            type="messages",
            value=[{
                "role": "assistant",
                "content": (
                    "👋 Hi! I'm **AImanda**, the digital version of Amanda Hernández.\n\n"
                    "Ask me anything about her career path, skills, or the projects she's most passionate about. 💫"\
                ),
            }],
            label="Chat with AImanda",
        )

        msg = gr.Textbox(placeholder="Type a message…")
        send = gr.Button("Send")

        # Handler: actualiza el historial en formato role/content
        def user_input(user_message, chat_history):
            # chat_history es una lista de {"role","content"}
            chat_history = list(chat_history) if chat_history else []
            chat_history.append({"role": "user", "content": user_message})

            # tu función puede usar el historial ya en formato OpenAI
            bot_reply = me.chat(user_message, chat_history)

            chat_history.append({"role": "assistant", "content": bot_reply})
            # Save in the database
            try:
                save_chat(session_id, user_message, bot_reply)
            except Exception as e:
                print("⚠️ Error saving in the database:", e)
            return "", chat_history

        # Botón enviar
        send.click(user_input, [msg, chatbot], [msg, chatbot])

        # 2) Pulsar ENTER en el Textbox
        msg.submit(user_input, [msg, chatbot], [msg, chatbot])

        # Sugerencias (cajitas)
        suggested_prompts = [
            "What are Amanda’s main technical skills?",
            "Tell me about one of her favorite projects.",
            "What is her professional background?",
            "What makes Amanda’s approach unique?",
        ]
        with gr.Row():
            for prompt in suggested_prompts:
                gr.Button(prompt).click(
                    fn=user_input,
                    inputs=[gr.State(prompt), chatbot],
                    outputs=[msg, chatbot],
                )

        # Mensaje de bienvenida al cargar (por si recargas)
        demo.load(lambda: [{"role": "assistant", "content":
                            "👋 Hi! I'm **AImanda**, the digital version of Amanda Hernández.\n\n"
                    "Ask me anything about her career path, skills, or the projects she's most passionate about. 💫"}],
                  inputs=None, outputs=chatbot)

    demo.launch()
