import requests
import json
import time

# Ne nécessite pas d'authentification
# (Sauf si des trophées secrets sont débloqués)

API_BASE = "https://leekwars.com/api"
DELAY_OK = 0.01
DELAY_ERROR = 0.10
MAX_RETRIES = 3

FIGHT_CONTEXT_GARDEN = 2
FIGHT_TYPE_BATTLE_ROYALE = 3
AUTHORIZED_ITEMS = [i for i in range(1000)] # Tout autorisé par défaut
CARACS = {"life": 2391, "strength": 359, "wisdom": 440, "agility": 240, "resistance": 300, "frequency": 130, "tp": 25, "mp": 4} # "science": 100, "magic": 100, # caractéristiques inutiles lors de la dernière soirée
ACTION_LEEK_TURN = 7
ACTIONS_DAMAGE = [101, 109, 110] # même si pour avoir 110 il faut passer par 301 ou 302 avant, on le met au cas-où
ACTIONS_EFFECTS = [301, 302] # action [301, *, *, *, target, effect, **]
DAMAGE_EFFECTS = [1, 13]

COUNT = {} # OU : charger depuis un fichier
WINS = {} # Idem
ELOs = {} # Idem
TOTAL_TROPHIES = 0
TOTAL_CHESTS = 0

def get_fight_data(fight_id: int):
    url = f"{API_BASE}/fight/get/{fight_id}"
    for t in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=10)
            text = resp.text
            if resp.status_code == 200:
                return json.loads(text)
            else:
                print(f"[{fight_id}] HTTP {resp.status_code} ({t}/{MAX_RETRIES})")
        except Exception as e:
            print(f"[FIGHT {fight_id}] Erreur de connexion : {e}")
            time.sleep(DELAY_ERROR)
    return None

def check_items(id: int):
    url = f"{API_BASE}/leek/get/{id}"
    for t in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=10)
            text = resp.text
            if resp.status_code == 200:
                data = json.loads(text)
                for item in data["chips"] + data["weapons"]:
                    if item["template"] not in AUTHORIZED_ITEMS:
                        return False
                return True
            else:
                print(f"[{id}] HTTP {resp.status_code} ({t}/{MAX_RETRIES})")
                time.sleep(DELAY_ERROR)
        except Exception as e:
            print(f"[LEEK {id}] Erreur de connexion : {e}")
            time.sleep(DELAY_ERROR)
    return None

def is_valid_BR(data: dict):
    if not (data["type"] == FIGHT_TYPE_BATTLE_ROYALE and data["context"] == FIGHT_CONTEXT_GARDEN):
        return False
    assert data["leeks2"] == [] # Tous les poireaux des BR sont dans leeks1
    for leek in data["leeks1"]:
        valid = check_items(leek["id"])
        if valid:
            continue
        else:
            return valid
    # NOTE : on ne peut pas vérifier directement la RAM et les coeurs des poireaux.
    # On se contente juste de vérifier qu'il n'y a pas de puces en trop, mais il est possible de tricher sur la mémoire.
    # Pour les coeurs, on pourrait comparer les nombre total d'ops au nombre de tours joués mais bon franchement c'est inutile.
    for leek in data["data"]["leeks"]:
        if "bulb" in leek["name"] or "chest" in leek["name"]:
            continue
        for carac in CARACS.keys():
            if leek[carac] > CARACS[carac]:
                print(leek, carac)
                return False
    return True

def get_BRs_data(start_id: int, end_id: int, save_path: str = "BRs_raw_data.json", log_path: str = "errors.log"):
    all_battle_royale = {}
    error_log = []
    for fight_id in range(start_id, end_id + 1):
        data = get_fight_data(fight_id)
        if data is None:
            error_log.append((fight_id, "No data"))
            continue
        data["data"]["map"] = None
        data["data"]["ops"] = None
        data["data"]["actions"] = None # Pas d'analyse détaillée des actions pour l'instant et très volumineux
        data["report"] = None
        valid = is_valid_BR(data)
        if valid:
            all_battle_royale[fight_id] = data
        elif valid is None:
            error_log.append((fight_id, "Item check failed"))
        time.sleep(DELAY_OK) # Eventuellement baisser voire supprimer ce délai si l'exécution du script est déjà suffisamment lente
        if fight_id % 500 == 0:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(all_battle_royale, f, indent=2, ensure_ascii=False)
            print(f"[RECUPERATION DES DONNES] Sauvegarde intermédiaire ({fight_id}/{end_id})")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(all_battle_royale, f, indent=2, ensure_ascii=False)
    print(f"[RECUPERATION DES DONNES] TERMINE - {len(all_battle_royale)} BR enregistrées.")
    if error_log:
        with open(log_path, "w") as f:
            for entry in error_log:
                f.write(f"{entry[0]} : {entry[1]}\n")
        print(f"[LOG] {len(error_log)} erreurs trouvées et enregistrées dans {log_path}.")
    return all_battle_royale

def p(diff: float):
    # Calcul de la probabilité de victoire
    return 1 / (1 + 10 ** (-diff / 400))

