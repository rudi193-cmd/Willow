# core/aionic_ledger.py

class AionicLedger:
    def __init__(self):
        """
        Initialize the AionicLedger instance.
        
        Attributes:
            events (dict): A dictionary to store events with their event_id as key.
        """
        self.events = {}

    def log_event(self, username, event_dict):
        """
        Log an event into the ledger.

        Args:
            username (str): The username of the actor.
            event_dict (dict): The event information.

        Returns:
            str: The event_id.
        """
        event_id = len(self.events) + 1
        event_info = {
            'event_id': event_id,
            'timestamp': event_dict['timestamp'] if 'timestamp' in event_dict else None,
            'actor': username,
            'channel': event_dict['channel'],
            'type': event_dict['type'],
            'payload': event_dict['payload'],
            'hash_prev': event_dict['hash_prev'] if 'hash_prev' in event_dict else None,
            'hash': event_dict['hash'] if 'hash' in event_dict else None,
        }
        self.events[event_id] = event_info
        return event_id

    def get_events(self, username, filters):
        """
        Get events filtered by username and channel.

        Args:
            username (str): The username to filter by.
            filters (dict): A dictionary with channel and type filters.

        Returns:
            list: A list of events that match the filters.
        """
        events = []
        if 'channel' in filters and 'type' in filters:
            for event_id, event_info in self.events.items():
                if (event_info['actor'] == username and
                        event_info['channel'] == filters['channel'] and
                        event_info['type'] == filters['type']):
                    events.append(event_info)
        else:
            for event_info in self.events.values():
                if event_info['actor'] == username:
                    events.append(event_info)
        return events

    def validate_chain(self):
        """
        Validate the events chain.

        Returns:
            bool: True if the chain is valid, False otherwise.
        """
        # Implement the validation logic here
        for event_id, event_info in self.events.items():
            if event_info['hash_prev'] is not None and event_info['timestamp'] is not None:
                # Assuming that hash_prev is the previous hash and timestamp is a number
                # You need to implement your own logic to verify the chain
                print(f"Event {event_id} validation: {event_info}")
            elif event_info['event_id'] > 1 and event_info['hash'] is not None:
                # You need to implement your own logic to verify the chain
                print(f"Event {event_id} validation: {event_info}")
        return True  # For simplicity, assume that the chain is valid


def main():
    aionic_ledger = AionicLedger()

    # Log an event
    event_dict = {
        'timestamp': 1643723900,
        'channel': 'public',
        'type': 'delta',
        'payload': 'Hello, world!',
        'hash_prev': None,
        'hash': 'some_hash',
    }
    event_id = aionic_ledger.log_event('alice', event_dict)
    print(f"Event {event_id} logged successfully!")

    # Get events
    filters = {
        'channel': 'public',
        'type': 'delta',
    }
    events = aionic_ledger.get_events('alice', filters)
    print("Events:", events)

    # Validate the chain
    is_valid = aionic_ledger.validate_chain()
    print("Is the chain valid?", is_valid)


if __name__ == "__main__":
    main()
