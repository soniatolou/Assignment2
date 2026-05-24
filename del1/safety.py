# lista med kommandon som alltid blockeras direkt
BLOCKED_COMMANDS = [
    "rm -rf",
    "mkfs",
    "dd",
    "sudo",
    "chmod",
    "chown",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
]

# farliga mönster som kan förstöra saker
BLOCKED_PATTERNS = [
    "> /dev/",
    ":/dev/",
    "/etc/passwd",
    "/etc/shadow",
    "~/.ssh",
]

# farliga operatorer som kan kedja kommandon
BLOCKED_OPERATORS = [
    "&&",
    "||",
    ";",
    "|",
    "&",
]


def is_safe(command):
    # kollar om kommandot innehåller något farligt
    command_lower = command.lower()

    for blocked in BLOCKED_COMMANDS:
        if blocked in command_lower:
            return False, f"blockerat kommando: {blocked}"

    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return False, f"blockerat mönster: {pattern}"

    for operator in BLOCKED_OPERATORS:
        if operator in command:
            return False, f"blockerad operator: {operator}"

    return True, "ok"