from datetime import datetime, timedelta

class TimeResumeCapsule:
    def __init__(self, username=None):
        self.username = username
        self.timestamp_store = {}

    def calculate_time_gap(self, last_timestamp, current_timestamp):
        return current_timestamp - last_timestamp

    def classify_session(self, time_gap):
        if time_gap < timedelta(minutes=5):
            return "CONTINUOUS"
        elif time_gap < timedelta(days=1):
            return "RESUMED"
        else:
            return "DECAYED"

    def save_timestamp(self, username, session_id):
        if username not in self.timestamp_store:
            self.timestamp_store[username] = {}
        self.timestamp_store[username][session_id] = datetime.now()

    def load_last_timestamp(self, username):
        return self.timestamp_store.get(username, {})

def prevent_false_continuity(session_timestamps):
    new_timestamps = {}
    for session_id, timestamp in session_timestamps.items():
        new_timestamps[session_id] = timestamp
    return new_timestamps
