import os
from pyexpat.errors import messages
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ansluter till openai med api-nyckeln från .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# system-prompten som talar om för modellen vilket format den ska följa
SYSTEM_PROMPT = """You are a ReAct agent that solves tasks step by step using bash commands.

Always follow this EXACT format:

Thought: <what you are thinking>
Action: bash
Action Input: <the exact bash command>

When you have the final answer:
Thought: I now know the answer
Final Answer: <your answer>

Never skip the Thought. Never combine steps."""


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


def react_loop(user_input):
    # bygger upp historiken med system-prompt och användarens fråga
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    max_iterations = 10

    for i in range(max_iterations):
        print(f"\n--- iteration {i+1} ---")

        # anropar modellen
        response = call_llm(messages)
        print(response)

        # parsar ut vilket verktyg modellen vill använda
        action, action_input = parse_action(response)

        # om det finns en action, kör den först
        if action and action_input:
            if action.lower() == "bash":
                observation = run_bash(action_input)
            else:
                observation = f"okänt verktyg: {action}"

            print(f"\nobservation: {observation}")

            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
            continue

            # kollar om modellen är klar, bara om ingen action hittades
            final_answer = parse_final_answer(response)
            if final_answer:
                print(f"\nsvar: {final_answer}")
                return

            print("kunde inte parsa action, avslutar")
            break

            print("max iterationer nådda")
def main():
    print("react agent del 1 - skriv 'quit' för att avsluta\n")
    while True:
        user_input = input("du: ").strip()
        if user_input.lower() == "quit":
            break
        if not user_input:
            continue
        react_loop(user_input)


if __name__ == "__main__":
    main()