def analyse_BR(fight_data: dict):
    def getName_from_fight_id(leek_id_fight):
        for leek in fight_data["data"]["leeks"]:
            if leek["id"] == leek_id_fight:
                return leek["name"]
        return "Non déterminé" # Les coffres en général
    def getName_from_real_id(leek_id):
        for leek in fight_data["leeks1"]:
            if leek["id"] == leek_id:
                return leek["name"]
        return "Non déterminé" # Idem
    global TOTAL_TROPHIES, TOTAL_CHESTS, ELOs
    for trophy in fight_data["trophies"]:
        TOTAL_TROPHIES += 1
        # nom, farmer_name = trophy["name"], trophy["farmer"]["name"]
        # print(nom, farmer_name)
    for e in fight_data["data"]["leeks"]:
        if "chest" in e["name"]:
            TOTAL_CHESTS += 1
            # Vérifier s'il a été ouvert ?
        """
        # Exemple de code pour analyser le déroulement du combat
        # Récupérer le nom du poireau qui a été le premier à attaquer Jeez
        if e["name"] == "Jeez" and e["farmer"] == 43276: # Le bon Jeez
            attacker = None
            for action in fight_data["data"]["actions"]:
                if action[0] == ACTION_LEEK_TURN:
                    nom = getName_from_fight_id(action[1])
                    if "bulb" not in nom:
                        attacker = nom
                if (action[0] in ACTIONS_DAMAGE and action[1] == e["id"]) or (action[0] in ACTIONS_EFFECTS and action[4] == e["id"] and action[5] in DAMAGE_EFFECTS):
                    if attacker not in JEEZ:
                        JEEZ[attacker] = 0
                    JEEZ[attacker] += 1
                    break      
        """          
    winners, losers = [], []
    for id_str in fight_data["data"]["dead"]:
        if fight_data["data"]["dead"][id_str]:
            losers.append(getName_from_real_id(int(id_str)))
        else:
            winners.append(getName_from_real_id(int(id_str)))
    elos = {"w":{}, "l":{}} # pour ne pas modifier le dict principal en cours de route
    for w in winners:
        if w not in ELOs:
            ELOs[w] = 1500
        if w not in COUNT or w not in WINS: # Si on est dans l'un on devrait être dans l'autre
            COUNT[w] = 0
            WINS[w] = 0
        COUNT[w] += 1
        WINS[w] += 1
        elos["w"][w] = 0
        for l in losers:
            if l not in ELOs:
                ELOs[l] = 1500
            if l not in COUNT or l not in WINS:
                COUNT[l] = 0
                WINS[l] = 0
            if l not in elos["l"]:
                COUNT[l] += 1
            elos["l"][l] = 0
            elo_diff = 15 * (1 - p(ELOs[w] - ELOs[l])) # d'où ELOs et elos
            elos["w"][w] += elo_diff
            elos["l"][l] -= elo_diff
    # Pas de confrontation entre gagnants ni entre perdants, même si deux gagnants n'ont pas le même ELO (c'est pas une raison pour faire des égalités -_-)
    # Fonctionne même si tout le monde gagne parce que elos["w"] contient tout le monde avec une variation de 0
    for w in winners:
        ELOs[w] += elos["w"][w]
    if len(winners) == 0: 
        return
    # Par contre ici, pas de gagnant => losers n'est pas vide mais elos["l"] ne contient personne parce qu'on est jamais entré dans le boucle, vu qu'il n'y a pas de gagnant
    for l in losers:
        ELOs[l] += elos["l"][l]

if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # start = int(input("ID de début : "))
    # end = int(input("ID de fin : "))
    # BRs = get_BRs_data(start, end)
    with open("BRs_raw_data.json", "r", encoding="utf-8") as f:
        BRs = json.load(f)
    
    for br_data in BRs.values(): # Préserve l'ordre d'insertion normalement
        analyse_BR(br_data)
    
    elos_lisible = {}
    for leek_id, elo in ELOs.items():
        elos_lisible[leek_id] = round(elo, 2)
    # print(elos_lisible) # L'ordre des BR est important pour le calcul des ELOs. Mais avec suffisamment de BR, les scores de chacun devraient converger dans tous les cas.

    max_length = max(len(name) for name in ELOs.keys())
    print(f"""{"Poireau".ljust(max_length)} | Talent  | Nb de combats | Nb de victoires""")
    for name in sorted(ELOs.keys(), key=lambda x: ELOs[x], reverse=True):
        elo = round(ELOs[name], 2) # Ou juste récupérer elos_lisibles
        nb_combats = COUNT.get(name, 0) # Si on n'a pas participé à la dernière soirée, on peut ne pas être dedans
        nb_win = WINS.get(name, 0)
        print(f"{name.ljust(max_length)} | {str(elo).ljust(7)} | {str(nb_combats).ljust(13)} | {nb_win}")

    print()
    print(f'Nombre de trophées débloqués : {TOTAL_TROPHIES}')
    print(f'Nombre de coffres apparus : {TOTAL_CHESTS}')

    with open("past_BR_results.json", "w", encoding="utf-8") as f:
        json.dump({"ELOs": ELOs, "COUNT": COUNT, "WINS": WINS}, f, indent=4, ensure_ascii=False)
