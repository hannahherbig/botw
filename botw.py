import random
import socket
import re
import toml
import argparse
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", default="config.toml")
args = parser.parse_args()

with open(args.config, "r") as f:
    config = toml.load(f)

rows = [
    "TL-BR",
    "BL-TR",
    "COL1",
    "COL2",
    "COL3",
    "COL4",
    "COL5",
    "ROW1",
    "ROW2",
    "ROW3",
    "ROW4",
    "ROW5",
]


def parse(msg):
    if msg[0] == ":":
        prefix, msg = msg[1:].split(maxsplit=1)
    else:
        prefix = None
    if " :" in msg:
        before, after = msg.split(" :", maxsplit=1)
        params = before.split() + [after]
    else:
        params = msg.split()
    command = params.pop(0)
    return prefix, command, params


def strip_colors(msg):
    for ch in "\x02\x1d\x1f\x16\x0f":
        msg = msg.replace(ch, "")
    return re.sub(r"\x03(\d+(\,\d+)?)?", "", msg)


sock = socket.socket()
sock.connect((config["server"], config["port"]))
buf = b""


def send(line):
    print(f">> {line}")
    sock.sendall(line.encode() + b"\r\n")


current_nick = config["nick"].lower()

send("USER {user} 0 * :{real}".format_map(config))
send("PASS :{pass}".format_map(config))
send(f"NICK {current_nick}")

bingo_state = {}
bingo_version = {}

while True:
    try:
        buf += sock.recv(8192)
    except KeyboardInterrupt:
        break
    else:
        if not buf:
            break
    lines = buf.split(b"\r\n")
    buf = lines.pop()
    lines = [strip_colors(line.decode("utf-8", "ignore")) for line in lines]
    for line in lines:
        print(f"<< {line}")
    for line in lines:
        prefix, command, params = parse(line)
        if prefix:
            nick = prefix.split("!", maxsplit=1)[0].lower()
        target = None
        mode = None
        text = None
        word = []
        if params:
            target = params[0].lower()
            if target in bingo_state:
                mode = bingo_state[target]
                version = bingo_version[target]
            text = params[-1].lower()
            word = text.split()
        if command == "PING":
            send(f"PONG :{params[0]}")
        elif command == "001":  # welcome
            send("JOIN :{main}".format_map(config))
        elif command == "JOIN" and mode and nick == current_nick:
            modes = "|".join(config["modes"])
            versions = "|".join(sorted(config["versions"].keys()))
            send(f"PRIVMSG {target} :I'll automatically generate a {mode} {version} bingo card after the countdown.")
            send(f"PRIVMSG {target} :If you don't want a card, type !nobingo.")
            send(f"PRIVMSG {target} :Type !mode <{modes}> to set the mode or to undo !nobingo.")
            send(f"PRIVMSG {target} :Type !version <{versions}> to set the version.")
            send(f"PRIVMSG {target} :.filename")
        elif command == "NICK" and nick == current_nick:
            current_nick = target
        elif command == "KICK" and target in bingo_state and params[1] == current_nick:
            del bingo_state[target]
            del bingo_version[target]
        elif command == "NOTICE":
            if nick == "nickserv":
                if params[1].startswith("This nickname is registered"):
                    send("PRIVMSG NickServ :IDENTIFY {pass}".format_map(config))
        elif command == "PRIVMSG" and target[0] == "#":
            if nick == config["racebot"]:
                if target == config["main"]:
                    arg = text.rsplit("|", maxsplit=1)
                    if len(arg) == 2:
                        msg, chan = arg
                        msg = msg.strip()
                        chan = chan.strip()
                        if msg in config["checks"]:
                            vers = httpx.get("https://ootbingo.github.io/bingo/api/v1/available_versions.json").json()
                            config.update(vers)
                            bingo_state[chan] = config["checks"][msg]
                            bingo_version[chan] = config["versions"][config["default_version"]]
                            send(f"JOIN :{chan}")
                elif mode:
                    if text == "the race will begin in 10 seconds!":
                        send(f"PRIVMSG {target} :A {mode} {version} bingo card will be generated after the countdown.")
                    elif text == "go!":
                        seed = random.randrange(1_000_000)
                        url = f"https://ootbingo.github.io/bingo/{version}/bingo.html?seed={seed}&mode={mode}"
                        send(f"PRIVMSG {target} :.setgoal {url}")
            if target != config["main"] and target[0] == "#":
                if len(word) >= 1:
                    if word[0] == "!pick":
                        send(f"PRIVMSG {target} :{nick}: Your row is {random.choice(rows)}")
                    elif word[0] == "!mode":
                        if len(word) >= 2:
                            if word[1] in config["modes"]:
                                bingo_state[target] = mode = word[1]
                                send(f"PRIVMSG {target} :Mode set to {mode}")
                            else:
                                modes = ", ".join(config["modes"])
                                send(f"PRIVMSG {target} :Invalid mode specified. Must be one of: {modes}.")
                        else:
                            send(f"PRIVMSG {target} :Mode: {mode}")
                    elif word[0] == "!version":
                        if len(word) >= 2:
                            if word[1] in config["versions"]:
                                bingo_version[target] = version = config["versions"][word[1]]
                                send(f"PRIVMSG {target} :Version set to {version}")
                            else:
                                versions = ", ".join(sorted(config["versions"]))
                                send(f"PRIVMSG {target} :Invalid version specified. Must be one of: {versions}.")
                        else:
                            send(f"PRIVMSG {target} :Version: {mode}")
                    elif word[0] == "!status":
                        send(f"PRIVMSG {target} :Mode: {mode}. Version: {version}")
                    elif word[0] == "!nobingo":
                        if mode:
                            del bingo_state[target]
                            send(f"PRIVMSG {target} :No card will be set. Type !mode {mode} to revert.")
                        else:
                            modes = ", ".join(config["modes"])
                            send(f"PRIVMSG {target} :Already disabled. Type !mode <{modes}> to enable.")
    print(bingo_state, bingo_version)
