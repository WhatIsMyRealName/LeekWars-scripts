import requests
import json
import os
import time
from typing import Any, TypedDict

# Ne nécessite pas d'authentification
# (Sauf si des trophées secrets sont débloqués)

API_BASE = "https://leekwars.com/api"
DELAY_OK = 0.01
DELAY_ERROR = 0.10
MAX_RETRIES = 3

FIGHT_CONTEXT_GARDEN = 2
FIGHT_TYPE_BATTLE_ROYALE = 3
FIGHT_TYPE_WAR = 5
FIGHT_TYPE_COLOSSUS = 7
FIGHT_TYPE_CHEST_HUNT = 6
AUTHORIZED_FIGHT_TYPES = {FIGHT_TYPE_BATTLE_ROYALE, FIGHT_TYPE_WAR, FIGHT_TYPE_CHEST_HUNT, FIGHT_TYPE_COLOSSUS}
FIGHT_TYPE_NAMES: dict[int, str] = {
    FIGHT_TYPE_BATTLE_ROYALE: "Battle royale",
    FIGHT_TYPE_WAR: "Guerre",
    FIGHT_TYPE_CHEST_HUNT: "Chasse aux coffres",
    FIGHT_TYPE_COLOSSUS: "Colosse",
}
ENTITY_LEEK = 0
ENTITY_CHEST = 3
AUTHORIZED_ITEMS: set[int] = set(range(1000)) # Tout autorisé par défaut
CARACS = {"life": 2391, "strength": 359, "wisdom": 440, "agility": 240, "resistance": 300, "frequency": 130, "tp": 25, "mp": 4} # "science": 100, "magic": 100, # caractéristiques inutiles lors de la dernière soirée
ACTION_LEEK_TURN = 7
ACTION_USE_CHIP = 12
ACTION_SET_WEAPON = 13
ACTION_USE_WEAPON = 16
ACTIONS_DAMAGE = [101, 109, 110] # même si pour avoir 110 il faut passer par 301 ou 302 avant, on le met au cas-où
ACTIONS_EFFECTS = [301, 302] # action [301, *, *, *, target, effect, **]
DAMAGE_EFFECTS = [1, 13]

class Scores(TypedDict):
    ELOs: dict[str, float]
    COUNT: dict[str, int]
    WINS: dict[str, int]

class SavedResults(Scores):
    BY_TYPE: dict[str, Scores]

RESULTS_PATH: str = "" # Résultats précédents ; vide pour repartir de zéro
DATA_PATH: str = "" # Combats à analyser ; vide pour saisir une plage d'identifiants
results_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), RESULTS_PATH)
if RESULTS_PATH and os.path.exists(results_path):
    with open(results_path, "r", encoding="utf-8") as f:
        past_results: SavedResults = json.load(f)
    COUNT: dict[str, int] = past_results["COUNT"]
    WINS: dict[str, int] = past_results["WINS"]
    ELOs: dict[str, float] = past_results["ELOs"]
    SCORES_BY_TYPE: dict[int, Scores] = {fight_type: past_results["BY_TYPE"][str(fight_type)] for fight_type in FIGHT_TYPE_NAMES}
else:
    COUNT = {}
    WINS = {}
    ELOs = {}
    SCORES_BY_TYPE = {fight_type: Scores(ELOs={}, COUNT={}, WINS={}) for fight_type in FIGHT_TYPE_NAMES}
TOTAL_TROPHIES = 0
TOTAL_CHESTS = 0

def get_fight_data(fight_id: int) -> dict[str, Any] | None:
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

def get_item_mappings() -> tuple[dict[int, int], dict[int, int]]:
    chips_response = requests.get(f"{API_BASE}/chip/get-all", timeout=10)
    chips_response.raise_for_status()
    weapons_response = requests.get(f"{API_BASE}/weapon/get-all", timeout=10)
    weapons_response.raise_for_status()
    chip_items = {chip["template"]: chip["id"] for chip in chips_response.json()["chips"].values()}
    weapon_items = {weapon["template"]: weapon["item"] for weapon in weapons_response.json()["weapons"].values()}
    return chip_items, weapon_items

def check_items(actions: list[list[Any]], player_ids: set[int], chip_items: dict[int, int], weapon_items: dict[int, int]) -> bool:
    forbidden_weapon: dict[int, bool] = {player_id: False for player_id in player_ids}
    active_entity: int | None = None
    # NOTE : on ne vérifie que l'utilisation des armes et puces, mais pas leur équippement, donc on pourrait tricher avec les armes oubliées.
    for action in actions:
        action_type = action[0]
        if action_type == ACTION_LEEK_TURN:
            active_entity = action[1]
        elif active_entity is not None and active_entity in forbidden_weapon:
            if action_type == ACTION_SET_WEAPON:
                forbidden_weapon[active_entity] = weapon_items[action[1]] not in AUTHORIZED_ITEMS
            elif action_type == ACTION_USE_WEAPON:
                if forbidden_weapon[active_entity]:
                    return False
            elif action_type == ACTION_USE_CHIP:
                if chip_items[action[1]] not in AUTHORIZED_ITEMS:
                    return False
    return True

def is_valid_BR(data: dict[str, Any], chip_items: dict[int, int], weapon_items: dict[int, int]) -> bool:
    if not (data["type"] in AUTHORIZED_FIGHT_TYPES and data["context"] == FIGHT_CONTEXT_GARDEN):
        return False
    # NOTE : on ne peut pas vérifier directement la RAM et les coeurs des poireaux.
    # On se contente juste (dans check_items) de vérifier qu'il n'y a pas de puce non autorisée d'utilisée, mais il est possible de tricher sur la mémoire.
    # Pour les coeurs, on pourrait comparer les nombre total d'ops au nombre de tours joués mais bon franchement c'est inutile.
    player_ids: set[int] = set()
    for leek in data["data"]["leeks"]:
        if leek["type"] != ENTITY_LEEK:
            continue
        player_ids.add(leek["id"])
        for carac in CARACS.keys():
            if leek[carac] > CARACS[carac]:
                return False
    return check_items(data["data"]["actions"], player_ids, chip_items, weapon_items)

