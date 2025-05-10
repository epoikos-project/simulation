# TODO: Only mocked until now. Just ideas
TYPE1 = {
    "name": "Type1",
    "num_types": 3,
    "resource_types": [
        {
            "id": "1",
            "name": "Type1",
            "description": "This is a type 1 resource.",
            "energy_value": 10,
            "energy_cost": 5,
            "harvest_time": 2,
            "regen_time": 5,
        },
        {
            "id": "2",
            "name": "Type2",
            "description": "This is a type 2 resource.",
            "energy_value": 20,
            "energy_cost": 10,
            "harvest_time": 3,
            "regen_time": 7,
        },
        {
            "id": "3",
            "name": "Type3",
            "description": "This is a type 3 resource.",
            "energy_value": 30,
            "energy_cost": 15,
            "harvest_time": 4,
            "regen_time": 10,
        },
    ],
    "required_abilities": ["a", "b", "c", "ab", "ac", "bc", "abc"],
}
