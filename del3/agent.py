import os
import time
import requests
import yaml
from openai import OpenAI
from dotenv import load_dotenv
from logger import setup_logger, log_event

load_dotenv()

# läser in config från yaml-filen
def load_config():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    with open(config["system_prompt_file"], "r") as f:
        config["system_prompt"] = f.read()
    return config

config = load_config()

# ansluter till openai
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HUB_URL = config["hub_url"]
HUB_PASSWORD = os.getenv("HUB_PASSWORD")
AGENT_NAME = os.getenv("AGENT_NAME")
MAX_MESSAGES = config["max_messages"]
POLL_INTERVAL = config["poll_interval"]


def fetch_messages(since):
    # hämtar nya meddelanden från hubben sedan senaste seq
    try:
        resp = requests.get(
            f"{HUB_URL}/api/messages",
            params={"since": since, "password": HUB_PASSWORD},
            timeout=10
        )
        return resp.json().get("messages", [])
    except Exception as e:
        print(f"fel vid hämtning: {e}")
        return []


def post_message(content):
    # skickar ett meddelande till hubben
    try:
        resp = requests.post(
            f"{HUB_URL}/api/message",
            json={
                "agent_name": AGENT_NAME,
                "content": content,
                "password": HUB_PASSWORD
            },
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"fel vid skickning: {e}")
        return False


def should_respond(messages):
    # kollar om agenten är direkt adresserad
    for msg in messages[-5:]:
        if msg["agent_name"] == AGENT_NAME:
            continue
        if f"@{AGENT_NAME}" in msg["content"].lower():
            return True
    return False


def call_llm(messages):
    # skickar konversationen till modellen och får tillbaka svar
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=300,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


def build_conversation(messages):
    # bygger upp konversationshistoriken för modellen
    conversation = [{"role": "system", "content": config["system_prompt"]}]
    for msg in messages[-20:]:
        role = "assistant" if msg["agent_name"] == AGENT_NAME else "user"
        conversation.append({
            "role": role,
            "content": f"[{msg['agent_name']}]: {msg['content']}"
        })
    conversation.append({
        "role": "user",
        "content": "Based on the conversation above, write a short response OR reply with exactly 'PASS' if you have nothing to add."
    })
    return conversation


def main():
    log_file = setup_logger()
    print(f"agent {AGENT_NAME} startad")
    print(f"max meddelanden: {MAX_MESSAGES}")
    print(f"loggar sparas i: {log_file}\n")

    last_seen = 0
    messages_sent = 0

    while messages_sent < MAX_MESSAGES:
        # hämtar nya meddelanden
        new_messages = fetch_messages(last_seen)

        if not new_messages:
            time.sleep(POLL_INTERVAL)
            continue

        last_seen = new_messages[-1]["seq"]

        # loggar och skriver ut nya meddelanden
        for msg in new_messages:
            if msg["agent_name"] != AGENT_NAME:
                print(f"[{msg['agent_name']}]: {msg['content'][:80]}")
                log_event(log_file, "incoming_message", msg)

        # kollar om vi ska svara
        if not should_respond(new_messages):
            time.sleep(POLL_INTERVAL)
            continue

        # frågar modellen vad den ska svara
        conversation = build_conversation(new_messages)
        reply = call_llm(conversation)

        if reply.upper() == "PASS":
            print("[PASS] agenten väljer att inte svara")
            log_event(log_file, "pass", {})
            time.sleep(POLL_INTERVAL)
            continue

        # skickar svaret till hubben
        if post_message(reply):
            messages_sent += 1
            print(f"[{AGENT_NAME}] ({messages_sent}/{MAX_MESSAGES}): {reply[:80]}")
            log_event(log_file, "outgoing_message", {
                "content": reply,
                "messages_sent": messages_sent
            })

        time.sleep(POLL_INTERVAL)

    print(f"klar - skickade {messages_sent} meddelanden")


if __name__ == "__main__":
    main()