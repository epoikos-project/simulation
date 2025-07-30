import json
from typing import Any, Dict, List, Union
import csv
import os


def compute_distance(a: tuple[int, int], b: tuple[int, int]):
    """Compute distance between two coordinates in 2D space"""
    # Using Manhattan distance formula
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def compute_distance_raw(
    x_coord_a: int, y_coord_a: int, x_coord_b: int, y_coord_b: int
):
    """Compute distance between two coordinates in 2D space"""
    # Using Manhattan distance formula
    return abs(x_coord_a - x_coord_b) + abs(y_coord_a - y_coord_b)


def compute_in_radius(
    location_a: tuple[int, int], location_b: tuple[int, int], radius: int
):
    """Check if agent is within range of resource"""
    distance = compute_distance(location_a, location_b)
    return distance <= radius


def extract_tool_call_info(data: Any) -> Dict[str, List[Dict[str, Any]]]:
    """
    Pulls out:
      - from each ToolCallRequestEvent: name & arguments (always as a dict)
      - from each ToolCallExecutionEvent: is_error flag

    Works on both dicts and objects by using _get(). Flattens any nested lists
    inside ToolCallRequestEvent. Always returns lists (even if empty or singleton).
    If `arguments` is a JSON string, it will attempt to decode it; otherwise it's
    returned as-is.
    """

    def _get(o: Any, key: str, default: Any = None) -> Any:
        if isinstance(o, dict):
            return o.get(key, default)
        return getattr(o, key, default)

    result = {"ToolCallRequestEvent": [], "ToolCallExecutionEvent": []}

    messages = _get(data, "messages", []) or []
    for msg in messages:
        msg_type = _get(msg, "type")
        content = _get(msg, "content", []) or []

        if msg_type == "ToolCallRequestEvent":
            # flatten any nested lists
            for call in content:
                calls = call if isinstance(call, list) else [call]
                for single in calls:
                    name = _get(single, "name")
                    args = _get(single, "arguments", {})

                    # if args is a JSON string, decode it; otherwise leave as-is
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            pass

                    result["ToolCallRequestEvent"].append(
                        {"name": name, "arguments": args}
                    )

        elif msg_type == "ToolCallExecutionEvent":
            for exec_res in content:
                result["ToolCallExecutionEvent"].append(
                    {"is_error": _get(exec_res, "is_error", False)}
                )

    return result


def summarize_tool_call(calls: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
    """
    Summarize tool calls into a single string.
    - Accepts a dict with "ToolCallRequestEvent", a single call-dict, or a list of call-dicts.
    - Parses JSON-string arguments if needed.
    - Drops any 'add_memory' entry when there are multiple calls.
    - Returns a single string: if multiple summaries, concatenated with ", ";
      if only one, returns it directly.
    """

    def _summarize_one(call: Dict[str, Any]) -> str:
        name = call.get("name", "")
        raw_args = call.get("arguments", {})

        # Decode JSON if needed
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                return f"{name}({raw_args})"
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            return f"{name}({raw_args!r})"

        parts = []
        for k, v in args.items():
            if isinstance(v, str):
                parts.append(f"{k}={json.dumps(v)}")
            else:
                parts.append(f"{k}={v!r})")
        joined = ", ".join(parts)
        return f"{name}({joined})"

    # Normalize into flat list of call-dicts
    if isinstance(calls, dict) and "ToolCallRequestEvent" in calls:
        call_list = calls["ToolCallRequestEvent"] or []
    elif isinstance(calls, dict) and "name" in calls:
        call_list = [calls]
    elif isinstance(calls, list):
        call_list = calls
    else:
        raise ValueError(
            "Input must be a list of call-dicts, a single call-dict, "
            "or a dict containing 'ToolCallRequestEvent'"
        )

    # If no calls present, return early

    # Build summary strings
    summaries = [_summarize_one(c) for c in call_list]

    # Filter out 'update_plan' if more than one
    if len(summaries) > 1:
        summaries = [s for s in summaries if not s.startswith("update_plan(")]

    if len(call_list) == 0 or len(summaries) == 0:
        return "No tool call made."

    # Join into one string
    return ", ".join(summaries)


def log_simulation_result(
    simulation_id: str,
    test_name: str,
    ticks: int,
    success: bool,
    file_path="tests/results/simulation_results.csv",
):
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=["test_name", "simulation_id", "ticks", "success"]
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "test_name": test_name,
                "simulation_id": simulation_id,
                "ticks": ticks,
                "success": success,
            }
        )


