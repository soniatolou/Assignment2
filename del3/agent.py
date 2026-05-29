import os
import json
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


GROUP_TRIGGERS = ["all agents", "alla agenter", "attention agents", "agents", "everyone", "@all", "@everyone"]
SILENCE_WORDS = ["quiet", "stop", "tyst", "silence", "halt", "be quiet", "stop writing", "sluta skriva", "håll tyst", "pause"]


def is_silence_command(messages):
    # kollar om någon ber hela gruppen vara tyst
    for msg in messages:
        if msg["agent_name"] == AGENT_NAME:
            continue
        content = msg["content"].lower()
        has_group = any(t in content for t in GROUP_TRIGGERS)
        has_silence = any(w in content for w in SILENCE_WORDS)
        if has_group and has_silence:
            return True
        # direkt tystnad-kommando utan grupptrigger
        if has_silence and ("sonia" in content or AGENT_NAME.lower() in content):
            return True
    return False


def should_respond(messages):
    # kollar alla nya meddelanden
    for msg in messages:
        if msg["agent_name"] == AGENT_NAME:
            continue
        content = msg["content"].lower()
        if f"@{AGENT_NAME}".lower() in content or AGENT_NAME.lower() in content or "sonia" in content:
            return True, True  # direkt adresserad, tvingat svar
        if any(t in content for t in GROUP_TRIGGERS):
            return True, False  # gruppadresserad, kan passa
    return False, False


def is_too_similar(reply, all_messages):
    # jämför svaret med agentens senaste egna meddelande
    own = [m["content"] for m in all_messages if m["agent_name"] == AGENT_NAME]
    if not own:
        return False
    last = own[-1].lower()
    words_last = set(last.split())
    words_reply = set(reply.lower().split())
    if not words_last:
        return False
    overlap = len(words_last & words_reply) / len(words_last)
    return overlap > 0.7


def call_llm(messages):
    # skickar konversationen och får tillbaka json-svar
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=600,
        temperature=0.7,
        response_format={"type": "json_object"}
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
        "content": 'Respond with exactly one JSON object. Use {"action": "final", "answer": "..."} to send a message, or {"action": "pass", "reason": "..."} to stay silent. Only pass if the message is clearly for another specific agent or fully resolved with nothing to add. IMPORTANT: if the task requires producing content (documentation, code, text), write the full content now in "answer" — do NOT say you will do it later.'
    })
    return conversation


def main():
    log_file = setup_logger()
    print(f"agent {AGENT_NAME} startad")
    print(f"max meddelanden: {MAX_MESSAGES}")
    print(f"loggar sparas i: {log_file}\n")

    last_seen = 0
    messages_sent = 0
    all_messages = []  # ackumulerar hela chatthistoriken
    initial_load = True  # första pollen är bara historik, svara inte
    silenced = False  # sätts till true om gruppen ombeds vara tyst

    while messages_sent < MAX_MESSAGES:
        new_messages = fetch_messages(last_seen)

        if not new_messages:
            time.sleep(POLL_INTERVAL)
            continue

        last_seen = new_messages[-1]["seq"]

        for msg in new_messages:
            if msg["agent_name"] != AGENT_NAME:
                print(f"[{msg['agent_name']}]: {msg['content'][:80]}")
                log_event(log_file, "incoming_message", msg)
        all_messages.extend(new_messages)

        # läser in historiken tyst utan att svara
        if initial_load:
            initial_load = False
            print(f"historik inläst: {len(all_messages)} meddelanden")
            time.sleep(POLL_INTERVAL)
            continue

        # aktivera tystnad om gruppen ombeds vara tyst (bara under aktiv session)
        if not initial_load and is_silence_command(new_messages):
            silenced = True
            print("[TYST] agenten tystades ned")
            log_event(log_file, "silenced", {})

        # kolla om agenten är direkt adresserad
        respond, forced = should_respond(new_messages)

        # en människa som direkt adresserar agenten häver tystnaden
        direct_from_human = any(
            m["agent_name"].startswith("human:") and
            ("sonia" in m["content"].lower() or AGENT_NAME.lower() in m["content"].lower())
            for m in new_messages
        )
        if direct_from_human:
            silenced = False

        # var tyst om silenced är satt, oavsett vad andra agenter säger
        if silenced:
            time.sleep(POLL_INTERVAL)
            continue

        # kalla llm även om en människa skriver, även utan trigger
        human_wrote = any(m["agent_name"].startswith("human:") for m in new_messages)

        if not respond and not human_wrote:
            time.sleep(POLL_INTERVAL)
            continue

        conversation = build_conversation(all_messages)

        # om agenten är direkt adresserad, tvinga svar
        if forced:
            conversation[-1]["content"] = 'You have been directly mentioned. You MUST respond. Use {"action": "final", "answer": "..."}.'

        raw = call_llm(conversation)

        # parsar json-svaret, försöker en gång till om det misslyckas
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            log_event(log_file, "json_error", {"raw": raw[:200]})
            print(f"json-fel, försöker igen: {raw[:80]}")
            raw = call_llm(conversation)
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                print(f"json-fel igen, hoppar över: {raw[:80]}")
                time.sleep(POLL_INTERVAL)
                continue

        action = result.get("action", "pass")

        if action == "pass":
            reason = result.get("reason", "")
            print(f"[PASS] {reason}")
            log_event(log_file, "pass", {"reason": reason})
            time.sleep(POLL_INTERVAL)
            continue

        reply = result.get("answer", "")
        if not reply:
            time.sleep(POLL_INTERVAL)
            continue

        # hoppa över om svaret liknar det senaste egna meddelandet
        if is_too_similar(reply, all_messages):
            print("[PASS] för likt senaste egna svaret")
            log_event(log_file, "pass", {"reason": "too similar to last own message"})
            time.sleep(POLL_INTERVAL)
            continue

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