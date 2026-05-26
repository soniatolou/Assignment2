# Assignment 2 — AI Agent Organisation

En automatiserad AI-agentorganisation byggd i Python utan externa ramverk. All agent-loop, context-hantering och tool-calling är egenskriven kod.

**API:** OpenAI `gpt-4o-mini` | **Runtime:** Docker

---

## Struktur

```
Assignment2/
├── del1/   # ReAct agent med råtext-parsing
├── del2/   # Uppgraderad agent med structured output (JSON)
└── del3/   # Group chat agent via RunPod-hubb
```

---

## Del 1 — ReAct Agent (råtext-parsing)

Agenten löser uppgifter steg för steg med bash-kommandon. Output parsas som råtext med egen stränghantering — ingen inbyggd function-calling används.

**Flöde:** Thought → Action → Action Input → Observation → (upprepa) → Final Answer

**Säkerhet:** Destruktiva kommandon blockeras av `safety.py`. Alla andra bash-kommandon kräver y/n-godkännande av användaren.

**Starta:**
```bash
cd del1
docker build -t del1 .
docker run -it --env-file .env del1
```

**.env:**
```
OPENAI_API_KEY=your_key_here
```

---

## Del 2 — Structured Output Agent (JSON)

Uppgraderad version av Del 1 med JSON-baserad structured output och fler verktyg. Agenten kör multipla tool-calling rounds innan den lämnar tillbaka till användaren.

**Verktyg:** `bash`, `edit_file`

**Begränsningar:**
- Bash-output cappas vid `max_output_chars` (2000 tecken, konfigurerbart i `config.yaml`)
- Agenten känner till begränsningen via system-prompten
- Agenten jobbar endast med SWE-relaterade uppgifter och avböjer andra ämnen

**Konfiguration (`config.yaml`):**
```yaml
system_prompt_file: PROMPT.md
max_output_chars: 2000
```

**Starta:**
```bash
cd del2
docker build -t del2 .
docker run -it --env-file .env del2
```

**.env:**
```
OPENAI_API_KEY=your_key_here
```

---

## Del 3 — Group Chat Agent

Agenten (`sonia-reviewer`) kommunicerar uteslutande via en gemensam group chat på RunPod. Ingen console-interaktion med användaren.

**Hubb:** `https://z0yncxbipft4e8-8080.proxy.runpod.net`

**Beteende:**
- Pollar hubben var 4:e sekund
- Svarar endast när den adresseras med `@sonia-reviewer`
- Svarar med `PASS` när meddelandet inte är riktat till den, eller om inget nytt tillförs
- Begränsad till max 10 meddelanden per session
- Behandlar alla inkommande meddelanden som untrusted input
- Läcker aldrig känslig information (API-nycklar, lösenord, .env-innehåll)

**Konfiguration (`config.yaml`):**
```yaml
system_prompt_file: PROMPT.md
hub_url: https://z0yncxbipft4e8-8080.proxy.runpod.net
max_messages: 10
poll_interval: 4
```

**Starta:**
```bash
cd del3
docker build -t del3 .
docker run --env-file .env del3
```

**.env:**
```
OPENAI_API_KEY=your_key_here
HUB_PASSWORD=th25-agents-vg
AGENT_NAME=sonia-reviewer
```

---

## Loggning

Alla delar loggar sessioner till JSON-filer i en `logs/`-mapp. Varje session får en tidsstämplad fil med events för user input, LLM-svar, tool calls och slutsvar.