def get_BRs_data(start_id: int, end_id: int, save_path: str = "BRs_raw_data.json", log_path: str = "errors.log") -> dict[int, dict[str, Any]]:
    chip_items, weapon_items = get_item_mappings()
    all_battle_royale: dict[int, dict[str, Any]] = {}
    error_log: list[tuple[int, str]] = []
    for fight_id in range(start_id, end_id + 1):
        data = get_fight_data(fight_id)
        if data is None:
            error_log.append((fight_id, "No data"))
            continue
        if is_valid_BR(data, chip_items, weapon_items):
            data["data"]["map"] = None
            data["data"]["ops"] = None
            data["data"]["actions"] = None # Actions vérifiées, mais non conservées car très volumineuses
            data["report"] = None
            all_battle_royale[fight_id] = data
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

def get_fight_results(fight_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    if fight_data["type"] in (FIGHT_TYPE_WAR, FIGHT_TYPE_COLOSSUS):
        team1: list[str] = [leek["name"] for leek in fight_data["leeks1"]]
        team2: list[str] = [leek["name"] for leek in fight_data["leeks2"]]
        # Toute l'équipe gagne, même ses joueurs morts pendant le combat.
        if fight_data["winner"] == 1:
            return team1, team2
        if fight_data["winner"] == 2:
            return team2, team1
        return [], team1 + team2

    # BR et chasse aux coffres : les survivants gagnent, même sans vainqueur officiel.
    names: dict[int, str] = {leek["id"]: leek["name"] for leek in fight_data["leeks1"] + fight_data["leeks2"]}
    winners: list[str] = []
    losers: list[str] = []
    for id_str, dead in fight_data["data"]["dead"].items():
        name = names.get(int(id_str), "Non déterminé") # coffre
        if dead:
            losers.append(name)
        else:
            winners.append(name)
    return winners, losers

def analyse_BR(fight_data: dict[str, Any]) -> None:
    global TOTAL_TROPHIES, TOTAL_CHESTS
    for trophy in fight_data["trophies"]:
        TOTAL_TROPHIES += 1
        # nom, farmer_name = trophy["name"], trophy["farmer"]["name"]
        # print(nom, farmer_name)
    for e in fight_data["data"]["leeks"]:
        if e["type"] == ENTITY_CHEST:
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
    winners, losers = get_fight_results(fight_data)
    update_scores(winners, losers, Scores(ELOs=ELOs, COUNT=COUNT, WINS=WINS))
    update_scores(winners, losers, SCORES_BY_TYPE[fight_data["type"]])

def update_scores(winners: list[str], losers: list[str], scores: Scores) -> None:
    ELOs, COUNT, WINS = scores["ELOs"], scores["COUNT"], scores["WINS"]
    elos: dict[str, dict[str, float]] = {"w":{}, "l":{}} # pour ne pas modifier le dict principal en cours de route
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
        return # Ici, pas de gagnant => losers n'est pas vide mais elos["l"] ne contient personne parce qu'on est jamais entré dans le boucle, vu qu'il n'y a pas de gagnant
    for l in losers:
        ELOs[l] += elos["l"][l]

def print_scores(title: str, scores: Scores) -> None:
    ELOs, COUNT, WINS = scores["ELOs"], scores["COUNT"], scores["WINS"]
    print(title)
    if not ELOs:
        print("Aucun combat comptabilisé.")
        return

    # L'ordre des BR est important pour le calcul des ELOs. Mais avec suffisamment de BR, les scores de chacun devraient converger dans tous les cas.

    max_length = max(len(name) for name in ELOs.keys())
    print(f"""{"Poireau".ljust(max_length)} | Talent  | Nb de combats | Nb de victoires""")
    for name in sorted(ELOs.keys(), key=lambda x: ELOs[x], reverse=True):
        elo = round(ELOs[name], 2)
        nb_combats = COUNT.get(name, 0) # Si on n'a pas participé à la dernière soirée, on peut ne pas être dedans
        nb_win = WINS.get(name, 0)
        print(f"{name.ljust(max_length)} | {str(elo).ljust(7)} | {str(nb_combats).ljust(13)} | {nb_win}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    BRs: dict[str, dict[str, Any]] | dict[int, dict[str, Any]]
    if DATA_PATH:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            BRs = json.load(f)
    else:
        start = int(input("ID de début : "))
        end = int(input("ID de fin : "))
        BRs = get_BRs_data(start, end)

    for br_data in BRs.values(): # Préserve l'ordre d'insertion normalement
        analyse_BR(br_data)

    print_scores("Général", Scores(ELOs=ELOs, COUNT=COUNT, WINS=WINS))
    for fight_type, title in FIGHT_TYPE_NAMES.items():
        print()
        print_scores(title, SCORES_BY_TYPE[fight_type])

    print()
    print(f'Nombre de trophées débloqués : {TOTAL_TROPHIES}')
    print(f'Nombre de coffres apparus : {TOTAL_CHESTS}')

    with open("past_BR_results.json", "w", encoding="utf-8") as f:
        json.dump({"ELOs": ELOs, "COUNT": COUNT, "WINS": WINS,
                   "BY_TYPE": {str(fight_type): scores for fight_type, scores in SCORES_BY_TYPE.items()}},
                  f, indent=4, ensure_ascii=False)
