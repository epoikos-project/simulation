def extract_tool_call_info(data):
    """
    Pulls out:
      - from each ToolCallRequestEvent: name & arguments
      - from each ToolCallExecutionEvent: is_error flag

    Works on both dicts and objects (e.g. TaskResult), by falling
    back to getattr when .get isn’t available.
    """

    def _get(o, key, default=None):
        # dict first, then attribute, then default
        if isinstance(o, dict):
            return o.get(key, default)
        return getattr(o, key, default)

    result = {"ToolCallRequestEvent": [], "ToolCallExecutionEvent": []}

    messages = _get(data, "messages", []) or []
    for msg in messages:
        msg_type = _get(msg, "type")
        content = _get(msg, "content", []) or []

        if msg_type == "ToolCallRequestEvent":
            for call in content:
                result["ToolCallRequestEvent"].append(
                    {"name": _get(call, "name"), "arguments": _get(call, "arguments")}
                )

        elif msg_type == "ToolCallExecutionEvent":
            for call in content:
                result["ToolCallExecutionEvent"].append(
                    {"is_error": _get(call, "is_error")}
                )

    # If exactly one of each, unwrap into a single dict
    if len(result["ToolCallRequestEvent"]) == 1:
        result["ToolCallRequestEvent"] = result["ToolCallRequestEvent"][0]
    if len(result["ToolCallExecutionEvent"]) == 1:
        result["ToolCallExecutionEvent"] = result["ToolCallExecutionEvent"][0]

    return result
