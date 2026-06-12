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

def load_config():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    # läser in system-prompten från md-filen och ersätter template-variabler
    with open(config["system_prompt_file"], "r") as f:
        config["system_prompt"] = f.read().replace(
            "{{ max_output_chars }}", str(config["max_output_chars"])
        )
    
    return config

config = load_config()
SYSTEM_PROMPT = config["system_prompt"]
MAX_OUTPUT_CHARS = config["max_output_chars"]

def call_llm(messages):
    # skickar konversationen och får tillbaka strukturerad json
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=1000,
        temperature=0,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content


def run_bash(command):
    # kollar säkerheten först
    safe, reason = is_safe(command)
    if not safe:
        return f"blockerat: {reason}"

    # frågar användaren om det är okej
    print(f"\n[BASH] agenten vill köra: {command}")
    confirm = input("tillåt? (y/n): ").strip().lower()

    if confirm != "y":
        return "kommando nekades av användaren"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        # kapper outputen till max_output_chars från config
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n... output kappad vid {MAX_OUTPUT_CHARS} tecken"
        return output if output else "(inget output)"
    except subprocess.TimeoutExpired:
        return "timeout - kommandot tog för lång tid"
    except Exception as e:
        return f"fel: {str(e)}"


def edit_file(filepath, old_str, new_str):
    # läser in filen och byter ut ett specifikt avsnitt
    try:
        with open(filepath, "r") as f:
            content = f.read()

        if old_str not in content:
            return f"kunde inte hitta texten i {filepath}"

        new_content = content.replace(old_str, new_str, 1)

        with open(filepath, "w") as f:
            f.write(new_content)

        return f"filen {filepath} uppdaterad"
    except Exception as e:
        return f"fel vid fileditering: {str(e)}"


def react_loop(messages, user_input, log_file):
    messages.append({"role": "user", "content": user_input})

    max_iterations = 10

    for i in range(max_iterations):
        print(f"\n--- iteration {i+1} ---")

        # får tillbaka json istället för råtext
        response_text = call_llm(messages)
        print(response_text)

        log_event(log_file, "llm_response", {"iteration": i+1, "response": response_text})

        # parsar json-svaret
        try:
            response = json.loads(response_text)
        except json.JSONDecodeError:
            print("kunde inte parsa json, avslutar")
            break

        # kollar om modellen är klar
        if response.get("final_answer"):
            print(f"\nsvar: {response['final_answer']}")
            log_event(log_file, "final_answer", {"answer": response["final_answer"]})
            messages.append({"role": "assistant", "content": response_text})
            return

        action = response.get("action")
        action_input = response.get("action_input")

        if not action or not action_input:
            print("ingen action hittades, avslutar")
            break

        # kör rätt verktyg
        if action == "bash":
            observation = run_bash(action_input)
        elif action == "edit_file":
            # action_input ska vara en dict med filepath, old_str, new_str
            try:
                args = json.loads(action_input)
                observation = edit_file(args["filepath"], args["old_str"], args["new_str"])
            except Exception as e:
                observation = f"fel vid edit_file: {str(e)}"
        else:
            observation = f"okänt verktyg: {action}"

        print(f"\nobservation: {observation}")

        log_event(log_file, "tool_call", {
            "iteration": i+1,
            "action": action,
            "action_input": action_input,
            "observation": observation
        })

        messages.append({"role": "assistant", "content": response_text})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    print("max iterationer nådda")


def main():
    log_file = setup_logger()
    print("react agent del 2 - skriv 'quit' för att avsluta\n")
    print(f"loggar sparas i: {log_file}\n")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    while True:
        user_input = input("du: ").strip()
        if user_input.lower() == "quit":
            break
        if not user_input:
            continue
        log_event(log_file, "user_input", {"message": user_input})
        react_loop(messages, user_input, log_file)


if __name__ == "__main__":
    main()