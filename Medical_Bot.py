from datetime import date, datetime
import os
import pymysql
from pymongo import MongoClient
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = OpenAI(api_key=api_key)

st.set_page_config(page_title="Eva - Well-Being Companion", layout="wide")


mongo_client = MongoClient(mongo_uri)
mongo_db = mongo_client["medical_bot_db"]
chat_collection = mongo_db["chat_history"]

def get_mongo_chat_history(client_name: str, limit: int = 20):
    cursor = chat_collection.find(
        {"client_name": client_name.strip().lower()}
    ).sort("timestamp", -1).limit(limit)
    
    records = list(cursor)
    records.reverse()  
    return [{"role": r["role"], "content": r["content"]} for r in records]

def save_mongo_chat_message(client_name: str, role: str, content: str):
    chat_collection.insert_one({
        "client_name": client_name.strip().lower(),
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow()
    })


def get_db_connection():
    return pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="mat1",
        password="arjun",
        database="mat1",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS medical_bot (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(50),
                    email VARCHAR(50),
                    mobile_number VARCHAR(20),
                    dob DATE,
                    gender VARCHAR(15),
                    country VARCHAR(30),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

init_db()

def get_user_by_name(name: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM medical_bot WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s)) ORDER BY id DESC LIMIT 1",
                (name,)
            )
            return cur.fetchone()

def create_user(name, email, mobile_number, dob, gender, country, description):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = """
                INSERT INTO medical_bot (name, email, mobile_number, dob, gender, country, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(query, (
                name.strip(),
                email.strip(),
                mobile_number.strip(),
                dob,
                gender,
                country,
                description.strip()
            ))


if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_client_name" not in st.session_state:
    st.session_state.active_client_name = ""

def end_chat_session():
    st.session_state.messages = []
    st.session_state.active_client_name = ""
    st.session_state["client_name_field"] = ""


st.sidebar.title("Client Profile")
client_name_input = st.sidebar.text_input("Enter Client Name", key="client_name_field")

current_client = None

if client_name_input.strip():
    normalized_name = client_name_input.strip().lower()

    if st.session_state.active_client_name != normalized_name:
        st.session_state.active_client_name = normalized_name
        current_client = get_user_by_name(client_name_input)

        if current_client:
            st.session_state.messages = get_mongo_chat_history(current_client["name"])
        else:
            st.session_state.messages = []
    else:
        current_client = get_user_by_name(client_name_input)

    if current_client:
        st.sidebar.success(f"Record found for: {current_client['name']}")
        st.sidebar.write(f"**Email:** {current_client.get('email', 'N/A')}")
        st.sidebar.write(f"**Contact:** {current_client.get('mobile_number', 'N/A')}")
        st.sidebar.write(f"**Country:** {current_client.get('country', 'N/A')}")
        st.sidebar.write(f"**Gender:** {current_client.get('gender', 'N/A')}")
        if current_client.get("description"):
            st.sidebar.info(f"**Description:**\n{current_client['description']}")

        st.sidebar.divider()
        st.sidebar.button("End Chat Session", type="primary", use_container_width=True, on_click=end_chat_session)
    else:
        st.sidebar.warning(f"No record found for '{client_name_input}'. Please register below:")
        with st.sidebar.form("quick_reg_form"):
            reg_email = st.text_input("Email")
            reg_mobile = st.text_input("Mobile Number")
            reg_dob = st.date_input(
                "Date of Birth",
                value=date(1995, 1, 1),
                min_value=date(1920, 1, 1),
                max_value=date.today()
            )
            reg_gender = st.selectbox("Gender", ("Male", "Female", "Others"))
            reg_country = st.selectbox("Country", ("India", "USA", "UK", "UAE", "Others"))
            reg_description = st.text_area("Description")
            submit_reg = st.form_submit_button("Save & Register")

            if submit_reg:
                if not reg_email or not reg_mobile:
                    st.sidebar.error("Email and Mobile Number are required.")
                else:
                    create_user(client_name_input, reg_email, reg_mobile, reg_dob, reg_gender, reg_country, reg_description)
                    st.sidebar.success("Client registered successfully! Refreshing...")
                    st.rerun()
else:
    if st.session_state.active_client_name != "":
        st.session_state.messages = []
        st.session_state.active_client_name = ""
    st.sidebar.info("Please enter a name above to begin.")

st.title("Eva - Your Well-Being Companion")

if not current_client:
    st.info("Welcome! Please enter your name in the sidebar to start or continue your session.")
else:
    col_status, col_btn = st.columns([0.82, 0.18])
    with col_status:
        st.caption(f"Currently chatting with: **{current_client['name']}**")
    with col_btn:
        st.button("End Chat", key="main_end_btn", on_click=end_chat_session)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("How are you feeling right now?"):
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        save_mongo_chat_message(current_client["name"], "user", prompt)

        past_turns = get_mongo_chat_history(current_client["name"], limit=40)
        formatted_history = "\n".join([f"- {t['role'].upper()}: {t['content']}" for t in past_turns[:-1]])

        client_context = f"""
        CLIENT PROFILE FROM DATABASE:
        - Name: {current_client['name']}
        - Description: {current_client.get('description', 'None provided')}
        - Country: {current_client.get('country', 'Not specified')}

        RECORDED PAST CHATS & ONGOING ISSUES (FROM DATABASE):
        \"\"\"
        {formatted_history if formatted_history else "No previous chat history recorded."}
        \"\"\"
        """

        system_instruction = f"""
        You are Eva, an empathetic Well-Being Companion.

        {client_context}

        CRITICAL INSTRUCTIONS FOR CONTINUITY:
        1. PRIOR CONVERSATION RECALL: Thoroughly review the 'RECORDED PAST CHATS & ONGOING ISSUES' above. 
           - Identify any recurring stressors, emotional struggles, symptoms (e.g., anxiety, sleep problems, burnout), or life events the client previously brought up.
           - Acknowledge or gently check in on those issues when responding to their latest message. Show them you remember their past context.
        2. VALIDATION & ACTIVE LISTENING: Validate their current feelings without being sycophantic. Ask meaningful follow-up questions linked to their ongoing journey.
        3. BOUNDARIES: You are not a medical doctor or licensed psychiatrist. Do not offer formal clinical diagnoses or prescribe medication.
        4. NO NEED FOR APOLOGY: Avoid unnecessary apologies for past conversations. Instead, focus on moving the conversation forward with empathy and support.
        5. RESPONSE STYLE: Keep your responses warm, grounded, and conversational. Offer practical practices.
        6. RELEVANT RESPONSES: Give only the responses related to client's well-being, emotional support, and self-reflection. Avoid generic or unrelated advice. No need of out of box responses.If they ask such questions avoid answering and gently redirect the conversation back to their well-being.
        """

        payload = [{"role": "system", "content": system_instruction}]
        for msg in st.session_state.messages[-20:]:
            payload.append({"role": msg["role"], "content": msg["content"]})

        with st.chat_message("assistant"):
            try:
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=payload,
                    temperature=0.1,
                    max_tokens=400
                )
                reply = res.choices[0].message.content
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})

                # Save assistant turn to MongoDB
                save_mongo_chat_message(current_client["name"], "assistant", reply)

            except Exception as e:
                st.error(f"Error connecting to AI service: {e}")