import json
from typing import Any, Dict, List, Union


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
    if len(call_list) == 0:
        return "No tool call made."

    # Build summary strings
    summaries = [_summarize_one(c) for c in call_list]

    # Filter out 'update_plan' if more than one
    if len(summaries) > 1:
        summaries = [s for s in summaries if not s.startswith("update_plan(")]

    # Join into one string
    return ", ".join(summaries)
