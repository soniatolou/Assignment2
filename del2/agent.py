import os
import json
import subprocess
import yaml
from openai import OpenAI
from dotenv import load_dotenv
from safety import is_safe
from logger import setup_logger, log_event

load_dotenv()

# ansluter till openai
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# läser in system-prompt och inställningar från config-filen
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

config = load_config()
SYSTEM_PROMPT = config["system_prompt"]
MAX_OUTPUT_CHARS = config["max_output_chars"]

def call_llm(messages):
    # skickar hela konversationen till modellen och får tillbaka råtext
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, max_tokens=1000, temperature=0
    )
    return response.choices[0].message.content


def parse_action(text):
    # letar igenom texten rad för rad efter action och action input
    action = None
    action_input = None

    for line in text.strip().split("\n"):
        if line.startswith("Action:"):
            action = line.replace("Action:", "").strip()
        if line.startswith("Action Input:"):
            action_input = line.replace("Action Input:", "").strip()

    return action, action_input


def parse_final_answer(text):
    # kollar om modellen är klar och har ett slutsvar
    for line in text.strip().split("\n"):
        if line.startswith("Final Answer:"):
            return line.replace("Final Answer:", "").strip()
    return None


def run_bash(command):
    # kollar säkerheten först innan vi ens frågar användaren
    safe, reason = is_safe(command)
    if not safe:
        print(f"\n[BLOCKERAT] {reason}")
        return f"kommando blockerades: {reason}"

    # frågar användaren om det är okej att köra kommandot
    print(f"\n[BASH] agenten vill köra: {command}")
    confirm = input("tillåt? (y/n): ").strip().lower()

    if confirm != "y":
        return "kommando nekades av användaren"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        # kapper outputen så att contexten inte blir för stor
        return output[:2000] if output else "(inget output)"
    except subprocess.TimeoutExpired:
        return "timeout - kommandot tog för lång tid"
    except Exception as e:
        return f"fel: {str(e)}"


def react_loop(user_input, log_file):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    max_iterations = 10

    for i in range(max_iterations):
        print(f"\n--- iteration {i+1} ---")

        response = call_llm(messages)
        print(response)

        # loggar modellens svar
        log_event(log_file, "llm_response", {"iteration": i+1, "response": response})

        action, action_input = parse_action(response)

        if action and action_input:
            if action.lower() == "bash":
                observation = run_bash(action_input)
            else:
                observation = f"okänt verktyg: {action}"

            print(f"\nobservation: {observation}")

            # loggar bash-anropet och resultatet
            log_event(log_file, "tool_call", {
                "iteration": i+1,
                "action": action,
                "action_input": action_input,
                "observation": observation
            })

            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
            continue

        final_answer = parse_final_answer(response)
        if final_answer:
            print(f"\nsvar: {final_answer}")
            # loggar slutsvaret
            log_event(log_file, "final_answer", {"answer": final_answer})
            return

        print("kunde inte parsa action, avslutar")
        break

    print("max iterationer nådda")

def main():
    log_file = setup_logger()
    print(f"react agent del 1 - skriv 'quit' för att avsluta\n")
    print(f"loggar sparas i: {log_file}\n")
    while True:
        user_input = input("du: ").strip()
        if user_input.lower() == "quit":
            break
        if not user_input:
            continue
        log_event(log_file, "user_input", {"message": user_input})
        react_loop(user_input, log_file)


if __name__ == "__main__":
    main()