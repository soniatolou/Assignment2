import os
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
