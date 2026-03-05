from typing import Dict, List

class RecursionTracker:
    def __init__(self):
        self.max_depths = {'GENERATION': 3, 'TRAVERSAL': 23}
        self.current_depths = {'GENERATION': 0, 'TRAVERSAL': 0}
        self.depth_history = {'GENERATION': [], 'TRAVERSAL': []}

    def track_depth(self, op):
        curr = self.current_depths.get(op, 0)
        self.current_depths[op] = curr + 1
        self.depth_history[op].append(self.current_depths[op])
        return curr

    def check_depth_limit(self, op):
        return self.current_depths.get(op, 0) > self.max_depths.get(op, 99)

    def reset_depth(self, op):
        self.current_depths[op] = 0
        self.depth_history[op].clear()

    def get_depth_history(self, op):
        return self.depth_history.get(op, [])
