import json
import re
from utils.logging_setup import get_logger

logger = get_logger()

# Map of regex flag strings to their actual values
REGEX_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
    "MULTILINE": re.MULTILINE,
    "ASCII": re.ASCII,
    "VERBOSE": re.VERBOSE,
    "UNICODE": re.UNICODE
}

# Global dictionary to store compiled responses with their patterns for each server
server_patterns = {}

def load_patterns():
    """Load patterns from the patterns.json file"""
    try:
        with open('patterns.json', 'r', encoding='utf-8') as f:
            pattern_data = json.load(f)
        
        # Compile regex patterns for each server
        for server_id, responses_list in pattern_data.items():
            server_patterns[server_id] = []
            for response_info in responses_list:
                response_id = response_info.get("response_id", 0)
                response_text = response_info.get("response", "")
                name = response_info.get("name", "")
                note = response_info.get("note", "")
                
                # Create a response object with compiled patterns
                response_obj = {
                    "response_id": response_id,
                    "response": response_text,
                    "name": name,
                    "note": note,
                    "patterns": []
                }
                
                # Compile each pattern for this response
                for pattern_info in response_info.get("patterns", []):
                    pattern_id = pattern_info.get("id", 0)
                    pattern_name = pattern_info.get("name", f"pattern_{pattern_id}")
                    pattern_str = pattern_info.get("pattern", "")
                    flags_str = pattern_info.get("flags", "")
                    url = pattern_info.get("url", "")
                    
                    # Parse and combine regex flags
                    flag_value = 0
                    if flags_str:
                        for flag in flags_str.split('|'):
                            if flag in REGEX_FLAGS:
                                flag_value |= REGEX_FLAGS[flag]
                    
                    # Compile the pattern
                    try:
                        compiled_pattern = re.compile(pattern_str, flag_value)
                        
                        # Add the compiled pattern to the response's patterns list
                        response_obj["patterns"].append({
                            "id": pattern_id,
                            "name": pattern_name,
                            "pattern": compiled_pattern,
                            "url": url
                        })
                    except re.error as e:
                        logger.error(f"Error compiling pattern {pattern_name} for response {response_id}: {e}")
                        
                # Only add responses that have at least one valid pattern
                if response_obj["patterns"]:
                    server_patterns[server_id].append(response_obj)
        
        logger.info(f"Successfully loaded patterns for {len(pattern_data)} servers")
        return True
    except Exception as e:
        logger.error(f"Error loading patterns: {e}")
        # If there's an error, initialize with empty patterns
        server_patterns.clear()
        return False

def save_patterns():
    """Save patterns back to the patterns.json file"""
    try:
        # Convert compiled patterns back to serializable format
        serializable_patterns = {}
        for server_id, responses_list in server_patterns.items():
            serializable_patterns[server_id] = []
            for response_info in responses_list:
                # Create a serializable response object
                serializable_response = {
                    "response_id": response_info["response_id"],
                    "response": response_info["response"],
                    "name": response_info.get("name", ""),
                    "note": response_info.get("note", ""),
                    "patterns": []
                }
                
                # Convert each pattern to serializable format
                for pattern_info in response_info["patterns"]:
                    # Get the pattern string and flags from the compiled regex
                    pattern_obj = pattern_info["pattern"]
                    pattern_str = pattern_obj.pattern
                    
                    # Determine flags
                    flags = []
                    if pattern_obj.flags & re.IGNORECASE:
                        flags.append("IGNORECASE")
                    if pattern_obj.flags & re.DOTALL:
                        flags.append("DOTALL")
                    if pattern_obj.flags & re.MULTILINE:
                        flags.append("MULTILINE")
                    if pattern_obj.flags & re.ASCII:
                        flags.append("ASCII")
                    if pattern_obj.flags & re.VERBOSE:
                        flags.append("VERBOSE")
                    if pattern_obj.flags & re.UNICODE:
                        flags.append("UNICODE")
                    
                    serializable_response["patterns"].append({
                        "id": pattern_info["id"],
                        "name": pattern_info["name"],
                        "pattern": pattern_str,
                        "flags": "|".join(flags),
                        "url": pattern_info.get("url", "")
                    })
                
                serializable_patterns[server_id].append(serializable_response)
        
        with open('patterns.json', 'w', encoding='utf-8') as f:
            json.dump(serializable_patterns, f, indent=2)
        
        logger.info(f"Successfully saved patterns for {len(serializable_patterns)} servers")
        return True
    except Exception as e:
        logger.error(f"Error saving patterns: {e}")
        return False

def find_response(server_id, response_id_or_name):
    """Find a response by ID or name in a server's patterns"""
    if server_id not in server_patterns:
        return None
    
    # Try to interpret as an integer (ID)
    try:
        response_id = int(response_id_or_name)
        # Search by ID
        for r in server_patterns[server_id]:
            if r["response_id"] == response_id:
                return r
    except ValueError:
        pass  # Not an integer, continue to name search
    
    # Search by name (case insensitive)
    for r in server_patterns[server_id]:
        if r.get("name", "").lower() == str(response_id_or_name).lower():
            return r
    
    return None

def get_server_patterns(server_id):
    """Get responses with patterns for a specific server with fallback to default patterns"""
    server_id_str = str(server_id)
    
    # If server has specific patterns, use those
    if server_id_str in server_patterns:
        return server_patterns[server_id_str]
    
    # Otherwise use default patterns
    if "default" in server_patterns:
        return server_patterns["default"]
    
    # If no patterns are found, return an empty list
    return []

def get_next_response_id(server_id):
    """Get the next available response ID for a server"""
    patterns = get_server_patterns(server_id)
    if not patterns:
        return 1
    
    # Find the highest response_id and add 1
    return max(response.get("response_id", 0) for response in patterns) + 1

def get_next_pattern_id(response):
    """Get the next available pattern ID within a response"""
    if not response.get("patterns"):
        return 1
    
    # Find the highest pattern ID and add 1
    return max(pattern.get("id", 0) for pattern in response["patterns"]) + 1

def match_patterns(server_id, text):
    """Match text against patterns for a server and return the matching response"""
    # Get responses with patterns for this server
    responses = get_server_patterns(server_id)
    
    # For each response, check all its patterns
    for response in responses:
        for pattern in response["patterns"]:
            if pattern["pattern"].search(text):
                return response
    
    # No match found
    return None