def get_neutral_first_names():
    """
    Name list adapted from SSA baby names data and Wolfe & Caliskan (2021, EMNLP).
    See also Wikipedia: Unisex names in English.
    """
    return [
        "Alex",
        "Taylor",
        "Morgan",
        "Casey",
        "Riley",
        "Jordan",
        "Avery",
        "Quinn",
        "Robin",
        "Cameron",
        "Jamie",
        "Dakota",
        "Skyler",
        "Reese",
        "Sydney",
        "Jesse",
        "Charlie",
        "Corey",
        "Drew",
        "Sam",
        "Addison",
        "Adel",
        "Al",
        "Alexis",
        "Ali",
        "Alli",
        "Alix",
        "Alison",
        "Allison",
        "Allyson",
        "Ally",
        "Allie",
        "Alley",
        "Allyn",
        "Alva",
        "Andy",
        "Angel",
        "Arden",
        "Ariel",
        "Ari",
        "Arlie",
        "Ash",
        "Asher",
        "Ashton",
        "Ashley",
        "Apple",
        "Aston",
        "Aspen",
        "Aubrey",
        "Audie",
        "Audrey",
        "Avie",
        "Avis",
        "Abby",
        "Abbey",
        "Ainsley",
        "Banks",
        "Bailey",
        "Beverly",
        "Bev",
        "Bentley",
        "Benny",
        "Bernie",
        "Berny",
        "Berni",
        "Berry",
        "Beryl",
        "Bexley",
        "Billy",
        "Billie",
        "Blaze",
        "Blake",
        "Blaine",
        "Blane",
        "Blair",
        "Blue",
        "Bliss",
        "Bobby",
        "Bobbi",
        "Brett",
        "Brennan",
        "Brandy",
        "Brownie",
        "Brooke",
        "Brook",
        "Brooklyn",
        "Brooklin",
        "Bryce",
        "Bryn",
        "Calvin",
        "Campbell",
        "Cameron",
        "Kameron",
        "Camryn",
        "Cammy",
        "Cam",
        "Kam",
        "Camille",
        "Carol",
        "Carroll",
        "Carrol",
        "Caryl",
        "Caryll",
        "Karyl",
        "Carey",
        "Cary",
        "Carson",
        "Carsen",
        "Carmen",
        "Carman",
        "Karmen",
        "Casey",
        "Kasey",
        "Cassidy",
        "Cass",
        "Cashmere",
        "Chandler",
        "Channing",
        "Charlie",
        "Charley",
        "Charly",
        "Charli",
        "Charlee",
        "Chase",
        "Chelsea",
        "Cheyenne",
        "Chris",
        "Cris",
        "Kris",
        "Chrissy",
        "Christy",
        "Christian",
        "Collins",
        "Cody",
        "Coby",
        "Connie",
        "Corrie",
        "Corry",
        "Cory",
        "Cordy",
        "Cosmo",
        "Courtney",
        "Cecil",
        "Cedric",
        "Cree",
        "Kree",
        "Cleo",
        "Claire",
        "Clare",
        "Dakota",
        "Dallas",
        "Dale",
        "Dayle",
        "Danny",
        "Dannie",
        "Danni",
        "Dani",
        "Denny",
        "Dana",
        "Dayna",
        "Darby",
        "Darcy",
        "D'arcy",
        "Darian",
        "Darien",
        "Darryl",
        "Dawson",
        "Delaney",
        "Delanie",
        "Dell",
        "Del",
        "Devin",
        "Devyn",
        "Devon",
        "Devan",
        "Derby",
        "Dee",
        "Dominique",
        "Drew",
        "Dru",
        "Drue",
        "Duncan",
        "Dylan",
        "Diamond",
        "Eden",
        "Elisha",
        "Elis",
        "Ellis",
        "Ellyse",
        "Ellice",
        "Ellison",
        "Elliot",
        "Ellie",
        "Ellery",
        "Ember",
        "Emerson",
        "Emery",
        "Emory",
        "Emmett",
        "Erin",
        "Ev",
        "Evan",
        "Evelyn",
        "Everly",
        "Esmé",
        "Finley",
        "Florence",
        "Florenz",
        "Flower",
        "Fran",
        "Frankie",
        "Freddy",
        "Freddie",
        "Freddi",
        "Gail",
        "Gale",
        "Gayle",
        "Gay",
        "Gaye",
        "Garnet",
        "Gaelan",
        "Gaelen",
        "Galen",
        "Gabby",
        "Gerry",
        "Gerrie",
        "Gerri",
        "Georgie",
        "Gene",
        "Gill",
        "Gussie",
        "Greer",
        "Glenn",
        "Gwyn",
        "Gwynn",
        "Gwynne",
        "Gwen",
        "Haven",
        "Hadley",
        "Halsey",
        "Harley",
        "Harlee",
        "Harlow",
        "Harrison",
        "Harper",
        "Harmony",
        "Hayes",
        "Hayden",
        "Haiden",
        "Hayley",
        "Hailey",
        "Haley",
        "Halley",
        "Hale",
        "Hilary",
        "Hillary",
        "Hero",
        "Hennie",
        "Hope",
        "Hollis",
        "Holliday",
        "Holiday",
        "Hunter",
        "Ivy",
        "Ivey",
        "Ivie",
        "Ivory",
        "Iggy",
        "Izzy",
        "Indigo",
        "Jacy",
        "Jacey",
        "Jack",
        "Jackie",
        "Jacki",
        "Jamie",
        "Jamey",
        "Jaime",
        "Jaimie",
        "Jayme",
        "Jay",
        "Jaye",
        "Jai",
        "Jae",
        "Jaylon",
        "Jayden",
        "Jaden",
        "Jadyn",
        "Jade",
        "Jazz",
        "Jean",
        "Jensen",
        "Jerry",
        "Jeri",
        "Jeryl",
        "Jeryn",
        "Jess",
        "Jes",
        "Jesse",
        "Jessie",
        "Jessy",
        "Jessey",
        "Jessi",
        "Jewel",
        "Jewell",
        "Jo",
        "Jocelyn",
        "Joey",
        "Jodie",
        "Jody",
        "Jordan",
        "Jordy",
        "Jordie",
        "Joy",
        "Joie",
        "Journey",
        "Jude",
        "June",
        "Junie",
        "Juniper",
        "Jupiter",
        "Justice",
        "Kai",
        "Kye",
        "Kay",
        "Kayle",
        "Kary",
        "Karey",
        "Keegan",
        "Kelly",
        "Kelley",
        "Kelsey",
        "Kendall",
        "Kennedy",
        "Kenzie",
        "Kerry",
        "Kim",
        "Kym",
        "Kimberly",
        "Kirby",
        "Kira",
        "Kit",
        "Kinsley",
        "Kristen",
        "Kyrie",
        "Kyle",
        "Lacy",
        "Lacey",
        "Lacie",
        "Laci",
        "Lake",
        "Lane",
        "Landy",
        "Larkin",
        "Lavern",
        "Laverne",
        "Laurel",
        "Laurie",
        "Lee",
        "Leigh",
        "Leighton",
        "Lenny",
        "Lennox",
        "Lennon",
        "Leslie",
        "Lesley",
        "Les",
        "Lex",
        "Liberty",
        "Lin",
        "Linn",
        "Lyn",
        "Lynn",
        "Lindsay",
        "Lindsey",
        "Lindy",
        "Linden",
        "Logan",
        "London",
        "Loren",
        "Lauren",
        "Lorne",
        "Lou",
        "Louie",
        "Lyndon",
        "Mandy",
        "Mandi",
        "Mackenzie",
        "Madison",
        "Maddison",
        "Maddox",
        "Madox",
        "Mallory",
        "Marian",
        "Marion",
        "Marin",
        "Marley",
        "Marlee",
        "Marlo",
        "Marlowe",
        "Marshal",
        "Marvel",
        "Marty",
        "Martie",
        "Marti",
        "Max",
        "Maxie",
        "Matty",
        "Mattie",
        "Maverick",
        "McKinley",
        "Meade",
        "Mel",
        "Meredith",
        "Merle",
        "Merlyn",
        "Merrill",
        "Merril",
        "Merritt",
        "Merry",
        "Milo",
        "Mickey",
        "Micky",
        "Mickie",
        "Micki",
        "Mikki",
        "Miki",
        "Misha",
        "Mischa",
        "Monroe",
        "Montana",
        "Morgan",
        "Morley",
        "Murphy",
        "Nevada",
        "Nat",
        "Nic",
        "Nicola",
        "Nicky",
        "Nickey",
        "Nickie",
        "Nicki",
        "Nikki",
        "Niki",
        "Noah",
        "Noa",
        "Nova",
        "Noel",
        "Norrie",
        "Ocean",
        "Oakley",
        "Odell",
        "Odie",
        "Ollie",
        "Olly",
        "Opal",
        "Paisley",
        "Paige",
        "Page",
        "Palmer",
        "Paris",
        "Parris",
        "Parker",
        "Patrice",
        "Pat",
        "Patty",
        "Patti",
        "Patsy",
        "Paxton",
        "Payton",
        "Peyton",
        "Pearl",
        "Perry",
        "Perrey",
        "Perrie",
        "Perri",
        "Parry",
        "Pepper",
        "Presley",
        "Piper",
        "Pinkie",
        "Phoenix",
        "Posy",
        "Posey",
        "Posie",
        "Quinn",
        "Quincy",
        "Raleigh",
        "Raven",
        "Ray",
        "Rae",
        "Rea",
        "Randy",
        "Randi",
        "Reagan",
        "Regan",
        "Reggie",
        "Rennie",
        "Renny",
        "Renée",
        "René",
        "Rémy",
        "Rebel",
        "Reese",
        "Reece",
        "Reed",
        "Ricky",
        "Rickey",
        "Rickie",
        "Ricki",
        "Riki",
        "Rikki",
        "Riley",
        "Ridley",
        "Ripley",
        "River",
        "Robin",
        "Robyn",
        "Robbie",
        "Rory",
        "Rorie",
        "Rori",
        "Ronnie",
        "Ronny",
        "Roni",
        "Roma",
        "Romilly",
        "Romy",
        "Rowan",
        "Rowen",
        "Royce",
        "Rudy",
        "Russi",
        "Rutherford",
        "Ryan",
        "Ryann",
        "Rhyan",
        "Ryder",
        "Rylan",
        "Rynn",
        "Sage",
        "Sam",
        "Sammy",
        "Sammie",
        "Sammi",
        "Sandy",
        "Sandie",
        "Sandi",
        "Sasha",
        "Sacha",
        "Sascha",
        "Sawyer",
        "Sal",
        "Sky",
        "Skye",
        "Skyler",
        "Skylar",
        "Schuyler",
        "Scotty",
        "Scottie",
        "Scout",
        "Selby",
        "Sharon",
        "Shane",
        "Shannon",
        "Shawn",
        "Shaun",
        "Shon",
        "Shay",
        "Shaye",
        "Shai",
        "Shae",
        "Shea",
        "Shelby",
        "Shelley",
        "Shelly",
        "Sherrill",
        "Shirl",
        "Shirley",
        "Sherley",
        "Shiloh",
        "Silver",
        "Sidney",
        "Sydney",
        "Sid",
        "Syd",
        "Cyd",
        "Spencer",
        "Stacy",
        "Stacey",
        "Stef",
        "Steph",
        "Stevie",
        "Storm",
        "Stormie",
        "Stormy",
        "Storme",
        "Sutton",
        "Summer",
        "Sunny",
        "Sloane",
        "Taran",
        "Tate",
        "Tatum",
        "Taylor",
        "Tayler",
        "Tegan",
        "Temple",
        "Terry",
        "Terri",
        "Tenley",
        "Teal",
        "Teale",
        "Tommie",
        "Tommy",
        "Tony",
        "Toni",
        "Tori",
        "Tory",
        "Torrey",
        "Torry",
        "Torrie",
        "Torrance",
        "Trace",
        "Tracy",
        "Tracey",
        "Tyler",
        "Valentine",
        "Vale",
        "Val",
        "Viv",
        "Vivian",
        "Vivien",
        "Wallis",
        "Waverly",
        "Willy",
        "Willie",
        "Willey",
        "Win",
        "Winnie",
        "Winter",
        "Wynn",
        "Wynne",
        "Whitney",
        "Woodrow",
        "Wren",
        "Xan",
        "Yancy",
    ]
